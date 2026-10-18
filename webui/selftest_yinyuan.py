#!/usr/bin/env python
# webui/selftest_yinyuan.py
"""「斐萃 → yinyuan」接入的**逻辑层直测**（不依赖 GUI —— 主要验收面）。

做什么（全部用**假 HTTP 层**，不打真实网络、不注册、不登录）：
  ① 登录体形状：手机号/邮箱分流、**口令不 trim**、`Authorization: Session <token>` 头；
  ② 自动建 key：`POST /keys` 的 label＝`斐萃-<主机名>`、`plain` **落盘 600**、返回值**只含 prefix**；
  ③ 泄漏面：明文/key/令牌**不出现在任何返回体、也不出现在任何日志记录**里；
  ④ 缓存：命中不打网络（计数为 0）、过期（>24h）重拉；
  ⑤ 失败面：超时 / 非 2xx(401,409,429) / 坏 JSON / 网络断 ⇒ 各自**结构化回落**，
     朝代回落本地 15 枚举并**逐字比对** `pdf_library.DYNASTY_OPTIONS`；
  ⑥ 分页：`total=450` ⇒ 按 `limit=200` 走 3 页拉全；作者/印文候选按 `art_names` /
     `courtesy_names` / `seal_name` / `transcription` 命中；
  ⑦ api 桥：`tab1_list` 用缓存值域（无缓存 ⇒ 本地 15）、`yinyuan_connect` 拒绝空输入、
     `yinyuan_suggest` 永不抛。

隔离：`FEICUI_DATA_DIR` 在 import `api` **之前**指到临时目录 ⇒ 密钥文件 / 缓存 / `.env` /
`.session.json` / `var/**` 全落 tmp；真实 `~/Library/Application Support/斐萃/` **一概不动**。

跑法：
    ./venv/bin/python webui/selftest_yinyuan.py            # 打印 PASS/FAIL + 落盘读数
    ./venv/bin/python webui/selftest_yinyuan.py --out /tmp/x.json
"""
from __future__ import annotations

import ast
import json
import logging
import os
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEBUI_DIR))

#: ⚠️ 必须在 import `api` / `yinyuan_client` 之前设好（隔离：不写真实用户目录）
SCRATCH = Path(tempfile.mkdtemp(prefix="feicui-yinyuan-selftest-"))
os.environ["FEICUI_DATA_DIR"] = str(SCRATCH / "data")
Path(os.environ["FEICUI_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

from src import pdf_library as lib  # noqa: E402
from src import yinyuan_client as yc  # noqa: E402

READINGS = WEBUI_DIR / "build" / "readings-yinyuan.json"
RESULTS: list[dict] = []
LOGS: list[str] = []


def record(name: str, ok: bool, detail: str = "", extra: dict | None = None) -> bool:
    RESULTS.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail,
                    "extra": extra or {}})
    print(("✅ " if ok else "❌ ") + f"{name}: {detail}", flush=True)
    return ok


class _LogTrap(logging.Handler):
    """把所有日志记录原文抓下来（用于断言「明文/令牌不进日志」）。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            LOGS.append(self.format(record))
        except Exception:
            pass


# ============================================================
# 假 HTTP 层
# ============================================================
def jresp(status: int, obj) -> yc.HttpResponse:
    return yc.HttpResponse(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))


class FakeTransport:
    """假 transport：按 `(method, path)` 路由；**记录每一次调用**（可断言打了没打）。"""

    def __init__(self, routes: dict | None = None, *, error: str = "", raw: bytes | None = None):
        self.routes = routes or {}
        self.calls: list[dict] = []
        self.error = error
        self.raw = raw

    def request(self, method, path, *, headers=None, json_body=None, timeout=None):
        self.calls.append({"method": method, "path": path,
                           "headers": dict(headers or {}), "json": json_body,
                           "timeout": timeout})
        if self.error:
            return yc.HttpResponse(0, b"", self.error)
        if self.raw is not None:
            return yc.HttpResponse(200, self.raw)
        base = path.split("?")[0]
        handler = self.routes.get((method, base)) or self.routes.get((method, "*"))
        if handler is None:
            return jresp(404, {"ok": False, "reason": "NOT_FOUND", "message": "密钥不存在。"})
        out = handler(path, headers or {}, json_body) if callable(handler) else handler
        return out

    def count(self, method: str | None = None, path_prefix: str = "") -> int:
        return sum(1 for c in self.calls
                   if (method is None or c["method"] == method)
                   and (path_prefix == "" or c["path"].startswith(path_prefix)))


PLAIN = "yy_TESTONLY0123456789abcdefghijklmnop"
SESSION_TOKEN = "sess-TESTONLY-0123456789"


def routes_ok(*, key_label: str = "", total_authors: int = 0, total_inscriptions: int = 0,
              dyn_values: tuple = lib.DYNASTY_OPTIONS, plain: str = PLAIN) -> dict:
    """一套正常应答（登录 / 建 key / 校验 / 朝代 / 作者 / 印文）。"""
    def login(path, headers, body):
        return jresp(200, {"ok": True,
                           "session": {"token": SESSION_TOKEN, "token_type": "Session",
                                       "expires_in": 604800,
                                       "expires_at": "2026-10-25T00:00:00.000Z"},
                           "user": {"id": "u-1", "role": "user", "phone": None, "email": "a@b.com",
                                    "status": "active"}})

    def create_key(path, headers, body):
        return jresp(201, {"ok": True, "key": {"id": "k-abc123", "prefix": plain[:11],
                                               "label": (body or {}).get("label"), "plain": plain}})

    def authors(path, headers, body):
        q = dict(kv.split("=", 1) for kv in path.split("?", 1)[1].split("&")) if "?" in path else {}
        offset = int(q.get("offset", 0))
        limit = int(q.get("limit", 50))
        items = [{"id": f"p-{i}", "name": f"作者{i:04d}", "courtesy_names": [f"字{i:04d}"],
                  "art_names": [f"号{i:04d}"], "alias_names": [], "dynasty": "清中期",
                  "birth_year": 1900, "death_year": 1980}
                 for i in range(offset, min(offset + limit, total_authors))]
        return jresp(200, {"ok": True, "data": {"total": total_authors, "limit": limit,
                                                "offset": offset, "items": items}})

    def inscriptions(path, headers, body):
        q = dict(kv.split("=", 1) for kv in path.split("?", 1)[1].split("&")) if "?" in path else {}
        offset = int(q.get("offset", 0))
        limit = int(q.get("limit", 50))
        seals = [f"印{i:04d}" for i in range(max(0, offset), min(offset + limit, total_inscriptions))]
        items = [{"id": f"s-{i}", "collection": "seals", "seal_name": f"白文印{i:04d}",
                  "transcription": name, "author": "作者0001", "dynasty": "漢",
                  "seal_type": "白文"} for i, name in enumerate(seals, start=offset)]
        return jresp(200, {"ok": True, "data": {"total": total_inscriptions, "limit": limit,
                                                "offset": offset, "items": items}})

    def dynasties(path, headers, body):
        return jresp(200, {"ok": True, "data": {
            "total": len(dyn_values),
            "items": [{"seq": i + 1, "value": v} for i, v in enumerate(dyn_values)],
            "counts": {"faces": {dyn_values[0]: 3}, "seals": {}},
            "unrecorded": {"faces": 0, "seals": 0}}})

    def verify(path, headers, body):
        return jresp(200, {"ok": True, "data": {"total": 1, "limit": 1, "offset": 0,
                                                "items": [{"id": "p-0", "name": "作者0000"}]}})

    return {("POST", "/api/v1/auth/login"): login,
            ("POST", "/api/v1/keys"): create_key,
            ("GET", "/api/v1/keys"): lambda p, h, b: jresp(200, {"ok": True, "items": [
                {"id": "k-abc123", "prefix": plain[:11], "label": key_label or "x",
                 "status": "active", "created_at": None, "last_used_at": None, "call_count": 1}]}),
            ("GET", "/api/v1/dynasties"): dynasties,
            ("GET", "/api/v1/authors"): authors,
            ("GET", "/api/v1/inscriptions"): inscriptions}


def new_client(tmp: Path, transport, **kw) -> yc.YinyuanClient:
    return yc.YinyuanClient(transport=transport, data_dir=tmp, label=kw.pop("label", "斐萃-testhost"),
                            **kw)


def mode_of(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def wait_warm(api_like, timeout: float = 15.0) -> bool:
    """等后台预热线程收尾（`_yy_warm_state.running` 变 False）。"""
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not api_like._yy_warm_state.get("running"):
            return True
        time.sleep(0.1)
    return False


def no_secret_in(obj, *secrets) -> tuple[bool, str]:
    """返回体里不许出现明文/令牌（序列化后子串检查）。"""
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        text = str(obj)
    for s in secrets:
        if s and s in text:
            return False, f"返回体含敏感串 {s[:8]}…"
    return True, "无明文/令牌"


# ============================================================
# 各项检查
# ============================================================
def check_import_purity() -> None:
    src = (WEBUI_DIR / "src" / "yinyuan_client.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                mods.add(node.module.split(".")[0])
    banned = {"webview", "streamlit", "requests", "httpx", "aiohttp", "urllib3", "tkinter"}
    hit = sorted(mods & banned)
    stdlib_ok = {"json", "logging", "os", "re", "socket", "sys", "urllib", "dataclasses",
                 "datetime", "pathlib", "pdf_library", "__future__", "typing"}
    unknown = sorted(mods - stdlib_ok)
    record("import/purity", not hit and not unknown,
           f"imports={sorted(mods)} 命中禁用={hit} 未知={unknown}")


def check_login_shape() -> None:
    tmp = SCRATCH / "c1"
    tr = FakeTransport(routes_ok())
    c = new_client(tmp, tr)
    r = c.login("13800000000", " p@ss word ")          # 前后空格**必须保留**
    body = (tr.calls[0] or {}).get("json") or {}
    ok = (r.get("ok") is True and tr.calls[0]["path"] == "/api/v1/auth/login"
          and body.get("phone") == "13800000000" and "email" not in body
          and body.get("password") == " p@ss word ")
    record("login/phone_split_password_not_trimmed", ok,
           f"path={tr.calls[0]['path']} body_keys={sorted(body)} "
           f"password={body.get('password')!r} len={len(body.get('password') or '')}")

    r2 = c.login("a@b.com", "x")
    body2 = tr.calls[1]["json"]
    record("login/email_split", r2.get("ok") is True and body2.get("email") == "a@b.com"
           and "phone" not in body2, f"body={body2}")

    n_before = len(tr.calls)
    r3 = c.login("not-an-identity", "x")
    record("login/bad_identity_local_no_network",
           r3.get("ok") is False and r3.get("reason") == "INVALID_INPUT" and len(tr.calls) == n_before,
           f"reason={r3.get('reason')} 新增调用={len(tr.calls) - n_before}")

    # 401 面
    tr2 = FakeTransport({("POST", "/api/v1/auth/login"):
                         lambda p, h, b: jresp(401, {"ok": False, "reason": "UNAUTHORIZED",
                                                     "message": "手机号/邮箱或口令不正确。"})})
    r4 = new_client(SCRATCH / "c1b", tr2).login("a@b.com", "bad")
    record("login/401_structured", r4.get("ok") is False and r4.get("reason") == "UNAUTHORIZED"
           and "不正确" in (r4.get("msg") or ""),
           f"status={r4.get('status')} reason={r4.get('reason')} msg={r4.get('msg')!r}")

    ok_tok, _ = no_secret_in(r, SESSION_TOKEN, " p@ss word ")
    record("login/token_not_in_response", ok_tok, "登录返回体不含 token/口令")

    # 会话头形态：建 key 走 Authorization: Session <token>
    tr3 = FakeTransport(routes_ok())
    c3 = new_client(SCRATCH / "c1c", tr3)
    c3.login("a@b.com", "pw")
    c3.create_key("斐萃-x")
    hdr = [x["headers"].get("Authorization") for x in tr3.calls if x["path"] == "/api/v1/keys"]
    record("login/session_header_shape", hdr == [f"Session {SESSION_TOKEN}"],
           f"Authorization={hdr}")


def check_key_lifecycle() -> None:
    tmp = SCRATCH / "c2"
    tr = FakeTransport(routes_ok())
    # 不显式给 label ⇒ 走默认标签 `斐萃-<主机名>`（本单要求的形态）
    c = yc.YinyuanClient(transport=tr, data_dir=tmp)
    res = c.connect("a@b.com", "pw")
    key_path = tmp / yc.KEY_FILE_NAME
    label_sent = [x["json"] for x in tr.calls if x["path"] == "/api/v1/keys" and x["method"] == "POST"]
    want_label = f"斐萃-{__import__('socket').gethostname()}"[:64]
    stored = json.loads(key_path.read_text(encoding="utf-8")) if key_path.exists() else {}
    mode_ok = key_path.exists() and mode_of(key_path) == 0o600
    record("key/auto_created_on_first_connect",
           res.get("ok") is True and res.get("created") is True and len(label_sent) == 1
           and label_sent[0].get("label") == want_label
           and yc.default_label() == want_label,
           f"created={res.get('created')} label={label_sent[0].get('label')!r} 期望={want_label!r}")
    record("key/plain_on_disk_600", mode_ok and stored.get("plain") == PLAIN,
           f"exists={key_path.exists()} mode={oct(mode_of(key_path)) if key_path.exists() else '—'} "
           f"plain_ok={stored.get('plain') == PLAIN} prefix={stored.get('prefix')!r}")
    ok_resp, why = no_secret_in(res, PLAIN, SESSION_TOKEN)
    record("key/plain_not_in_connect_response", ok_resp and "plain" not in res,
           f"{why}；返回键={sorted(res)}")

    st = c.status()
    ok_st, why_st = no_secret_in(st, PLAIN, SESSION_TOKEN)
    record("key/status_only_prefix", st.get("connected") is True and st.get("prefix") == PLAIN[:11]
           and ok_st and "plain" not in st,
           f"connected={st.get('connected')} prefix={st.get('prefix')!r} {why_st}")

    # 复用：再次 connect ⇒ 不发 POST /keys（只 verify 一次）
    tr.calls.clear()
    res2 = c.connect("a@b.com", "pw")
    posts = tr.count("POST", "/api/v1/keys")
    record("key/reuse_existing_no_duplicate",
           res2.get("ok") is True and res2.get("reused") is True and posts == 0,
           f"reused={res2.get('reused')} POST /keys={posts} 调用={[ (x['method'], x['path']) for x in tr.calls ]}")

    # 409 KEY_LIMIT
    trl = FakeTransport({("POST", "/api/v1/auth/login"):
                         lambda p, h, b: jresp(200, {"ok": True, "session": {"token": SESSION_TOKEN},
                                                     "user": {"id": "u", "role": "user"}}),
                         ("POST", "/api/v1/keys"):
                         lambda p, h, b: jresp(409, {"ok": False, "reason": "KEY_LIMIT",
                                                     "message": "每个账号最多保留 10 把有效密钥。"})})
    rl = new_client(SCRATCH / "c2b", trl).connect("a@b.com", "pw")
    record("key/limit_409_structured", rl.get("ok") is False and rl.get("reason") == "KEY_LIMIT"
           and "10" in (rl.get("msg") or ""),
           f"reason={rl.get('reason')} status={rl.get('status')} msg={rl.get('msg')!r}")

    # 断开：删文件
    dr = c.disconnect()
    record("key/disconnect_removes_file",
           dr.get("ok") is True and not key_path.exists() and c.status().get("connected") is False,
           f"removed={dr.get('removed')} 文件存在={key_path.exists()}")


def check_log_leak() -> None:
    """明文 / 令牌 / 口令**一律不进日志**。"""
    tmp = SCRATCH / "c3"
    tr = FakeTransport(routes_ok(total_authors=3))
    c = new_client(tmp, tr)
    LOGS.clear()
    res = c.connect("a@b.com", "p@ss word")
    c.fetch_dynasties(force=True)
    c.suggest_authors("作者")
    r = c.create_key("斐萃-x")            # 会话仍在 ⇒ 再建一把（触发一次 plain 日志路径）
    joined = "\n".join(LOGS)
    leaks = [s for s in (PLAIN, SESSION_TOKEN, "p@ss word") if s in joined]
    record("log/no_secret_leak", not leaks,
           f"日志条数={len(LOGS)} 泄漏={leaks}；日志样例={LOGS[:3]}")
    ok1, _ = no_secret_in([res, r], PLAIN, SESSION_TOKEN)
    record("log/all_payloads_clean", ok1, "connect/create_key 返回体均无明文")


def check_dynasty_cache_and_fallback() -> None:
    # ① 命中不打网络
    tmp = SCRATCH / "c4"
    tr = FakeTransport(routes_ok())
    c = new_client(tmp, tr)
    c._write_secure(tmp / yc.KEY_FILE_NAME,
                    {"schema": yc.KEY_SCHEMA, "base_url": c.base_url, "key_id": "k-1",
                     "prefix": PLAIN[:11], "label": "斐萃-t", "plain": PLAIN,
                     "created_at": "2026-10-18T00:00:00+00:00"})
    c._secrets.add(PLAIN)
    first = c.fetch_dynasties()
    n1 = len(tr.calls)
    second = c.fetch_dynasties()
    record("cache/dynasty_first_network_second_hit",
           first.get("source") == "network" and n1 == 1 and second.get("source") == "cache"
           and len(tr.calls) == n1 and second.get("items") == list(lib.DYNASTY_OPTIONS),
           f"first={first.get('source')}(调用{n1}) second={second.get('source')}"
           f"(累计{len(tr.calls)}) 值域一致={second.get('items') == list(lib.DYNASTY_OPTIONS)}")
    cache_file = tmp / yc.CACHE_DIR_NAME / "dynasties.json"
    record("cache/dynasty_file_written",
           cache_file.is_file() and mode_of(cache_file) == 0o600,
           f"{cache_file} mode={oct(mode_of(cache_file)) if cache_file.exists() else '—'}")

    # ② 过期（>24h）⇒ 重拉
    entry = json.loads(cache_file.read_text(encoding="utf-8"))
    entry["fetched_ts"] = (datetime.now(timezone.utc) - timedelta(hours=25)).timestamp()
    entry["fetched_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    cache_file.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    n_before = len(tr.calls)
    third = c.fetch_dynasties()
    record("cache/dynasty_expired_refetch", third.get("source") == "network"
           and len(tr.calls) == n_before + 1,
           f"source={third.get('source')} 新增调用={len(tr.calls) - n_before}")

    # ③ 失败面：超时 / 401 / 坏 JSON / 网络断 ⇒ 回落本地 15 枚举（逐字）
    want = list(lib.DYNASTY_OPTIONS)
    cases = {
        "timeout": FakeTransport(error="timeout"),
        "http401": FakeTransport({("GET", "*"): jresp(401, {"ok": False, "reason": "UNAUTHORIZED",
                                                            "message": "访问密钥缺失或无效。"})}),
        "bad_json": FakeTransport(raw=b"<html>502 Bad Gateway</html>"),
        "network": FakeTransport(error="network"),
    }
    for name, trx in cases.items():
        tmpc = SCRATCH / f"c4-{name}"
        cc = new_client(tmpc, trx)
        cc._write_secure(tmpc / yc.KEY_FILE_NAME,
                         {"schema": yc.KEY_SCHEMA, "base_url": cc.base_url, "prefix": PLAIN[:11],
                          "plain": PLAIN, "label": "x", "created_at": ""})
        cc._secrets.add(PLAIN)
        out = cc.fetch_dynasties()
        record(f"fallback/dynasty_{name}", out.get("source") == "fallback_local"
               and out.get("items") == want and out.get("degraded") is True,
               f"source={out.get('source')} reason={out.get('reason')} 15项逐字一致={out.get('items') == want}")

    # ④ 无 key（且无缓存）⇒ 本地 15 枚举，且**不打网络**
    trn = FakeTransport(routes_ok())
    cn = new_client(SCRATCH / "c4-nokey", trn)
    out = cn.fetch_dynasties()
    record("fallback/no_key_local_15_no_network",
           out.get("source") == "fallback_local" and out.get("items") == want
           and len(trn.calls) == 0 and out.get("reason") == "NO_KEY",
           f"source={out.get('source')} reason={out.get('reason')} 网络调用={len(trn.calls)} "
           f"15项逐字一致={out.get('items') == want}")

    # ⑤ 429 / 5xx 结构化
    for status, reason in ((429, "RATE_LIMITED"), (503, "NOT_CONFIGURED")):
        trx = FakeTransport({("GET", "*"): jresp(status, {"ok": False, "reason": reason,
                                                          "message": "稍后重试。"})})
        tmpc = SCRATCH / f"c4-{status}"
        cc = new_client(tmpc, trx)
        cc._write_secure(tmpc / yc.KEY_FILE_NAME,
                         {"schema": yc.KEY_SCHEMA, "base_url": cc.base_url, "prefix": PLAIN[:11],
                          "plain": PLAIN, "label": "x", "created_at": ""})
        out = cc.fetch_authors()
        record(f"fail/authors_http{status}_structured",
               out.get("ok") is False and out.get("reason") == reason and out.get("status") == status
               and out.get("items") == [],
               f"reason={out.get('reason')} status={out.get('status')} msg={out.get('msg')!r}")


def check_paging_and_suggest() -> None:
    tmp = SCRATCH / "c5"
    tr = FakeTransport(routes_ok(total_authors=450, total_inscriptions=260))
    c = new_client(tmp, tr)
    c._write_secure(tmp / yc.KEY_FILE_NAME,
                    {"schema": yc.KEY_SCHEMA, "base_url": c.base_url, "prefix": PLAIN[:11],
                     "plain": PLAIN, "label": "x", "created_at": ""})
    c._secrets.add(PLAIN)
    a = c.fetch_authors()
    offsets = [x["path"].split("offset=")[1] for x in tr.calls if x["path"].startswith("/api/v1/authors")]
    limits = [x["path"].split("limit=")[1].split("&")[0] for x in tr.calls
              if x["path"].startswith("/api/v1/authors")]
    record("paging/authors_450_by_200", a.get("ok") and a.get("count") == 450
           and offsets == ["0", "200", "400"] and set(limits) == {"200"} and a.get("total") == 450,
           f"count={a.get('count')} total={a.get('total')} offsets={offsets} limit={set(limits)}")

    n = len(tr.calls)
    a2 = c.fetch_authors()
    record("paging/authors_second_is_cache", a2.get("source") == "cache"
           and a2.get("count") == 450 and len(tr.calls) == n,
           f"source={a2.get('source')} 新增调用={len(tr.calls) - n}")

    s1 = c.suggest_authors("作者0007")
    s2 = c.suggest_authors("字0007")            # courtesy_names 命中
    s3 = c.suggest_authors("号0007")            # art_names 命中
    record("suggest/author_by_name_courtesy_artname",
           s1.get("items") and s1["items"][0]["value"] == "作者0007"
           and s2.get("items") and s2["items"][0]["value"] == "作者0007"
           and s3.get("items") and s3["items"][0]["value"] == "作者0007",
           f"name→{s1['items'][:1]} courtesy→{s2['items'][:1]} art→{s3['items'][:1]}")

    i = c.fetch_inscriptions()
    si1 = c.suggest_inscriptions("印01")
    si2 = c.suggest_inscriptions("印01")            # transcription 面
    record("suggest/inscription_seal_and_transcription",
           i.get("count") == 260 and si1.get("items") and si2.get("items"),
           f"count={i.get('count')} seal候选={[x['value'] for x in si1.get('items') or []][:3]}")

    # 无缓存 ⇒ degraded 空候选（不阻塞手输）
    cn = new_client(SCRATCH / "c5-nocache", FakeTransport(routes_ok()))
    d = cn.suggest_authors("陈")
    record("suggest/no_cache_degraded_empty",
           d.get("ok") is True and d.get("items") == [] and d.get("degraded") is True
           and d.get("reason") == "NO_CACHE",
           f"items={d.get('items')} degraded={d.get('degraded')} reason={d.get('reason')}")


def check_api_bridge() -> None:
    import api as api_mod  # 隔离后 import（DATA_DIR 已指到 SCRATCH/data）

    a = api_mod.FeicuiApi()
    # ① 无 key / 无缓存 ⇒ tab1 值域回落本地 15（逐字）
    root = SCRATCH / "feicui"
    for sub in lib.SUB_DIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    vr = a.verify_dir({"path": str(root)})
    t1 = a.tab1_list({})
    record("api/tab1_dynasty_fallback_local15",
           vr.get("ok") is True and t1.get("ok") is True
           and t1.get("dynasty_options") == list(lib.DYNASTY_OPTIONS)
           and t1.get("dynasty_source") == "fallback_local",
           f"verify={vr.get('ok')} source={t1.get('dynasty_source')} "
           f"n={len(t1.get('dynasty_options') or [])} 逐字一致={t1.get('dynasty_options') == list(lib.DYNASTY_OPTIONS)}")

    # ② 注入假 transport + 假数据根 ⇒ connect 全链路（key 落盘 600），tab1 改读缓存
    yy_root = SCRATCH / "api-yy"
    a.yinyuan = yc.YinyuanClient(transport=FakeTransport(routes_ok(
        dyn_values=("远1", "远2"), total_authors=2, total_inscriptions=3)),
                                 data_dir=yy_root, label="斐萃-apitest")
    bad = a.yinyuan_connect({"identifier": "", "password": ""})
    record("api/connect_rejects_empty", bad.get("ok") is False and bad.get("reason") == "INVALID_INPUT",
           f"reason={bad.get('reason')} msg={bad.get('msg')!r}")

    conn = a.yinyuan_connect({"identifier": "a@b.com", "password": " p "})   # 口令带空格
    keyf = yy_root / yc.KEY_FILE_NAME
    record("api/connect_creates_key_600",
           conn.get("ok") is True and conn.get("connected") is True and keyf.is_file()
           and mode_of(keyf) == 0o600 and conn.get("prefix") == PLAIN[:11]
           and "plain" not in conn,
           f"connected={conn.get('connected')} prefix={conn.get('prefix')!r} "
           f"mode={oct(mode_of(keyf)) if keyf.exists() else '—'} 返回键={sorted(conn)}")

    # 预热是后台线程 ⇒ 等它收尾后再同步跑一次（确定性），再看 tab1
    wait_warm(a)
    a._yy_warm(force=True)
    t1b = a.tab1_list({})
    record("api/tab1_dynasty_from_cache",
           t1b.get("dynasty_source") == "cache" and t1b.get("dynasty_options") == ["远1", "远2"],
           f"source={t1b.get('dynasty_source')} options={t1b.get('dynasty_options')}")

    sg = a.yinyuan_suggest({"kind": "author", "query": "作者"})
    si = a.yinyuan_suggest({"kind": "inscription", "query": "印"})
    record("api/suggest_bridge_ok",
           sg.get("ok") is True and sg.get("count", 0) >= 1 and sg["items"][0]["value"].startswith("作者")
           and si.get("count", 0) >= 1,
           f"author={sg.get('count')} {[x['value'] for x in sg.get('items') or []][:2]} "
           f"inscription={si.get('count')} {[x['value'] for x in si.get('items') or []][:2]}")

    # ③ 断网时 api 全链路不抛、不阻塞
    a.yinyuan = yc.YinyuanClient(transport=FakeTransport(error="timeout"), data_dir=SCRATCH / "api-dead",
                                 label="斐萃-dead")
    t1c = a.tab1_list({})
    sg2 = a.yinyuan_suggest({"kind": "inscription", "query": "印"})
    st = a.yinyuan_status()
    record("api/offline_no_throw",
           t1c.get("ok") is True and t1c.get("dynasty_options") == list(lib.DYNASTY_OPTIONS)
           and sg2.get("ok") is True and st.get("ok") is True and st.get("connected") is False,
           f"tab1 source={t1c.get('dynasty_source')} suggest={sg2.get('count')} "
           f"status.connected={st.get('connected')}")

    disc = a.yinyuan_disconnect()
    record("api/disconnect_bridge", disc.get("ok") is True, f"msg={disc.get('msg')!r}")


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="斐萃 × yinyuan 逻辑层直测（假 transport）")
    ap.add_argument("--out", default=str(READINGS))
    args = ap.parse_args(argv)

    trap = _LogTrap()
    trap.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root_log = logging.getLogger()
    root_log.addHandler(trap)
    root_log.setLevel(logging.DEBUG)
    for name in ("斐萃.yinyuan",):
        lg = logging.getLogger(name)
        lg.addHandler(trap)
        lg.setLevel(logging.DEBUG)

    print(f"SELFTEST_YINYUAN scratch={SCRATCH} data_dir={os.environ['FEICUI_DATA_DIR']}", flush=True)
    check_import_purity()
    check_login_shape()
    check_key_lifecycle()
    check_log_leak()
    check_dynasty_cache_and_fallback()
    check_paging_and_suggest()
    check_api_bridge()

    counts = {s: sum(1 for r in RESULTS if r["status"] == s) for s in ("PASS", "FAIL")}
    payload = {"schema": "feicui.yinyuan.selftest.v1",
               "generated_at": datetime.now().isoformat(timespec="seconds"),
               "scratch": str(SCRATCH), "counts": counts,
               "local_dynasty_options": list(lib.DYNASTY_OPTIONS), "checks": RESULTS}
    out = Path(args.out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"READINGS → {out}", flush=True)
    except Exception as exc:
        print(f"READINGS 落盘失败 {exc!r}", flush=True)
    print(f"SUMMARY pass={counts['PASS']} fail={counts['FAIL']}", flush=True)
    if not os.environ.get("FEICUI_KEEP_SCRATCH"):
        shutil.rmtree(SCRATCH, ignore_errors=True)
    return 0 if counts["FAIL"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
