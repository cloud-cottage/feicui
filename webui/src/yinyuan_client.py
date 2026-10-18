#!/usr/bin/env python
# webui/src/yinyuan_client.py
"""「斐萃」→ **yinyuan（印源）** 接入层：登录 → 自动建「斐萃专用」API Key → 读数据 → 缓存/离线回落。

口径（本单 B4）：
  * **纯逻辑层**：不 import `webview` / `streamlit` / 任何 GUI，也不 import `api.py`
    ⇒ 可直接被脚本 import 做直测（见 `webui/selftest_yinyuan.py`）。
  * **只用 stdlib**：HTTP 走 `urllib.request`（不引 requests 等新依赖）；
    `transport` 可注入（假 HTTP 层直测的唯一入口，见 `FakeTransport` 用法在 selftest）。
  * **永不抛**：超时 / 网络断 / 非 2xx / 非 JSON 一律折成结构化 dict
    （`{ok:false, reason, status, msg, …}`），绝不把异常抛到 UI，也绝不阻塞重命名主流程。
  * **密钥落盘**：首次登录成功后自动 `POST /api/v1/keys {label:"斐萃-<主机名>"}`，
    把 `plain` 写进 `~/Library/Application Support/斐萃/yinyuan.json`（**权限 600**），
    此后日常调用只用 key（不依赖 7 天会话）；会话**只在内存**，进程退出即失效。
  * **`plain` 不外泄**：返回值只给 `id/prefix/label`；`_secrets` 内的明文在写日志前统一替换成
    `yy_****`（`_scrub`），日志器「斐萃.yinyuan」不存在任何明文路径。
  * **离线纪律**：`/dynasties` 拿不到 ⇒ 回落本地 15 枚举（`pdf_library.DYNASTY_OPTIONS`，单一真源）；
    作者/印文拿不到 ⇒ 建议列表为空，输入框仍可自由手输，**不阻塞**。

上游契约（以 `yinyuan` 仓 `api/**` 为准，2026-10-18 线上复核）：
  * 登录 `POST /api/v1/auth/login`，体 `{phone?, email?, password}`（**手机号/邮箱二选一**，不是
    `phone_or_email`；口令**不 trim、不归一**）；成功 200 `{ok:true, session:{token,…}, user:{…}}`。
  * 会话头 `Authorization: Session <token>`。
  * 密钥 `GET|POST /api/v1/keys`（`POST` 体 `{label?, ttl?}` ⇒ 201 `{ok:true,key:{id,prefix,label,plain}}`，
    `plain` **只此一次**）；`PATCH|DELETE /api/v1/keys/{kid}`、`POST /api/v1/keys/{kid}/rotate`
    （线上由 `vercel.json` rewrite 折成 query，对外仍是路径形态）。
  * 数据 `GET /api/v1/{dynasties,authors,inscriptions}?limit=&offset=`，头 `Authorization: ApiKey <key>`，
    成功 `{ok:true, data:{…}}`；分页 `limit` 缺省 50 / **上限 200**（超出截断）/ `offset ≥ 0`。
  * 失败面统一信封 `{ok:false, reason, message}`：401 `UNAUTHORIZED` / 404 `NOT_FOUND` /
    409 `KEY_LIMIT` / 429 `RATE_LIMITED` / 503 `NOT_CONFIGURED` / 400 `INVALID_INPUT`、`INVALID_PARAM`。
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

#: 本地 15 类朝代值域的**单一真源**（`pdf_library.DYNASTY_OPTIONS`，逐字繁体、顺序即显示顺序）。
#: 包内相对导入；被当脚本直跑时退化成同目录绝对导入（两条路径都指向同一个常量）。
try:  # pragma: no cover - 导入形态分支
    from .pdf_library import DYNASTY_OPTIONS as LOCAL_DYNASTY_OPTIONS
except ImportError:  # pragma: no cover
    from pdf_library import DYNASTY_OPTIONS as LOCAL_DYNASTY_OPTIONS  # type: ignore

__all__ = [
    "DEFAULT_BASE_URL", "CACHE_TTL_SECONDS", "PAGE_LIMIT", "MAX_PAGES",
    "KEY_FILE_NAME", "HttpResponse", "UrllibTransport", "YinyuanClient",
    "LOCAL_DYNASTY_OPTIONS", "default_data_dir", "default_key_path", "default_label",
]

#: 上游站点（B1/B2/B2.1/B3 已上线；父级实测）
DEFAULT_BASE_URL = "https://yinyuan2026.vercel.app"
#: 数据缓存 24h（`…/cache/{dynasties,authors,inscriptions}.json`）
CACHE_TTL_SECONDS = 24 * 3600
#: 分页上限（服务端 `MAX_LIMIT = 200`，超出会被**截断**而非报错 ⇒ 客户端必须按 200 走页）
PAGE_LIMIT = 200
#: 单次同步最多翻几页（200 × 60 = 12000 条；超出记 `truncated`，不无限拉）
MAX_PAGES = 60
#: 密钥文件名（落在数据根，权限 600；不入库、不进包）
KEY_FILE_NAME = "yinyuan.json"
CACHE_DIR_NAME = "cache"
KEY_SCHEMA = "feicui.yinyuan.key.v1"
CACHE_SCHEMA = "feicui.yinyuan.cache.v1"
DEFAULT_TIMEOUT = 8.0
#: 索引/建议列表里单条字符串的最大长度（防脏数据把 UI 撑爆）
MAX_FIELD_LEN = 120

_LOG = logging.getLogger("斐萃.yinyuan")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PHONE_RE = re.compile(r"^\+?\d{6,20}$")


# ============================================================
# 路径 / 主机名（包外可写；`.env` / 密钥文件不入库不入包）
# ============================================================
def default_data_dir() -> Path:
    """数据根：`FEICUI_DATA_DIR`（打包态由 `pack_main.py` 设）优先，否则
    `~/Library/Application Support/斐萃/`（与打包态同址 ⇒ 源码态跑出来的 key 打包后仍可用）。"""
    env = os.environ.get("FEICUI_DATA_DIR") or ""
    if env:
        return Path(env).expanduser()
    return Path.home() / "Library" / "Application Support" / "斐萃"


def default_key_path(data_dir: Path | str | None = None) -> Path:
    return Path(data_dir or default_data_dir()) / KEY_FILE_NAME


def default_label() -> str:
    """专用密钥标签：`斐萃-<主机名>`（≤64 字符，服务端上限）。"""
    try:
        host = socket.gethostname() or "本机"
    except Exception:  # pragma: no cover
        host = "本机"
    host = re.sub(r"\s+", "-", host.strip())[:48] or "本机"
    return f"斐萃-{host}"[:64]


# ============================================================
# 传输层（stdlib urllib；可注入假层）
# ============================================================
@dataclass
class HttpResponse:
    """传输层原始结果。`error` 非空 ⇒ **没拿到 HTTP 响应**（timeout / network）。"""
    status: int = 0
    body: bytes = b""
    error: str = ""

    def json_or_none(self):
        if not self.body:
            return None
        try:
            return json.loads(self.body.decode("utf-8", "replace"))
        except Exception:
            return None

    def text(self, limit: int = 300) -> str:
        try:
            return self.body[:limit].decode("utf-8", "replace")
        except Exception:  # pragma: no cover
            return ""


class UrllibTransport:
    """默认传输层：`urllib.request`（无第三方依赖）。**永不抛**。"""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = str(base_url).rstrip("/")
        self.timeout = float(timeout)

    def request(self, method: str, path: str, *, headers: dict | None = None,
                json_body: dict | None = None, timeout: float | None = None) -> HttpResponse:
        url = self.base_url + path
        data = None
        if json_body is not None:
            # ⚠️ 口令**不 trim**：原样序列化（确保 `' pass '` 与 `'pass'` 不被归一）
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=str(method).upper())
        for key, value in (headers or {}).items():
            req.add_header(str(key), str(value))
        if data is not None:
            req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "feicui-webui/yinyuan-client")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return HttpResponse(int(getattr(resp, "status", 0) or 0), resp.read() or b"")
        except urllib.error.HTTPError as exc:  # 4xx/5xx：**有响应**，按状态码返回
            try:
                body = exc.read() or b""
            except Exception:
                body = b""
            return HttpResponse(int(exc.code or 0), body)
        except (socket.timeout, TimeoutError):
            return HttpResponse(0, b"", "timeout")
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), (socket.timeout, TimeoutError)):
                return HttpResponse(0, b"", "timeout")
            return HttpResponse(0, b"", "network")
        except Exception:
            return HttpResponse(0, b"", "network")


# ============================================================
# 客户端
# ============================================================
class YinyuanClient:
    """yinyuan 接入客户端。

    典型用法（`api.py`）::

        c = YinyuanClient()
        c.connect("13800000000", "口令")      # 登录 + 自动建 key（plain 落盘，不回传）
        c.fetch_dynasties()                   # 24h 缓存；拿不到 ⇒ 本地 15 枚举
        c.suggest_authors("陈")               # 读缓存索引，不打网络、不阻塞
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, *,
                 transport=None, timeout: float = DEFAULT_TIMEOUT,
                 data_dir: Path | str | None = None, key_path: Path | str | None = None,
                 label: str | None = None, now=None, logger=None) -> None:
        self.base_url = str(base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = float(timeout)
        self._data_dir = Path(data_dir).expanduser() if data_dir else default_data_dir()
        self._key_path = Path(key_path).expanduser() if key_path else default_key_path(self._data_dir)
        self._label = (label or default_label())[:64]
        self._transport = transport or UrllibTransport(self.base_url, self.timeout)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._log = logger or _LOG
        #: 会话**只在内存**（7 天有效，但本进程内用完即弃；日常只用 key）
        self._session: dict = {}
        #: 需要在日志里脱敏的明文（登录口令 / 密钥明文）
        self._secrets: set[str] = set()
        self._suggest_cache: dict[str, list] = {}

    # ---------------- 小工具 ----------------
    def _scrub(self, text) -> str:
        out = str(text)
        for secret in self._secrets:
            if secret and secret in out:
                out = out.replace(secret, "yy_****")
        return out

    def _info(self, msg: str) -> None:
        try:
            self._log.info(self._scrub(msg))
        except Exception:  # pragma: no cover
            pass

    def _warn(self, msg: str) -> None:
        try:
            self._log.warning(self._scrub(msg))
        except Exception:  # pragma: no cover
            pass

    def _now_iso(self) -> str:
        try:
            return self._now().isoformat()
        except Exception:  # pragma: no cover
            return datetime.now(timezone.utc).isoformat()

    def _now_ts(self) -> float:
        try:
            return float(self._now().timestamp())
        except Exception:  # pragma: no cover
            return float(datetime.now(timezone.utc).timestamp())

    # ---------------- HTTP ----------------
    def _request(self, method: str, path: str, *, headers=None, json_body=None,
                 timeout: float | None = None) -> dict:
        """打一次 HTTP，折成 `{status, error, json, text}`（**永不抛**）。"""
        try:
            raw = self._transport.request(method, path, headers=headers or {},
                                          json_body=json_body, timeout=timeout or self.timeout)
        except Exception as exc:  # 假层/自定义层抛了也不许冒泡
            self._warn(f"{method} {path} 传输层异常：{exc.__class__.__name__}")
            return {"status": 0, "error": "network", "json": None, "text": ""}
        status = int(getattr(raw, "status", 0) or 0)
        body = getattr(raw, "body", b"") or b""
        err = str(getattr(raw, "error", "") or "")
        payload = None
        if body:
            try:
                payload = json.loads(body.decode("utf-8", "replace"))
            except Exception:
                payload = None
        return {"status": status, "error": err, "json": payload if isinstance(payload, dict) else None,
                "text": body[:300].decode("utf-8", "replace") if body else ""}

    def _failure(self, res: dict, *, what: str) -> dict | None:
        """把失败面折成结构化 dict；成功返回 None。"""
        if res["error"] == "timeout":
            self._warn(f"{what}：超时（{self.timeout:g}s）")
            return {"ok": False, "reason": "TIMEOUT", "status": 0,
                    "msg": f"连接 yinyuan 超时（{what}）"}
        if res["error"]:
            self._warn(f"{what}：网络不可达（{res['error']}）")
            return {"ok": False, "reason": "NETWORK", "status": 0,
                    "msg": f"连不上 yinyuan（{what}）"}
        payload = res["json"]
        if payload is None:
            self._warn(f"{what}：响应非 JSON（HTTP {res['status']}）")
            return {"ok": False, "reason": "BAD_JSON", "status": res["status"],
                    "msg": "yinyuan 响应格式异常"}
        if not (200 <= res["status"] < 300) or payload.get("ok") is not True:
            reason = str(payload.get("reason") or f"HTTP_{res['status']}")
            message = str(payload.get("message") or "")
            self._warn(f"{what}：HTTP {res['status']} reason={reason}")
            return {"ok": False, "reason": reason, "status": res["status"],
                    "msg": self._scrub(message) or f"yinyuan 返回 {reason}"}
        return None

    # ---------------- 密钥文件（600） ----------------
    def _write_secure(self, path: Path, data: dict) -> bool:
        """原子写 + 权限 600（先写同目录临时文件再 `os.replace`）。"""
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(path.parent, 0o700)
            except Exception:
                pass
            text = json.dumps(data, ensure_ascii=False, indent=2)
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, text.encode("utf-8"))
            finally:
                os.close(fd)
            try:
                os.chmod(tmp, 0o600)
            except Exception:
                pass
            os.replace(str(tmp), str(path))
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass
            return True
        except Exception as exc:
            self._warn(f"写 {path.name} 失败：{exc.__class__.__name__}")
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            return False

    def read_key_file(self) -> dict | None:
        """读密钥文件（**只给内部用**；对外一律走 `status()`，不含 plain）。"""
        try:
            if not self._key_path.exists():
                return None
            raw = json.loads(self._key_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            plain = raw.get("plain") or ""
            if not isinstance(plain, str) or not plain:
                return None
            if raw.get("base_url") and str(raw["base_url"]).rstrip("/") != self.base_url:
                return None
            self._secrets.add(plain)
            return raw
        except Exception as exc:
            self._warn(f"读 {self._key_path.name} 失败：{exc.__class__.__name__}")
            return None

    def _api_key(self) -> str:
        raw = self.read_key_file()
        return str((raw or {}).get("plain") or "")

    def _key_headers(self) -> dict:
        plain = self._api_key()
        return {"Authorization": f"ApiKey {plain}"} if plain else {}

    # ---------------- ① 登录 ----------------
    def login(self, phone_or_email, password) -> dict:
        """登录（**手机号/邮箱二选一**自动分流；口令**不 trim**）。成功只回展示面，不回 token。"""
        ident = str(phone_or_email if phone_or_email is not None else "")
        pwd = str(password if password is not None else "")   # ⚠️ 不 strip()
        ident_key = ident.strip()
        if ident_key == "" or pwd == "":
            return {"ok": False, "reason": "INVALID_INPUT", "status": 0,
                    "msg": "请填写手机号/邮箱与口令"}
        self._secrets.add(pwd)
        body = {"password": pwd}
        if _EMAIL_RE.match(ident_key):
            body["email"] = ident_key
        elif _PHONE_RE.match(ident_key):
            body["phone"] = ident_key
        else:
            return {"ok": False, "reason": "INVALID_INPUT", "status": 0,
                    "msg": "手机号或邮箱格式不正确"}
        res = self._request("POST", "/api/v1/auth/login", json_body=body)
        fail = self._failure(res, what="登录")
        if fail:
            if fail["reason"] == "UNAUTHORIZED":
                fail["msg"] = "手机号/邮箱或口令不正确"
            return fail
        payload = res["json"] or {}
        session = payload.get("session") or {}
        token = session.get("token") or ""
        if not token:
            return {"ok": False, "reason": "BAD_SESSION", "status": res["status"],
                    "msg": "yinyuan 未返回会话令牌"}
        self._secrets.add(str(token))
        self._session = {"token": token,
                         "expires_at": session.get("expires_at") or "",
                         "expires_in": session.get("expires_in") or 0,
                         "obtained_at": self._now_iso()}
        user = payload.get("user") or {}
        self._info(f"登录成功 role={user.get('role')} expires_in={session.get('expires_in')}")
        return {"ok": True, "msg": "已登录 yinyuan", "status": res["status"],
                "expires_in": session.get("expires_in") or 0,
                "expires_at": session.get("expires_at") or "",
                "user": {"id": user.get("id"), "role": user.get("role") or "user"}}

    def session_token(self) -> str:
        return str(self._session.get("token") or "")

    def _session_headers(self) -> dict:
        token = self.session_token()
        return {"Authorization": f"Session {token}"} if token else {}

    # ---------------- ② 密钥 ----------------
    def create_key(self, label: str | None = None, *, persist: bool = True,
                   ttl: int | None = None) -> dict:
        """建一把「斐萃专用」key：`plain` **落盘 600**，返回值**只含 id/prefix/label**。"""
        token = self.session_token()
        if not token:
            return {"ok": False, "reason": "NO_SESSION", "status": 0,
                    "msg": "请先登录 yinyuan"}
        lbl = re.sub(r"\s+", " ", str(label or self._label).strip())[:64] or self._label
        body: dict = {"label": lbl}
        if ttl:
            body["ttl"] = int(ttl)
        res = self._request("POST", "/api/v1/keys", headers=self._session_headers(), json_body=body)
        fail = self._failure(res, what="创建密钥")
        if fail:
            if fail["reason"] == "KEY_LIMIT":
                fail["msg"] = "该账号有效密钥已达 10 把；请到 yinyuan 控制台撤销旧密钥后重试"
            return fail
        key = (res["json"] or {}).get("key") or {}
        plain = key.get("plain") or ""
        if not isinstance(plain, str) or not plain:
            return {"ok": False, "reason": "BAD_KEY", "status": res["status"],
                    "msg": "yinyuan 未返回密钥明文（无法保存）"}
        self._secrets.add(plain)
        record = {"schema": KEY_SCHEMA, "base_url": self.base_url,
                  "key_id": key.get("id") or "", "prefix": key.get("prefix") or "",
                  "label": key.get("label") or lbl, "plain": plain,
                  "created_at": self._now_iso()}
        stored = self._write_secure(self._key_path, record) if persist else False
        if persist and not stored:
            return {"ok": False, "reason": "STORE_FAILED", "status": res["status"],
                    "msg": "密钥已创建但本地保存失败（请检查数据目录权限）"}
        self._info(f"已创建专用密钥 prefix={record['prefix']} stored={stored}")
        return {"ok": True, "msg": "已创建斐萃专用密钥", "status": res["status"], "stored": bool(stored),
                "store_path": str(self._key_path) if stored else "",
                "key": {"id": record["key_id"], "prefix": record["prefix"], "label": record["label"]}}

    def list_keys(self) -> dict:
        """列本账号密钥（**会话态**接口）。只回 7 字段投影面，永不含明文。"""
        if not self.session_token():
            return {"ok": False, "reason": "NO_SESSION", "status": 0, "msg": "请先登录 yinyuan"}
        res = self._request("GET", "/api/v1/keys", headers=self._session_headers())
        fail = self._failure(res, what="密钥列表")
        if fail:
            return fail
        items = (res["json"] or {}).get("items") or []
        safe = [{"id": k.get("id"), "prefix": k.get("prefix"), "label": k.get("label"),
                 "status": k.get("status"), "created_at": k.get("created_at"),
                 "last_used_at": k.get("last_used_at"), "call_count": k.get("call_count")}
                for k in items if isinstance(k, dict)]
        return {"ok": True, "items": safe, "count": len(safe)}

    def verify_key(self) -> dict:
        """验证本地 key 是否仍可用（`GET /authors?limit=1`，最轻的一次 key 鉴权调用）。"""
        plain = self._api_key()
        if not plain:
            return {"ok": False, "reason": "NO_KEY", "status": 0, "msg": "本地没有 yinyuan 密钥"}
        res = self._request("GET", "/api/v1/authors?limit=1&offset=0", headers=self._key_headers())
        fail = self._failure(res, what="校验密钥")
        if fail:
            if fail["reason"] == "UNAUTHORIZED":
                fail["msg"] = "本地密钥已失效（被撤销或轮换），请重新连接"
            return fail
        return {"ok": True, "msg": "密钥可用", "status": res["status"]}

    def status(self) -> dict:
        """连接态（**只回 prefix，永不回明文**）。UI 的顶栏/弹窗都读这一面。"""
        raw = self.read_key_file()
        cache_dir = self._data_dir / CACHE_DIR_NAME
        caches = {}
        for name in ("dynasties", "authors", "inscriptions"):
            entry = self._cache_read(name, ttl=None)
            caches[name] = ({"fetched_at": entry.get("fetched_at"), "count": entry.get("count")}
                            if entry else None)
        return {"ok": True, "connected": bool(raw), "base_url": self.base_url,
                "prefix": (raw or {}).get("prefix") or "", "label": (raw or {}).get("label") or "",
                "key_id": (raw or {}).get("key_id") or "",
                "store_path": str(self._key_path), "key_file_exists": bool(raw),
                "cache_dir": str(cache_dir), "cache": caches,
                "session": {"active": bool(self.session_token()),
                            "expires_at": self._session.get("expires_at") or ""},
                "local_dynasty_count": len(LOCAL_DYNASTY_OPTIONS)}

    def connect(self, phone_or_email, password, *, force_new: bool = False) -> dict:
        """登录 ⇒ 若本地无可用 key 就自动建一把 ⇒ 落盘。返回展示面（不含明文）。"""
        login = self.login(phone_or_email, password)
        if not login.get("ok"):
            return login
        existing = self.read_key_file()
        if existing and not force_new:
            check = self.verify_key()
            if check.get("ok"):
                self._info(f"复用本地密钥 prefix={existing.get('prefix')}")
                return {"ok": True, "connected": True, "reused": True, "created": False,
                        "prefix": existing.get("prefix") or "", "label": existing.get("label") or "",
                        "key_id": existing.get("key_id") or "", "store_path": str(self._key_path),
                        "msg": "已连接 yinyuan（复用本地专用密钥）",
                        "session_expires_at": login.get("expires_at") or ""}
            self._warn("本地密钥已失效 ⇒ 重新创建")
        created = self.create_key(self._label)
        if not created.get("ok"):
            return created
        key = created.get("key") or {}
        return {"ok": True, "connected": True, "reused": False, "created": True,
                "prefix": key.get("prefix") or "", "label": key.get("label") or "",
                "key_id": key.get("id") or "", "store_path": created.get("store_path") or "",
                "msg": "已连接 yinyuan 并创建斐萃专用密钥",
                "session_expires_at": login.get("expires_at") or ""}

    def disconnect(self, *, revoke_remote: bool = False) -> dict:
        """断开：删本地密钥文件（默认**不在服务端撤销**，key 仍留在账号下可复用于其它机器）。"""
        raw = self.read_key_file()
        removed = False
        try:
            if self._key_path.exists():
                self._key_path.unlink()
                removed = True
        except Exception as exc:
            return {"ok": False, "reason": "STORE_FAILED", "status": 0,
                    "msg": f"删除本地密钥失败：{exc.__class__.__name__}"}
        if revoke_remote and raw and self.session_token():
            kid = raw.get("key_id") or ""
            if kid:
                self._request("DELETE", f"/api/v1/keys/{kid}", headers=self._session_headers())
        self._session = {}
        if raw:
            self._secrets.discard(str(raw.get("plain") or ""))
        self._info(f"已断开 yinyuan（删除本地密钥文件 removed={removed}）")
        return {"ok": True, "msg": "已断开 yinyuan", "removed": removed, "store_path": str(self._key_path)}

    # ---------------- ③ 缓存 ----------------
    def _cache_path(self, name: str) -> Path:
        return self._data_dir / CACHE_DIR_NAME / f"{name}.json"

    def _cache_read(self, name: str, *, ttl: float | None = CACHE_TTL_SECONDS) -> dict | None:
        """读缓存；`ttl=None` ⇒ 不判新旧（只要文件能读就给）。损坏/过期 ⇒ None。"""
        try:
            path = self._cache_path(name)
            if not path.exists():
                return None
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("schema") != CACHE_SCHEMA:
                return None
            if not isinstance(raw.get("payload"), dict):
                return None
            raw["_path"] = str(path)
            if ttl is not None:
                fetched = raw.get("fetched_ts")
                if not isinstance(fetched, (int, float)):
                    return None
                raw["_fresh"] = (self._now_ts() - float(fetched)) < float(ttl)
            return raw
        except Exception:
            return None

    def _cache_write(self, name: str, payload: dict, count: int | None = None) -> bool:
        entry = {"schema": CACHE_SCHEMA, "name": name, "base_url": self.base_url,
                 "fetched_at": self._now_iso(), "fetched_ts": self._now_ts(),
                 "count": count if count is not None else None, "payload": payload}
        return self._write_secure(self._cache_path(name), entry)

    # ---------------- ④ 数据：朝代 ----------------
    def local_dynasty_options(self) -> list[str]:
        """本地 15 枚举（离线回落面；与 `pdf_library.DYNASTY_OPTIONS` 逐字同源）。"""
        return list(LOCAL_DYNASTY_OPTIONS)

    def fetch_dynasties(self, *, force: bool = False, allow_network: bool = True,
                        ttl: float = CACHE_TTL_SECONDS) -> dict:
        """朝代值域（15 类）。顺序：鲜缓存 → 网络 → 陈旧缓存 → 本地 15 枚举。"""
        cached = self._cache_read("dynasties", ttl=ttl)
        if cached and cached.get("_fresh") and not force:
            return self._dyn_result(cached, "cache")
        if allow_network and self._api_key():
            res = self._request("GET", "/api/v1/dynasties", headers=self._key_headers())
            fail = self._failure(res, what="朝代值域")
            if not fail:
                payload = (res["json"] or {}).get("data") or {}
                items = payload.get("items") or []
                values = [str(it.get("value")) for it in items
                          if isinstance(it, dict) and it.get("value")]
                if values:
                    self._cache_write("dynasties", payload, count=len(values))
                    fresh = self._cache_read("dynasties", ttl=None) or {}
                    return self._dyn_result(fresh, "network")
                fail = {"ok": False, "reason": "EMPTY", "status": res["status"],
                        "msg": "yinyuan 朝代值域为空"}
            stale = cached or self._cache_read("dynasties", ttl=None)
            if stale:
                out = self._dyn_result(stale, "cache_stale")
                out["network_error"] = fail["reason"]
                return out
            return self._dyn_fallback(fail["reason"])
        if cached:
            return self._dyn_result(cached, "cache_stale")
        return self._dyn_fallback("NO_KEY" if not self._api_key() else "OFFLINE")

    def _dyn_result(self, entry: dict, source: str) -> dict:
        payload = entry.get("payload") or {}
        items = payload.get("items") or []
        values = [str(it.get("value")) for it in items if isinstance(it, dict) and it.get("value")]
        if not values:                      # 缓存里没值就当没有（宁可回落本地）
            return self._dyn_fallback("EMPTY_CACHE")
        return {"ok": True, "source": source, "items": values, "total": len(values),
                "seq": [int(it.get("seq") or i + 1) for i, it in enumerate(items)
                        if isinstance(it, dict)],
                "counts": payload.get("counts") or {}, "fetched_at": entry.get("fetched_at") or "",
                "degraded": source != "network"}

    def _dyn_fallback(self, reason: str) -> dict:
        values = self.local_dynasty_options()
        return {"ok": True, "source": "fallback_local", "items": values, "total": len(values),
                "counts": {}, "fetched_at": "", "degraded": True, "reason": reason}

    def dynasty_values(self, *, allow_network: bool = False) -> dict:
        """tab1 下拉用：**默认不打网络**（扫描主流程不许被 8s 超时卡住）。"""
        return self.fetch_dynasties(allow_network=allow_network)

    # ---------------- ⑤ 数据：作者 / 印文（分页全量 + 缓存） ----------------
    def _page(self, path: str, limit: int, offset: int) -> dict:
        url = f"{path}?limit={int(limit)}&offset={int(offset)}"
        return self._request("GET", url, headers=self._key_headers())

    def _fetch_all(self, name: str, path: str, *, force: bool = False,
                   ttl: float = CACHE_TTL_SECONDS, max_pages: int = MAX_PAGES) -> dict:
        """先探 `total`，再按 `limit=200` 循环拉全，最后整体写缓存。"""
        cached = self._cache_read(name, ttl=ttl)
        if cached and cached.get("_fresh") and not force:
            payload = cached.get("payload") or {}
            return {"ok": True, "source": "cache", "items": payload.get("items") or [],
                    "total": payload.get("total") or 0, "count": len(payload.get("items") or []),
                    "fetched_at": cached.get("fetched_at") or "", "degraded": True}
        if not self._api_key():
            stale = cached or self._cache_read(name, ttl=None)
            if stale:
                payload = stale.get("payload") or {}
                return {"ok": True, "source": "cache_stale", "items": payload.get("items") or [],
                        "total": payload.get("total") or 0, "count": len(payload.get("items") or []),
                        "fetched_at": stale.get("fetched_at") or "", "degraded": True,
                        "reason": "NO_KEY"}
            return {"ok": False, "reason": "NO_KEY", "items": [], "total": 0, "count": 0,
                    "degraded": True, "msg": "未连接 yinyuan（可自由手输）"}

        items: list = []
        total = 0
        pages = 0
        last_fail = None
        while pages < max_pages:
            res = self._page(path, PAGE_LIMIT, len(items))
            fail = self._failure(res, what=name)
            if fail:
                last_fail = fail
                break
            data = (res["json"] or {}).get("data") or {}
            total = int(data.get("total") or 0)
            page_items = data.get("items") or []
            pages += 1
            if not page_items:
                break
            items.extend([it for it in page_items if isinstance(it, dict)])
            if len(items) >= total:
                break
        if last_fail and not items:
            stale = cached or self._cache_read(name, ttl=None)
            if stale:
                payload = stale.get("payload") or {}
                return {"ok": True, "source": "cache_stale", "items": payload.get("items") or [],
                        "total": payload.get("total") or 0, "count": len(payload.get("items") or []),
                        "fetched_at": stale.get("fetched_at") or "", "degraded": True,
                        "reason": last_fail["reason"]}
            return {"ok": False, "reason": last_fail["reason"], "status": last_fail.get("status") or 0,
                    "items": [], "total": 0, "count": 0, "degraded": True, "msg": last_fail["msg"]}

        payload = {"total": total or len(items), "items": items, "pages": pages}
        self._cache_write(name, payload, count=len(items))
        self._info(f"{name} 同步完成 count={len(items)} total={payload['total']} pages={pages}")
        return {"ok": True, "source": "network", "items": items, "total": payload["total"],
                "count": len(items), "pages": pages, "degraded": False,
                "truncated": bool(total and len(items) < total and pages >= max_pages),
                "fetched_at": self._now_iso()}

    def fetch_authors(self, *, force: bool = False, ttl: float = CACHE_TTL_SECONDS) -> dict:
        return self._fetch_all("authors", "/api/v1/authors", force=force, ttl=ttl)

    def fetch_inscriptions(self, *, force: bool = False, ttl: float = CACHE_TTL_SECONDS) -> dict:
        return self._fetch_all("inscriptions", "/api/v1/inscriptions", force=force, ttl=ttl)

    # ---------------- ⑥ 候选补全（只读缓存，不打网络、不阻塞） ----------------
    @staticmethod
    def _clip(text) -> str:
        s = str(text if text is not None else "").strip()
        return s[:MAX_FIELD_LEN]

    @staticmethod
    def _as_list(value) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value if isinstance(v, (str, int, float)) and str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [value]
        return []

    def _author_index(self) -> list[dict]:
        if "authors" in self._suggest_cache:
            return self._suggest_cache["authors"]
        entry = self._cache_read("authors", ttl=None)
        rows = ((entry or {}).get("payload") or {}).get("items") or []
        index = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = self._clip(row.get("name"))
            if not name or name in seen:
                continue
            seen.add(name)
            index.append({"name": name,
                          "art_names": [self._clip(x) for x in self._as_list(row.get("art_names"))],
                          "courtesy_names": [self._clip(x) for x in self._as_list(row.get("courtesy_names"))],
                          "dynasty": self._clip(row.get("dynasty")),
                          "birth_year": row.get("birth_year"),
                          "death_year": row.get("death_year")})
        self._suggest_cache["authors"] = index
        return index

    def suggest_authors(self, query: str = "", limit: int = 8) -> dict:
        """作者候选：`name` / `art_names` / `courtesy_names` 子串匹配（空 query ⇒ 前 N 条）。"""
        limit = max(1, min(int(limit or 8), 50))
        q = str(query or "").strip()
        index = self._author_index()
        if not index:
            return {"ok": True, "items": [], "count": 0, "degraded": True,
                    "reason": "NO_CACHE", "msg": "作者库未同步（可自由手输）"}
        hits = []
        for row in index:
            fields = [row["name"], *row["art_names"], *row["courtesy_names"]]
            if q == "":
                hits.append((2, row))
                continue
            if any(f.startswith(q) for f in fields):
                hits.append((0, row))
            elif any(q in f for f in fields):
                hits.append((1, row))
        hits.sort(key=lambda pair: (pair[0], pair[1]["name"]))
        items = []
        for _, row in hits[:limit]:
            alias = [x for x in row["art_names"] + row["courtesy_names"] if x and x != row["name"]]
            items.append({"value": row["name"], "label": row["name"], "alias": alias[:4],
                          "hint": " · ".join([p for p in (row["dynasty"],) if p]),
                          "dynasty": row["dynasty"]})
        return {"ok": True, "items": items, "count": len(items), "degraded": False,
                "index_size": len(index)}

    def _inscription_index(self) -> list[dict]:
        if "inscriptions" in self._suggest_cache:
            return self._suggest_cache["inscriptions"]
        entry = self._cache_read("inscriptions", ttl=None)
        rows = ((entry or {}).get("payload") or {}).get("items") or []
        index, seen = [], set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            seal = self._clip(row.get("seal_name"))
            trans = self._clip(row.get("transcription"))
            for value in (trans, seal):
                if not value or value in seen:
                    continue
                seen.add(value)
                index.append({"value": value, "seal_name": seal, "transcription": trans,
                              "author": self._clip(row.get("author")),
                              "dynasty": self._clip(row.get("dynasty")),
                              "seal_type": self._clip(row.get("seal_type"))})
        self._suggest_cache["inscriptions"] = index
        return index

    def suggest_inscriptions(self, query: str = "", limit: int = 8) -> dict:
        """印文候选：`seal_name` / `transcription` 子串匹配。"""
        limit = max(1, min(int(limit or 8), 50))
        q = str(query or "").strip()
        index = self._inscription_index()
        if not index:
            return {"ok": True, "items": [], "count": 0, "degraded": True,
                    "reason": "NO_CACHE", "msg": "印文库未同步（可自由手输）"}
        hits = []
        for row in index:
            if q == "":
                hits.append((2, row))
                continue
            if row["value"].startswith(q):
                hits.append((0, row))
            elif q in row["value"]:
                hits.append((1, row))
            else:
                continue
        hits.sort(key=lambda pair: (pair[0], len(pair[1]["value"])))
        items = [{"value": row["value"], "label": row["value"],
                  "seal_name": row["seal_name"], "transcription": row["transcription"],
                  "author": row["author"], "dynasty": row["dynasty"]}
                 for _, row in hits[:limit]]
        return {"ok": True, "items": items, "count": len(items), "degraded": False,
                "index_size": len(index)}

    def drop_caches(self) -> dict:
        """清内存索引（重新同步后调用，避免读到旧索引）。"""
        self._suggest_cache.clear()
        return {"ok": True}
