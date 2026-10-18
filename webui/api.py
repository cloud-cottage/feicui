# webui/api.py
"""「斐萃」本地电脑版 —— **js_api 桥接层**（PyWebView `js_api` 的唯一后端面）。

架构纪律（Kevin 2026-10-16，PyWebView 换壳；同日口径变更：**只保留原生窗口形态**，
不做 HTTP/端口监听）：
  * 本文件是 **逻辑编排层**，**不 import streamlit、不 import webview**、不含任何 UI 代码
    ⇒ 与 `ui/`（纯 HTML/JS）严格分层；可直接被脚本 import 做单测（见 `selftest.py`）。
  * 能力全部**复用既有实现**，不重写算法：
      - tab1  → `src/pdf_library.py`（盘点 / pymupdf 探针 / 元数据侧车）
      - yinyuan（印源）→ `src/yinyuan_client.py`：登录 ⇒ 自动建「斐萃-<主机名>」专用 key
                （明文落 `…/斐萃/yinyuan.json`，600）⇒ 朝代/作者/印文只读 + 24h 缓存；
                拿不到就**静默回落**（本地 15 类 / 自由手输），不阻塞重命名主流程。
      - 目录键 → 老工程 `server/app/naming.py`（纯 stdlib，单一真源）
      - tab2  → 老工程引擎 **子进程**
                `venv/bin/python ops/book-page-2400/render_page_2400.py --pdf … --page … --dpi 1200`
                （单页 1200dpi ≈ 64 s ⇒ 必须异步线程 + 进度推送 + 可取消）
      - tab3  → `src/pdf_library.py`（子目录 / tiff 列表 / 测试 tiff）
                ＋ 本文件：缩略图网格数据（`sips -Z 150` → 内联 base64，三级引擎回退）、
                大图预览（`-Z 400`）、文件名解析/新名预览/校验（`src/validator.py` 单一真源）、
                重命名（同目录同名 ⇒ 拒）＋ **本地**操作记录（`webui/var/rename_log.jsonl`）。
                腾讯文档日志 / 百度网盘云盘锁 **未接入**：接口返回值一律带
                `cloud_log=not_connected` / `cloud_lock=not_connected`，UI 上明标。
      - 文件名模板 → `src/validator.py`
  * 所有方法**只返回 JSON 可序列化对象**且**永不抛**（本地用户机器上任何异常都要变成
    `{"ok": false, "msg": …}`，不能让桥断掉）。
  * 口令只在**后端**（本文件 / `.env`），前端只拿到 `{username, is_admin}`。
  * 进度推送：native 窗口模式下由 `app.py` 注入 `window.evaluate_js('onProgress(…)')`。

启动：
    ./venv/bin/python webui/app.py            # PyWebView 原生窗口（唯一形态）
    ./venv/bin/python webui/selftest.py       # 逻辑层直测（不依赖 GUI）
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# ── 源码态 / 打包态（PyInstaller）路径解析 ───────────────────────────────────────────
# 打包态由 `webui/build/pack_main.py` 在**导入本模块之前**设好两个环境变量：
#   FEICUI_WEBUI_DIR  包内**资源根**（MEIPASS：ui/ src/ assets/ ops/ server/app/ config/）
#   FEICUI_DATA_DIR   用户机**可写目录**（日志 / var / .env / .session.json）
# 源码态两者都不设 ⇒ 行为与此前逐字一致（同目录、仓根父级）。见 `webui/build/README.md` §1/§5。
WEBUI_DIR = Path(os.environ.get("FEICUI_WEBUI_DIR") or Path(__file__).resolve().parent)
REPO_ROOT = Path(os.environ.get("FEICUI_PACK_ROOT") or WEBUI_DIR.parent)
DATA_DIR = Path(os.environ.get("FEICUI_DATA_DIR") or WEBUI_DIR)
ENV_FILE = DATA_DIR / ".env"
UI_DIR = WEBUI_DIR / "ui"
VAR_DIR = DATA_DIR / "var"
JOBS_DIR = VAR_DIR / "jobs"
SESSION_FILE = DATA_DIR / ".session.json"
#: 打包态专用：`sys.executable` 是 PyInstaller 引导器（不是 python）⇒ 子进程必须带此标志，
#: 由 `pack_main.py` 识别后**在同包内**执行引擎脚本（见 README §2「子进程解释器」实测）。
ENGINE_RUN_FLAG = "--engine-run"
ENGINE_SCRIPT = REPO_ROOT / "ops" / "book-page-2400" / "render_page_2400.py"
VENV_PYTHON = REPO_ROOT / "venv" / "bin" / "python"

# 既有逻辑层（`src/*.py` 自身不得 import streamlit / webview；此处只做编排）
sys.path.insert(0, str(WEBUI_DIR))
sys.path.insert(0, str(REPO_ROOT / "server"))  # `app.naming`（纯 stdlib，无图像栈）

from src import pdf_library as lib  # noqa: E402
from src import validator  # noqa: E402
from src import yinyuan_client as yy  # noqa: E402

APP_NAME = "斐萃 · 本地电脑版"
APP_VERSION = "0.3.0-pywebview"
#: ── 标题/副标题 **单一真源**（改文案只改这两行；`app.py` 的窗口标题与 `ui/` 均从
#:    `app_info()` 取，HTML 里只留一份同值兜底）────────────────────────────────────
#: 口径（Kevin 2026-10-16）：**PyWebView 本地版带后缀** ⇒ `「斐萃」玺印解析任务台 · 本地电脑版`
#: （注意「· 本地电脑版」前有空格）；主标题沿用旧版 `webui/src/webui.py` L42 的
#: `APP_TITLE_IN_PAGE`（「斐萃」玺印解析任务台）＋ 本地版后缀。**其它页面不加后缀**。
APP_TITLE = "「斐萃」玺印解析任务台 · 本地电脑版"
APP_SLOGAN = "数字玺印生成工具"

SESSION_EXPIRE_DAYS = 7
DPI_WHITELIST = (1200, 2400)
DPI_DEFAULT = 1200

# ── tab3：3_Cropped_Tiff 视图/缩略图/本地记录口径（数值取自旧版 `webui/src/webui.py`）───
#: 四档视图（**逐字照旧** `webui.py` L560–565 的 view_cfg：large 5×20 / medium 10×50 /
#: small 20×100 / list 1×30）——分页与列数都在这里，UI 不自造。
TAB3_VIEW_CFG: dict[str, dict[str, int]] = {
    "large":  {"cols": 5,  "per_page": 20},
    "medium": {"cols": 10, "per_page": 50},
    "small":  {"cols": 20, "per_page": 100},
    "list":   {"cols": 1,  "per_page": 30},
}
TAB3_VIEW_DEFAULT = "medium"
#: 缩略图 / 大图预览长边（旧版 **逐字**：网格 `sips -Z 150`、大图 `sips -Z 400`）
TIFF_THUMB_MAX = 150
TIFF_PREVIEW_MAX = 400
#: 缩略图缓存（`webui/var/**` 不入库）＋ 本地操作记录（jsonl）
THUMBS_DIR = VAR_DIR / "thumbs"
RENAME_LOG = VAR_DIR / "rename_log.jsonl"
#: 外部依赖状态（**必须如实上报**：腾讯文档日志 / 百度网盘云盘锁 本壳尚未接入）
CLOUD_LOG_STATUS = "not_connected"
CLOUD_LOCK_STATUS = "not_connected"
CLOUD_NOTE = "日志同步（腾讯文档）/ 云盘锁暂未接入：本壳只写本地记录 webui/var/rename_log.jsonl"

# ── 用户表（**仅后端**；可被 .env 的 FEICUI_USERS 覆盖，格式 `user:pwd:admin|user,...`）──
_DEFAULT_USERS: dict[str, dict] = {
    "ji": {"pwd": "6666", "is_admin": True},
    "pan": {"pwd": "1234", "is_admin": False},
    "test": {"pwd": "test", "is_admin": False},
}


def _load_env() -> dict:
    """读 `webui/.env`（不依赖 python-dotenv，缺库也能起）。"""
    env: dict[str, str] = {}
    p = ENV_FILE
    if p.exists():
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
    for k, v in os.environ.items():  # 真实环境变量优先
        env.setdefault(k, v)
    return env


def _users() -> dict[str, dict]:
    raw = _load_env().get("FEICUI_USERS", "").strip()
    if not raw:
        return _DEFAULT_USERS
    users = {}
    for chunk in raw.split(","):
        parts = chunk.split(":")
        if len(parts) >= 2 and parts[0].strip():
            users[parts[0].strip()] = {
                "pwd": parts[1],
                "is_admin": (len(parts) > 2 and parts[2].strip().lower() in ("admin", "1", "true")),
            }
    return users or _DEFAULT_USERS


def _write_env_key(key: str, value: str) -> None:
    """把 `FEICUI_ROOT` 回写 `.env`（与旧 Streamlit 行为一致：下次启动免选目录）。"""
    p = ENV_FILE
    lines: list[str] = []
    if p.exists():
        lines = p.read_text(encoding="utf-8").splitlines()
    hit = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            hit = True
    if not hit:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}={value}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ============================================================
# tab2 长任务（异步线程 + JSONL 进度 + 可取消）
# ============================================================
class Job:
    """一个 HighRes 渲染任务（页级）。进度来自引擎 `--progress` 的 JSONL。"""

    def __init__(self, pdf: Path, page: int, dpi: int, out_path: Path, dir_key: str):
        self.id = uuid.uuid4().hex[:12]
        self.pdf = pdf
        self.page = page
        self.dpi = dpi
        self.out_path = out_path
        self.dir_key = dir_key
        self.progress_path = JOBS_DIR / f"{self.id}.progress.jsonl"
        self.log_path = JOBS_DIR / f"{self.id}.log"
        self.readings_path = out_path.parent / f"readings-P{page}-{dpi}dpi-48bit.json"
        self.state = "queued"          # queued|running|done|error|cancelled
        self.percent = 0
        self.message = "排队中"
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.finished_at = ""
        self.returncode: int | None = None
        self.error = ""
        self.proc: subprocess.Popen | None = None
        self._cancel = False
        self._lock = threading.Lock()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "job_id": self.id, "state": self.state, "percent": self.percent,
                "message": self.message, "pdf": self.pdf.name, "page": self.page,
                "dpi": self.dpi, "out": str(self.out_path), "dir_key": self.dir_key,
                "returncode": self.returncode, "error": self.error,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "log_tail": self._tail(),
            }

    def _tail(self, n: int = 12) -> str:
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-n:])
        except Exception:
            return ""


class JobRunner:
    """任务注册表 + 进度推送（native ⇒ `window.evaluate_js('onProgress(…)')`；serve ⇒ 轮询）。"""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._push = None            # callable(dict) —— 由 app.py 注入（evaluate_js）
        self._python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
        #: 打包态（PyInstaller）：`self._python` ＝ **引导器**（不是 python）⇒ 引擎调用必须加
        #: `ENGINE_RUN_FLAG` 让引导器把参数转给 `pack_main.py`，在同包解释器内执行引擎脚本。
        self._frozen = bool(getattr(sys, "frozen", False))
        self._engine_mode = "frozen-bootloader-reentry" if self._frozen else (
            "repo-venv" if VENV_PYTHON.exists() else "sys.executable")

    def attach_pusher(self, fn) -> None:
        self._push = fn

    def engine_python(self) -> str:
        return self._python

    def engine_prefix(self) -> list[str]:
        """引擎命令前缀（**单点**）：源码态＝`[venv/bin/python]`；打包态＝`[引导器, --engine-run]`。"""
        return [self._python, ENGINE_RUN_FLAG] if self._frozen else [self._python]

    def engine_mode(self) -> str:
        return self._engine_mode

    def create(self, pdf: Path, page: int, dpi: int, out_path: Path, dir_key: str) -> Job:
        job = Job(pdf, page, dpi, out_path, dir_key)
        with self._lock:
            self._jobs[job.id] = job
        t = threading.Thread(target=self._run, args=(job,), daemon=True)
        t.start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(str(job_id))

    def recent(self) -> list[dict]:
        with self._lock:
            jobs = list(self._jobs.values())
        return [j.snapshot() for j in sorted(jobs, key=lambda j: j.started_at, reverse=True)[:10]]

    def cancel(self, job_id: str) -> tuple[bool, str]:
        job = self.get(job_id)
        if job is None:
            return False, "任务不存在"
        if job.state in ("done", "error", "cancelled"):
            return False, f"任务已结束（{job.state}）"
        job._cancel = True
        with job._lock:
            job.message = "正在取消…"
        proc = job.proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()            # 只杀自己起的子进程（精确 PID）
            except Exception:
                pass
        return True, "已请求取消"

    # ---- 内部 ----
    def _push_event(self, job: Job) -> None:
        if self._push is None:
            return
        try:
            self._push(job.snapshot())
        except Exception:
            pass

    def engine_cmd(self, pdf: Path, page: int, dpi: int, out_path: Path,
                   progress_path: Path, readings_path: Path) -> list[str]:
        """引擎命令行（**单点构造**，便于不跑渲染就断言参数面：见 `selftest.py`）。"""
        return self.engine_prefix() + [
            str(ENGINE_SCRIPT),
            "--pdf", str(pdf), "--page", str(page), "--dpi", str(dpi),
            "--out", str(out_path),
            "--progress", str(progress_path),
            "--readings", str(readings_path),
            "--scratch", str(JOBS_DIR),
        ]

    def _run(self, job: Job) -> None:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        job.out_path.parent.mkdir(parents=True, exist_ok=True)
        job.progress_path.write_text("", encoding="utf-8")
        cmd = self.engine_cmd(job.pdf, job.page, job.dpi, job.out_path,
                              job.progress_path, job.readings_path)
        with job._lock:
            job.state = "running"
            job.message = "引擎已启动"
        self._push_event(job)
        try:
            with open(job.log_path, "wb") as log:
                job.proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), stdout=log,
                                            stderr=subprocess.STDOUT)
                rc = self._monitor(job)
        except Exception as exc:
            with job._lock:
                job.state = "error"
                job.error = f"{exc.__class__.__name__}: {exc}"
                job.message = job.error
            self._push_event(job)
            return
        with job._lock:
            job.returncode = rc
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            if job._cancel or rc == -15:
                job.state = "cancelled"
                job.message = "已取消"
            elif rc == 0 and job.out_path.exists():
                job.state = "done"
                job.percent = 100
                job.message = f"完成：{job.out_path.name}"
            else:
                job.state = "error"
                job.error = f"引擎退出码 {rc}"
                job.message = job.error
        self._push_event(job)

    def _monitor(self, job: Job) -> int:
        """轮询 JSONL 进度 + 进程存活；引擎写 `{"strip": i, "of": N, …}`。"""
        last = 0
        while True:
            proc = job.proc
            assert proc is not None
            try:
                data = job.progress_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                data = ""
            lines = [ln for ln in data.splitlines() if ln.strip()]
            if len(lines) > last:
                last = len(lines)
                try:
                    rec = json.loads(lines[-1])
                    of = int(rec.get("of") or 0)
                    i = int(rec.get("strip") or 0)
                    if of > 0:
                        with job._lock:
                            job.percent = min(99, int(i * 100 / of))
                            job.message = f"渲染 strip {i}/{of}"
                        self._push_event(job)
                except Exception:
                    pass
            rc = proc.poll()
            if rc is not None:
                return rc
            time.sleep(0.4)


# ============================================================
# js_api（暴露给 JS；也由 `serve.py` 逐方法转发）
# ============================================================
class FeicuiApi:
    def __init__(self) -> None:
        self.jobs = JobRunner()
        self._users = _users()
        self._session: dict | None = None
        self._root: str = ""
        self._nav_root = str(Path.home())
        # yinyuan（印源）接入：**纯逻辑层**客户端（`src/yinyuan_client.py`），
        # 密钥落 `~/Library/Application Support/斐萃/yinyuan.json`（600，不入库）；见 `yinyuan_*` 方法。
        self.yinyuan = yy.YinyuanClient()
        self._yy_warm_lock = threading.Lock()
        self._yy_warm_state: dict = {"running": False, "done": False, "last": {}}

    # ---------------- 应用信息 ----------------
    def app_info(self, _req: dict | None = None) -> dict:
        env = _load_env()
        name, is_admin = self._session_user()
        return {
            "ok": True, "app": APP_NAME, "version": APP_VERSION,
            "title": APP_TITLE, "slogan": APP_SLOGAN,
            "engine_python": self.jobs.engine_python(),
            "engine_mode": self.jobs.engine_mode(),
            "engine_prefix": self.jobs.engine_prefix(),
            "data_dir": str(DATA_DIR), "var_dir": str(VAR_DIR),
            "engine_script": str(ENGINE_SCRIPT), "engine_script_exists": ENGINE_SCRIPT.exists(),
            "repo_root": str(REPO_ROOT), "ui_dir": str(UI_DIR),
            "dpi_whitelist": list(DPI_WHITELIST), "dpi_default": DPI_DEFAULT,
            "feicui_root_env": env.get("FEICUI_ROOT", ""),
            "username": name, "is_admin": is_admin,
            "tab3_view_cfg": TAB3_VIEW_CFG, "tab3_view_default": TAB3_VIEW_DEFAULT,
            "tab3_thumb_max": TIFF_THUMB_MAX, "tab3_preview_max": TIFF_PREVIEW_MAX,
            "cloud_log": CLOUD_LOG_STATUS, "cloud_lock": CLOUD_LOCK_STATUS,
            "log_note": CLOUD_NOTE,
        }

    # ---------------- 登录 / 会话（口令仅在后端） ----------------
    def session_state(self, _req: dict | None = None) -> dict:
        name, is_admin, root = self._load_session()
        if name:
            self._nav_root = root or self._nav_root
        return {"ok": True, "logged_in": bool(name), "username": name or "",
                "is_admin": bool(is_admin), "feicui_root": root or self._root or "",
                "dir_verified": bool(root and self._root == root)}

    def login(self, req: dict | None = None) -> dict:
        req = req or {}
        name = str(req.get("username", "")).strip()
        pwd = str(req.get("password", ""))
        user = self._users.get(name)
        if not user or user["pwd"] != pwd:
            time.sleep(0.35)          # 轻微延迟，挫伤暴力猜测（旧行为无此延时，仅加固）
            return {"ok": False, "msg": "账号或密码错误"}
        self._save_session(name, self._root)
        return {"ok": True, "msg": "登录成功", "user": {"username": name,
                "is_admin": bool(user["is_admin"]), "feicui_root": self._root}}

    def logout(self, _req: dict | None = None) -> dict:
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
        except Exception:
            pass
        self._session = None
        self._root = ""
        return {"ok": True, "msg": "已退出登录"}

    def _save_session(self, username: str, feicui_root: str = "") -> None:
        data = {"username": username,
                "expire": (datetime.now() + timedelta(days=SESSION_EXPIRE_DAYS)).isoformat(),
                "feicui_root": feicui_root}
        try:
            SESSION_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self._session = data

    def _load_session(self) -> tuple[str | None, bool, str]:
        if not SESSION_FILE.exists():
            return None, False, ""
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            if datetime.now() > datetime.fromisoformat(data["expire"]):
                SESSION_FILE.unlink()
                return None, False, ""
            name = data.get("username", "")
            user = self._users.get(name)
            if not user:
                return None, False, ""
            root = data.get("feicui_root", "") or ""
            if root:
                self._root = root
            return name, bool(user["is_admin"]), root
        except Exception:
            return None, False, ""

    # ---------------- 目录选择 / 校验 ----------------
    def browse(self, req: dict | None = None) -> dict:
        """列目录（默认起点＝家目录；`path` 给绝对路径则列它）。只列子目录 + 常用候选。"""
        req = req or {}
        raw = str(req.get("path", "")).strip()
        try:
            path = Path(raw).expanduser().resolve() if raw else Path(self._nav_root)
            if not path.is_dir():
                return {"ok": False, "msg": f"不是目录：{path}"}
            entries = sorted([e.name for e in path.iterdir()
                              if e.is_dir() and not e.name.startswith(".")])
            self._nav_root = str(path)
            return {"ok": True, "path": str(path), "parent": str(path.parent),
                    "entries": entries, "is_feicui": path.name == lib.FEICUI_NAME,
                    "home": str(Path.home())}
        except PermissionError:
            return {"ok": False, "msg": "无权限访问该目录", "path": raw}
        except Exception as exc:
            return {"ok": False, "msg": f"{exc.__class__.__name__}: {exc}"}

    def verify_dir(self, req: dict | None = None) -> dict:
        """校验并（通过后）记住 feicui 根：`src/pdf_library.verify_feicui_dir` 逐字复用。"""
        req = req or {}
        path = str(req.get("path", "")).strip()
        if not path:
            return {"ok": False, "msg": "未指定目录"}
        ok, msg = lib.verify_feicui_dir(Path(path).expanduser())
        if not ok:
            return {"ok": False, "msg": msg, "path": path}
        name, _, _ = self._load_session()          # 先取登录名（_load_session 会顺带套用旧 root）
        self._root = str(Path(path).expanduser().resolve())   # 再钉新 root（顺序不可颠倒）
        self._nav_root = self._root
        _write_env_key("FEICUI_ROOT", self._root)
        if name:
            self._save_session(name, self._root)
        return {"ok": True, "msg": msg, "feicui_root": self._root}

    def ensure_subdirs(self, req: dict | None = None) -> dict:
        req = req or {}
        path = str(req.get("path", "")).strip() or self._root
        ok, msg = lib.ensure_standard_subdirs(Path(path).expanduser() if path else Path("."))
        return {"ok": ok, "msg": msg, "path": path}

    def _root_path(self) -> Path:
        return Path(self._root) if self._root else Path("")

    def _need_root(self) -> dict | None:
        if not self._root or not Path(self._root).is_dir():
            return {"ok": False, "msg": "尚未选择并校验 feicui 目录", "need_dir": True}
        return None

    # ---------------- tab1：1_Original_PDF ----------------
    def tab1_list(self, req: dict | None = None) -> dict:
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        force = bool(req.get("force_probe"))
        try:
            res = lib.scan(self._root_path(), force_probe=force)
        except Exception as exc:
            return {"ok": False, "msg": f"扫描失败：{exc.__class__.__name__}: {exc}"}
        rows = [r.as_row() for r in res["rows"]]
        meta = [{"filename": r.filename, "dynasty": r.dynasty or "", "author": r.author or "",
                 "notes": r.notes or "", "page_count": r.page_count,
                 "scan_dpi": r.scan_dpi, "probe_error": r.probe_error,
                 "updated_at": r.updated_at} for r in res["rows"]]
        # 朝代下拉值域：**优先 yinyuan**（/dynasties 的 items[].value，24h 缓存），
        # 拿不到（无 key / 无网 / 缓存空）⇒ 回落本地 15 枚举（`lib.DYNASTY_OPTIONS`）。
        # ⚠️ 这里**只读缓存、不打网络**：tab1 扫描主流程不许被 8 s 超时卡住；
        #    联网刷新在 `yinyuan_status` / `yinyuan_connect` 的后台预热线程里做。
        dyn = self._yy_dynasty_safe()
        return {"ok": True, "root": res["root"], "rows": rows, "items": meta,
                "stats": res["stats"], "probe_available": res["probe_available"],
                "dynasty_options": dyn["items"], "dynasty_source": dyn["source"],
                "tab": lib.ORIGINAL_DIR}

    # ---------------- yinyuan（印源）接入 ----------------
    def _yy_dynasty_safe(self) -> dict:
        """朝代值域（缓存优先；永不抛、永不联网阻塞）。"""
        try:
            return self.yinyuan.dynasty_values(allow_network=False)
        except Exception:
            return {"ok": True, "source": "fallback_local",
                    "items": list(lib.DYNASTY_OPTIONS), "degraded": True, "reason": "EXC"}

    def _yy_warm(self, *, force: bool = False) -> dict:
        """后台预热：拉朝代 + 作者 + 印文并落缓存（**线程里跑**，UI 不等它）。"""
        with self._yy_warm_lock:
            if self._yy_warm_state["running"]:
                return {"ok": True, "skipped": True, "msg": "预热进行中"}
            self._yy_warm_state["running"] = True
        out: dict = {}
        try:
            out["dynasties"] = self.yinyuan.fetch_dynasties(force=force).get("source")
            out["authors"] = self.yinyuan.fetch_authors(force=force).get("count")
            out["inscriptions"] = self.yinyuan.fetch_inscriptions(force=force).get("count")
            self.yinyuan.drop_caches()
        except Exception as exc:
            out["error"] = f"{exc.__class__.__name__}: {exc}"
        finally:
            with self._yy_warm_lock:
                self._yy_warm_state["running"] = False
                self._yy_warm_state["done"] = True
                self._yy_warm_state["last"] = out
        return {"ok": True, **out}

    def _yy_warm_async(self, *, force: bool = False) -> None:
        try:
            threading.Thread(target=self._yy_warm, kwargs={"force": force},
                             name="yy-warm", daemon=True).start()
        except Exception:
            pass

    def yinyuan_status(self, _req: dict | None = None) -> dict:
        """连接态（只回 prefix，不回明文）+ 缓存读数；顺带触发一次后台预热（仅当已连且有 key）。"""
        try:
            st = self.yinyuan.status()
        except Exception as exc:
            return {"ok": False, "msg": f"{exc.__class__.__name__}: {exc}"}
        st["warm"] = dict(self._yy_warm_state)
        if st.get("connected") and not self._yy_warm_state["done"]:
            self._yy_warm_async()
        return st

    def yinyuan_connect(self, req: dict | None = None) -> dict:
        """登录 yinyuan ⇒ 本地无 key 就自动建「斐萃-<主机名>」⇒ plain 落盘 600。

        ⚠️ 口令**原样**传给逻辑层（不 strip、不归一）；返回值只含 prefix。
        """
        req = req or {}
        ident = str(req.get("identifier", "") or "")
        pwd = req.get("password")
        pwd = "" if pwd is None else str(pwd)      # **不 strip**
        try:
            res = self.yinyuan.connect(ident, pwd, force_new=bool(req.get("force_new")))
        except Exception as exc:
            return {"ok": False, "reason": "EXC", "msg": f"{exc.__class__.__name__}: {exc}"}
        if res.get("ok") and res.get("connected"):
            self._yy_warm_async(force=True)
        return res

    def yinyuan_disconnect(self, _req: dict | None = None) -> dict:
        try:
            out = self.yinyuan.disconnect()
        except Exception as exc:
            return {"ok": False, "reason": "EXC", "msg": f"{exc.__class__.__name__}: {exc}"}
        with self._yy_warm_lock:
            self._yy_warm_state.update({"running": False, "done": False, "last": {}})
        return out

    def yinyuan_sync(self, req: dict | None = None) -> dict:
        """手动「重新同步」（force）：同步执行（用户在等，允许慢一点；有 8 s×页 超时兜底）。"""
        req = req or {}
        return self._yy_warm(force=bool(req.get("force", True)))

    def yinyuan_suggest(self, req: dict | None = None) -> dict:
        """tab3 候选补全：`kind=author|inscription`，`query` 子串；**只读缓存，不打网络**。"""
        req = req or {}
        kind = str(req.get("kind", "author") or "author")
        query = str(req.get("query", "") or "")
        try:
            limit = int(req.get("limit") or 8)
        except Exception:
            limit = 8
        try:
            if kind == "inscription":
                return self.yinyuan.suggest_inscriptions(query, limit=limit)
            return self.yinyuan.suggest_authors(query, limit=limit)
        except Exception:
            # 候选补全**永远不许**影响重命名主流程 ⇒ 静默降级为「无候选」
            return {"ok": True, "items": [], "count": 0, "degraded": True, "reason": "EXC"}

    def tab1_save_meta(self, req: dict | None = None) -> dict:
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        filename = str(req.get("filename", "")).strip()
        if not filename:
            return {"ok": False, "msg": "未指定文件"}
        try:
            ok, msg = lib.update_book_meta(
                filename,
                dynasty=req.get("dynasty"),
                author=req.get("author"),
                notes=req.get("notes"),
            )
        except Exception as exc:
            return {"ok": False, "msg": f"保存失败：{exc.__class__.__name__}: {exc}"}
        return {"ok": ok, "msg": msg}

    # ---------------- tab2：2_HighRes_PDF ----------------
    def _dir_key_of(self, pdf_name: str) -> str:
        """目录键＝老工程 `naming.dir_key_for`（ISBN 优先）；不可用时回落 PDF 主名。"""
        try:
            from app import naming as _naming  # noqa: WPS433（延迟导入，失败也不致命）
            return _naming.dir_key_for(pdf_name, _naming.load_dir_keys())
        except Exception:
            return Path(pdf_name).stem

    def tab2_list(self, _req: dict | None = None) -> dict:
        miss = self._need_root()
        if miss:
            return miss
        root = self._root_path()
        out_dir = root / lib.HIGHRES_DIR
        dirs: list[dict] = []
        if out_dir.is_dir():
            for d in sorted([x for x in out_dir.iterdir() if x.is_dir()], key=lambda p: p.name):
                files = []
                for f in sorted(d.iterdir()):
                    if f.is_file() and f.suffix.lower() in (".tif", ".tiff"):
                        stt = f.stat()
                        files.append({
                            "name": f.name, "size_mb": round(stt.st_size / 1024 / 1024, 1),
                            "mtime": datetime.fromtimestamp(stt.st_mtime).strftime("%Y-%m-%d %H:%M"),
                            "path": str(f),
                        })
                dirs.append({"dir_key": d.name, "path": str(d), "files": files,
                             "file_count": len(files)})
        sources = []
        for p in lib.list_pdf_files(root):
            sources.append({"filename": p.name, "path": str(p),
                            "dir_key": self._dir_key_of(p.name),
                            "size_mb": round(p.stat().st_size / 1024 / 1024, 1)})
        return {"ok": True, "root": str(root), "out_dir": str(out_dir), "dirs": dirs,
                "sources": sources, "dpi_whitelist": list(DPI_WHITELIST),
                "dpi_default": DPI_DEFAULT, "tab": lib.HIGHRES_DIR,
                "engine": {"python": self.jobs.engine_python(), "script": str(ENGINE_SCRIPT),
                           "exists": ENGINE_SCRIPT.exists()},
                "jobs": self.jobs.recent()}

    def tab2_generate(self, req: dict | None = None) -> dict:
        """异步启动一页 HighRes 渲染（1200dpi 单页 ≈64 s）。立即返回 job_id。"""
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        name = str(req.get("filename", "")).strip()
        if not name:
            return {"ok": False, "msg": "未选择源 PDF"}
        pdf = self._root_path() / lib.ORIGINAL_DIR / name
        if not pdf.is_file():
            return {"ok": False, "msg": f"源 PDF 不存在：{pdf}"}
        raw_page = req.get("page", None)
        try:
            page = 1 if raw_page in (None, "") else int(raw_page)
        except Exception:
            return {"ok": False, "msg": "页号必须是整数"}
        if page < 1:
            return {"ok": False, "msg": "页号从 1 开始"}
        try:
            dpi = int(req.get("dpi") or DPI_DEFAULT)
        except Exception:
            dpi = DPI_DEFAULT
        if dpi not in DPI_WHITELIST:
            return {"ok": False, "msg": f"dpi 只支持 {list(DPI_WHITELIST)}"}
        # 预检：引擎硬断言「目标 dpi 须为扫描 dpi 的整数倍」（否则白跑 ≈80 s 才报错）
        if not bool(req.get("force")):
            book = (lib.load_meta().get("books") or {}).get(name, {}) or {}
            sd = book.get("scan_dpi")
            if isinstance(sd, int) and sd > 0 and dpi % sd != 0:
                return {"ok": False, "scan_dpi": sd, "retryable_with_force": True,
                        "msg": (f"目标 dpi {dpi} 不是扫描 dpi（tab1 探针估 {sd}）的整数倍："
                                f"引擎只做整数倍上采样（硬断言）。请改选 dpi / 换页后重扫探针；"
                                f"确要强行提交可传 force=true。")}
        if not ENGINE_SCRIPT.exists():
            return {"ok": False, "msg": f"引擎脚本缺失：{ENGINE_SCRIPT}"}
        dir_key = self._dir_key_of(name)
        out_path = self._root_path() / lib.HIGHRES_DIR / dir_key / f"P{page}-{dpi}dpi-48bit.tif"
        if out_path.exists() and not bool(req.get("overwrite")):
            return {"ok": False, "msg": f"产物已存在（不会覆盖）：{out_path.name}",
                    "exists": True, "out": str(out_path)}
        job = self.jobs.create(pdf, page, dpi, out_path, dir_key)
        return {"ok": True, "msg": "已开始渲染（异步）", "job": job.snapshot(),
                "note": "单页 1200dpi ≈64 s；进度见 onProgress / tab2_job"}

    def tab2_job(self, req: dict | None = None) -> dict:
        req = req or {}
        job = self.jobs.get(str(req.get("job_id", "")))
        if job is None:
            return {"ok": False, "msg": "任务不存在"}
        return {"ok": True, "job": job.snapshot()}

    def tab2_cancel(self, req: dict | None = None) -> dict:
        req = req or {}
        ok, msg = self.jobs.cancel(str(req.get("job_id", "")))
        return {"ok": ok, "msg": msg}

    def open_in_finder(self, req: dict | None = None) -> dict:
        """在访达里定位产物（仅 macOS；失败只报错，不抛）。"""
        req = req or {}
        p = Path(str(req.get("path", "")))
        if not p.exists():
            return {"ok": False, "msg": "路径不存在"}
        try:
            subprocess.Popen(["open", "-R" if p.is_file() else "", str(p)] if p.is_file()
                             else ["open", str(p)])
            return {"ok": True, "msg": "已在访达打开"}
        except Exception as exc:
            return {"ok": False, "msg": f"{exc.__class__.__name__}: {exc}"}

    # ---------------- tab3：3_Cropped_Tiff ----------------
    def tab3_list(self, req: dict | None = None) -> dict:
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        root = self._root_path()
        subs = lib.list_subdirs(root)
        cur = str(req.get("subdir", "")).strip()
        if cur not in subs:
            cur = subs[0] if subs else ""
        files = []
        for n in lib.list_tiff_files(root, cur) if cur else []:
            f = root / lib.TIFF_DIR / cur / n
            stt = f.stat()
            parsed = validator.parse_filename(n)
            files.append({
                "name": n, "size_mb": round(stt.st_size / 1024 / 1024, 2),
                "mtime": datetime.fromtimestamp(stt.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "standard": validator.is_standard_tiff(n),
                "shiwen": parsed[0] if parsed else "", "dynasty": parsed[1] if parsed else "",
                "author": parsed[2] if parsed else "",
                "path": str(f),
            })
        name, is_admin = self._session_user()
        return {"ok": True, "root": str(root), "tab": lib.TIFF_DIR, "subdirs": subs,
                "current": cur, "files": files,
                "count": len(files), "template": f"{validator.PREFIX}释文-朝代-作者{validator.SUFFIX}",
                "view_cfg": TAB3_VIEW_CFG, "view_default": TAB3_VIEW_DEFAULT,
                "thumb_max": TIFF_THUMB_MAX, "preview_max": TIFF_PREVIEW_MAX,
                "limits": {"shiwen_max": validator.SHIWEN_MAX, "author_max": validator.AUTHOR_MAX},
                "operator": name, "is_admin": bool(is_admin),
                "cloud_log": CLOUD_LOG_STATUS, "cloud_lock": CLOUD_LOCK_STATUS, "note": CLOUD_NOTE}

    def tab3_generate_test(self, req: dict | None = None) -> dict:
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        # 旧版是「仅管理员渲染按钮」（UI 层门禁）；本壳保留该口径，并在**后端**加一道：
        # 只有「已登录且非管理员」才拒（未登录的纯逻辑测试不受影响 ⇒ selftest 仍可直调）。
        sess_user, is_admin = self._session_user()
        if sess_user and not is_admin:
            return {"ok": False, "msg": "仅管理员可生成测试 TIFF"}
        sub = str(req.get("subdir", "")).strip()
        if not sub:
            return {"ok": False, "msg": "未选择子目录"}
        placeholder = WEBUI_DIR / "assets" / "test_seal.tiff"
        if not placeholder.exists():
            return {"ok": False, "msg": "占位图 webui/assets/test_seal.tiff 不存在"}
        try:
            name = lib.generate_test_tiff(self._root_path(), sub, placeholder)
        except Exception as exc:
            return {"ok": False, "msg": f"生成失败：{exc.__class__.__name__}: {exc}"}
        if not name:
            return {"ok": False, "msg": "生成失败（占位图不可读）"}
        return {"ok": True, "msg": f"已生成：{name}", "name": name}

    # ---- tab3 辅助：会话 / 路径护栏 / **真出图** / 命名构造 / 本地记录 ----
    def _session_user(self) -> tuple[str, bool]:
        """当前会话 (operator, is_admin)；未登录 ⇒ ("", False)。口令与会话只存在后端。"""
        try:
            name, is_admin, _root = self._load_session()
            return (name or ""), bool(is_admin)
        except Exception:
            return "", False

    @staticmethod
    def _safe_seg(s: str) -> str:
        """压成**单段**名（丢掉路径分隔符）⇒ 请求里的 subdir/name 无法穿越出 3_Cropped_Tiff。"""
        return Path(str(s if s is not None else "").replace("\\", "/")).name.strip()

    def _subdir_guard(self, sub: str) -> dict | None:
        subs = lib.list_subdirs(self._root_path())
        if self._safe_seg(sub) not in subs:
            return {"ok": False, "msg": f"子目录不存在：{sub or '（空）'}", "subdirs": subs}
        return None

    def _tiff_src(self, sub: str, name: str) -> Path:
        return self._root_path() / lib.TIFF_DIR / self._safe_seg(sub) / self._safe_seg(name)

    # -- 出图引擎（三级回退；旧版只有 sips 一级）--
    def _png_sips(self, src: Path, dst: Path, max_edge: int) -> bool:
        """旧版同款引擎：`sips -s format png -Z <max_edge> <src> --out <dst>`（macOS 自带）。"""
        r = subprocess.run(["sips", "-s", "format", "png", "-Z", str(max_edge),
                            str(src), "--out", str(dst)], capture_output=True, timeout=90)
        return r.returncode == 0

    def _png_pillow(self, src: Path, dst: Path, max_edge: int) -> bool:
        from PIL import Image  # 可选依赖（打包态内置）
        with Image.open(str(src)) as im:
            im = im.convert("RGB")
            im.thumbnail((max_edge, max_edge))
            im.save(str(dst), "PNG")
        return True

    def _png_pymupdf(self, src: Path, dst: Path, max_edge: int) -> bool:
        try:
            import pymupdf as mu
        except Exception:
            import fitz as mu  # 旧名回退
        pm = mu.Pixmap(str(src))
        if pm.alpha or pm.n not in (1, 3):
            pm = mu.Pixmap(mu.csRGB, pm)
        if max(pm.width, pm.height) > max_edge:
            raw = pm.tobytes("png")
            import io
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as im:
                im = im.convert("RGB")
                im.thumbnail((max_edge, max_edge))
                im.save(str(dst), "PNG")
        else:
            pm.save(str(dst))
        return True

    def _make_png(self, src: Path, dst: Path, max_edge: int) -> tuple[bool, str, str]:
        """TIFF → PNG（长边 = max_edge）。只有 PNG **落盘且非空**才算「真出图」。"""
        err = "未尝试"
        for engine, fn in (("sips", self._png_sips), ("pillow", self._png_pillow),
                           ("pymupdf", self._png_pymupdf)):
            try:
                if fn(src, dst, max_edge) and dst.exists() and dst.stat().st_size > 0:
                    return True, engine, ""
                err = f"{engine}: 返回失败/空文件"
            except Exception as exc:
                err = f"{engine}: {exc.__class__.__name__}: {exc}"
            if dst.exists():
                try:
                    dst.unlink()
                except Exception:
                    pass
        return False, "", f"三级引擎均失败（末次 {err}）"

    def _thumb_file(self, src: Path, sub: str, max_edge: int) -> tuple[Path | None, str, str]:
        """缩略图/预览 PNG（带 mtime 缓存，落在 `webui/var/thumbs/`，不入库）。"""
        tag = f"thumb{max_edge}" if max_edge <= TIFF_THUMB_MAX else f"prev{max_edge}"
        dst = THUMBS_DIR / tag / self._safe_seg(sub) / f"{src.stem}.png"
        try:
            if dst.exists() and dst.stat().st_size > 0 and dst.stat().st_mtime >= src.stat().st_mtime:
                return dst, "cache", ""
            dst.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return None, "", f"缩略图缓存不可用：{exc.__class__.__name__}: {exc}"
        ok, engine, msg = self._make_png(src, dst, max_edge)
        return (dst if ok else None), engine, msg

    @staticmethod
    def _data_uri(png: Path) -> str:
        return "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode("ascii")

    def tab3_thumbs(self, req: dict | None = None) -> dict:
        """当前页缩略图（**base64 data URI** 直给前端）。

        为什么不用 `<img src=file://…>`：3_Cropped_Tiff 是**用户选定的仓外目录**，不在
        `ui/` 静态根下（pywebview 内建 http server 只服务 ui/），WKWebView 取不到 ⇒ 与旧版
        Streamlit 一致走内联 base64（旧版 `sips -Z 150` → `<img src="data:image/png;base64,…">`）。
        """
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        sub = self._safe_seg(str(req.get("subdir", "")))
        bad = self._subdir_guard(sub)
        if bad:
            return bad
        raw_names = req.get("names") or []
        if not isinstance(raw_names, list):
            return {"ok": False, "msg": "names 必须是文件名数组"}
        names = [self._safe_seg(str(n)) for n in raw_names][:200]
        try:
            size = int(req.get("size") or TIFF_THUMB_MAX)
        except Exception:
            size = TIFF_THUMB_MAX
        size = max(48, min(512, size))
        thumbs: dict[str, str] = {}
        engines: dict[str, str] = {}
        failed: dict[str, str] = {}
        for n in names:
            if not n:
                continue
            src = self._tiff_src(sub, n)
            if not src.is_file():
                failed[n] = "文件不存在"
                continue
            png, engine, msg = self._thumb_file(src, sub, size)
            if png is None:
                failed[n] = msg or "出图失败"
                continue
            try:
                thumbs[n] = self._data_uri(png)
                engines[n] = engine
            except Exception as exc:
                failed[n] = f"读图失败：{exc.__class__.__name__}: {exc}"
        return {"ok": True, "subdir": sub, "size": size, "count": len(thumbs),
                "thumbs": thumbs, "engines": engines, "failed": failed,
                "cache_dir": str(THUMBS_DIR / (f"thumb{size}" if size <= TIFF_THUMB_MAX else f"prev{size}"))}

    def tab3_preview(self, req: dict | None = None) -> dict:
        """右栏大图预览（旧版口径 `sips -Z 400`，同样内联 base64）。"""
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        sub = self._safe_seg(str(req.get("subdir", "")))
        bad = self._subdir_guard(sub)
        if bad:
            return bad
        name = self._safe_seg(str(req.get("name", "")))
        src = self._tiff_src(sub, name)
        if not name or not src.is_file():
            return {"ok": False, "msg": f"文件不存在：{name or '（空）'}"}
        try:
            size = int(req.get("size") or TIFF_PREVIEW_MAX)
        except Exception:
            size = TIFF_PREVIEW_MAX
        size = max(120, min(1600, size))
        png, engine, msg = self._thumb_file(src, sub, size)
        if png is None:
            return {"ok": False, "msg": msg or "出图失败"}
        return {"ok": True, "name": name, "size": size, "engine": engine,
                "bytes": png.stat().st_size, "data_uri": self._data_uri(png)}

    def tab3_parse(self, req: dict | None = None) -> dict:
        """文件名解析（`validator.parse_filename` 单一真源）⇒ 回填 P/C/R 与三字段。

        非标准模板 ⇒ 三字段留空、前缀留空（与旧版 `webui.py` L808–816 同口径），并给出提示。
        """
        req = req or {}
        name = self._safe_seg(str(req.get("name", "")))
        parsed = validator.parse_filename(name)
        fields = {"shiwen": parsed[3], "dynasty": parsed[4], "author": parsed[5]} if parsed \
            else {"shiwen": "", "dynasty": "", "author": ""}
        return {"ok": True, "name": name, "standard": bool(parsed), "fields": fields,
                "page": int(parsed[0]) if parsed else None,
                "col": int(parsed[1]) if parsed else None,
                "row": int(parsed[2]) if parsed else None,
                "prefix": f"P{parsed[0]}-C{parsed[1]}-R{parsed[2]}-" if parsed else "",
                "limits": {"shiwen_max": validator.SHIWEN_MAX, "author_max": validator.AUTHOR_MAX},
                "note": "" if parsed else "文件名非标准模板 ⇒ 前缀留空，请手动填写（与旧版一致）"}

    def _compose_new_name(self, old_name: str, shiwen: str, dynasty: str,
                          author: str) -> dict:
        """新文件名 = `{旧文件名解析出的 P/C/R 前缀}{释文}-{朝代}-{作者}.tiff`。

        与旧版 `webui.py` L811/L829 **同一构造**：前缀来自 `parse_filename` 的回填
        （非标准模板 ⇒ 前缀留空，提示手填）；校验一律走 `validator.validate_fields`。
        """
        parsed = validator.parse_filename(old_name)
        prefix = f"P{parsed[0]}-C{parsed[1]}-R{parsed[2]}-" if parsed else ""
        valid, msg = validator.validate_fields(shiwen, dynasty, author)
        return {
            "prefix": prefix, "standard": bool(parsed), "valid": bool(valid), "msg": msg,
            "new_name": f"{prefix}{shiwen}-{dynasty}-{author}{validator.SUFFIX}",
            "counts": {"shiwen": validator.count_chinese(shiwen),
                       "author": validator.count_chinese(author)},
            "limits": {"shiwen_max": validator.SHIWEN_MAX, "author_max": validator.AUTHOR_MAX},
        }

    def tab3_check(self, req: dict | None = None) -> dict:
        """**纯校验 + 新名预览**（无副作用）：UI 据此置灰按钮并展示错误原文。"""
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        sub = self._safe_seg(str(req.get("subdir", "")))
        bad = self._subdir_guard(sub)
        if bad:
            return bad
        old = self._safe_seg(str(req.get("name", "")))
        src = self._tiff_src(sub, old)
        if not old or not src.is_file():
            return {"ok": False, "msg": f"文件不存在：{old or '（空）'}"}
        comp = self._compose_new_name(old, str(req.get("shiwen", "")),
                                      str(req.get("dynasty", "")), str(req.get("author", "")))
        same = comp["new_name"] == old
        conflict = (not same) and (src.parent / comp["new_name"]).exists()
        if not comp["valid"]:
            reason = comp["msg"]
        elif same:
            reason = "文件名未变化"
        elif conflict:
            reason = f"同目录已存在：{comp['new_name']}"
        else:
            reason = ""
        out = {"ok": True, "subdir": sub, "old_name": old, "same": same,
               "conflict": bool(conflict), "can_rename": (reason == ""), "reason": reason,
               "cloud_log": CLOUD_LOG_STATUS, "cloud_lock": CLOUD_LOCK_STATUS, "note": CLOUD_NOTE}
        out.update(comp)
        return out

    @staticmethod
    def _append_rename_log(record: dict) -> tuple[bool, str]:
        """本地记录落盘（jsonl 追加）。**不碰任何云 API**。"""
        try:
            RENAME_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(RENAME_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            return True, str(RENAME_LOG)
        except Exception as exc:
            return False, f"{exc.__class__.__name__}: {exc}"

    def tab3_rename(self, req: dict | None = None) -> dict:
        """执行重命名（**同目录同名 ⇒ 拒**）＋ 写本地记录。

        外部依赖如实标注：腾讯文档日志 `cloud_log=not_connected`；百度网盘云盘锁
        `cloud_lock=not_connected`（旧版的 lock_file/unlock_file/append_log_record 未接入本壳）。
        """
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        sub = self._safe_seg(str(req.get("subdir", "")))
        bad = self._subdir_guard(sub)
        if bad:
            return bad
        old = self._safe_seg(str(req.get("name", "")))
        src = self._tiff_src(sub, old)
        if not old or not src.is_file():
            return {"ok": False, "msg": f"文件不存在：{old or '（空）'}", "code": "missing"}
        shiwen = str(req.get("shiwen", ""))
        dynasty = str(req.get("dynasty", ""))
        author = str(req.get("author", ""))
        comp = self._compose_new_name(old, shiwen, dynasty, author)
        if not comp["valid"]:
            return {"ok": False, "msg": comp["msg"], "code": "invalid", **comp}
        if comp["new_name"] == old:
            return {"ok": False, "msg": "文件名未变化", "code": "noop", **comp}
        dst = src.parent / comp["new_name"]
        if dst.exists():
            return {"ok": False, "msg": f"同目录已存在：{comp['new_name']}", "code": "conflict",
                    "conflict_path": str(dst), **comp}
        operator = str(req.get("operator", "")).strip() or self._session_user()[0] or "unknown"
        try:
            src.rename(dst)                    # 已先验存在性 ⇒ 绝不覆盖同名文件
        except Exception as exc:
            return {"ok": False, "msg": f"重命名失败：{exc.__class__.__name__}: {exc}",
                    "code": "rename_failed"}
        md5 = ""
        try:
            md5 = hashlib.md5(dst.read_bytes()).hexdigest()
        except Exception:
            pass
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "subdir": sub,
            "original_path": str(src),
            "old_filename": old,
            "new_filename": comp["new_name"],
            "印面释文": shiwen, "朝代": dynasty, "作者": author,
            "file_md5": md5,
            "operator": operator,
            "status": "success",
            "log_target": "local",                 # 本次记录只落本地
            "cloud_log": CLOUD_LOG_STATUS,         # 腾讯文档日志：未接入（**不得假装已同步**）
            "cloud_lock": CLOUD_LOCK_STATUS,       # 百度网盘云盘锁：未接入
        }
        log_ok, log_msg = self._append_rename_log(record)
        return {"ok": True, "old_name": old, "new_name": comp["new_name"], "new_path": str(dst),
                "record": record, "log_ok": log_ok, "log_msg": log_msg, "log_path": str(RENAME_LOG),
                "cloud_log": CLOUD_LOG_STATUS, "cloud_lock": CLOUD_LOCK_STATUS,
                "msg": ("✅ 改名完成，本地记录已写入" if log_ok
                        else f"⚠️ 文件已改名，但本地记录写入失败：{log_msg}")}

    def tab3_log(self, req: dict | None = None) -> dict:
        """本地操作记录（尾部 N 条，只读本地 jsonl）。"""
        req = req or {}
        try:
            limit = max(1, min(200, int(req.get("limit") or 20)))
        except Exception:
            limit = 20
        rows: list[dict] = []
        try:
            if RENAME_LOG.exists():
                lines = [ln for ln in RENAME_LOG.read_text(encoding="utf-8", errors="replace")
                         .splitlines() if ln.strip()]
                for ln in lines[-limit:]:
                    try:
                        rows.append(json.loads(ln))
                    except Exception:
                        rows.append({"raw": ln, "status": "unparsable"})
        except Exception as exc:
            return {"ok": False, "msg": f"读取本地记录失败：{exc.__class__.__name__}: {exc}"}
        return {"ok": True, "rows": rows, "count": len(rows), "path": str(RENAME_LOG),
                "cloud_log": CLOUD_LOG_STATUS, "cloud_lock": CLOUD_LOCK_STATUS, "note": CLOUD_NOTE}

    def shutdown(self, _req: dict | None = None) -> dict:
        """关闭窗口（native 形态专用）。"""
        if self._closer is not None:
            threading.Thread(target=self._closer, daemon=True).start()
            return {"ok": True, "msg": "窗口即将关闭"}
        return {"ok": False, "msg": "当前进程无窗口可关（应经 app.py 启动）"}

    #: 由 app.py 注入的「关窗」回调（native only）
    _closer = None


def build_api() -> FeicuiApi:
    """唯一入口：两种形态都拿同一份实例。"""
    api = FeicuiApi()
    api._closer = None
    return api
