# webui/api.py
"""「斐萃」本地电脑版 —— **js_api 桥接层**（PyWebView `js_api` 的唯一后端面）。

架构纪律（Kevin 2026-10-16，PyWebView 换壳；同日口径变更：**只保留原生窗口形态**，
不做 HTTP/端口监听）：
  * 本文件是 **逻辑编排层**，**不 import streamlit、不 import webview**、不含任何 UI 代码
    ⇒ 与 `ui/`（纯 HTML/JS）严格分层；可直接被脚本 import 做单测（见 `selftest.py`）。
  * 能力全部**复用既有实现**，不重写算法：
      - tab1  → `src/pdf_library.py`（盘点 / pymupdf 探针 / 元数据侧车）
      - 目录键 → 老工程 `server/app/naming.py`（纯 stdlib，单一真源）
      - tab2  → 老工程引擎 **子进程**
                `venv/bin/python ops/book-page-2400/render_page_2400.py --pdf … --page … --dpi 1200`
                （单页 1200dpi ≈ 64 s ⇒ 必须异步线程 + 进度推送 + 可取消）
      - tab3  → `src/pdf_library.py`（子目录 / tiff 列表 / 测试 tiff）
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

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

WEBUI_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEBUI_DIR.parent
UI_DIR = WEBUI_DIR / "ui"
VAR_DIR = WEBUI_DIR / "var"
JOBS_DIR = VAR_DIR / "jobs"
SESSION_FILE = WEBUI_DIR / ".session.json"
ENGINE_SCRIPT = REPO_ROOT / "ops" / "book-page-2400" / "render_page_2400.py"
VENV_PYTHON = REPO_ROOT / "venv" / "bin" / "python"

# 既有逻辑层（`src/*.py` 自身不得 import streamlit / webview；此处只做编排）
sys.path.insert(0, str(WEBUI_DIR))
sys.path.insert(0, str(REPO_ROOT / "server"))  # `app.naming`（纯 stdlib，无图像栈）

from src import pdf_library as lib  # noqa: E402
from src import validator  # noqa: E402

APP_NAME = "斐萃 · 本地电脑版"
APP_VERSION = "0.3.0-pywebview"
SESSION_EXPIRE_DAYS = 7
DPI_WHITELIST = (1200, 2400)
DPI_DEFAULT = 1200

# ── 用户表（**仅后端**；可被 .env 的 FEICUI_USERS 覆盖，格式 `user:pwd:admin|user,...`）──
_DEFAULT_USERS: dict[str, dict] = {
    "ji": {"pwd": "6666", "is_admin": True},
    "pan": {"pwd": "1234", "is_admin": False},
    "test": {"pwd": "test", "is_admin": False},
}


def _load_env() -> dict:
    """读 `webui/.env`（不依赖 python-dotenv，缺库也能起）。"""
    env: dict[str, str] = {}
    p = WEBUI_DIR / ".env"
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
    p = WEBUI_DIR / ".env"
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

    def attach_pusher(self, fn) -> None:
        self._push = fn

    def engine_python(self) -> str:
        return self._python

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
        return [
            self._python, str(ENGINE_SCRIPT),
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

    # ---------------- 应用信息 ----------------
    def app_info(self, _req: dict | None = None) -> dict:
        env = _load_env()
        return {
            "ok": True, "app": APP_NAME, "version": APP_VERSION,
            "engine_python": self.jobs.engine_python(),
            "engine_script": str(ENGINE_SCRIPT), "engine_script_exists": ENGINE_SCRIPT.exists(),
            "repo_root": str(REPO_ROOT), "ui_dir": str(UI_DIR),
            "dpi_whitelist": list(DPI_WHITELIST), "dpi_default": DPI_DEFAULT,
            "feicui_root_env": env.get("FEICUI_ROOT", ""),
            "log_note": "腾讯文档日志：本壳未接入（见 webui/build/README.md「未实现」）",
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
        return {"ok": True, "root": res["root"], "rows": rows, "items": meta,
                "stats": res["stats"], "probe_available": res["probe_available"],
                "dynasty_options": list(lib.DYNASTY_OPTIONS),
                "tab": lib.ORIGINAL_DIR}

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
        return {"ok": True, "root": str(root), "tab": lib.TIFF_DIR, "subdirs": subs,
                "current": cur, "files": files,
                "template": f"{validator.PREFIX}释文-朝代-作者{validator.SUFFIX}"}

    def tab3_generate_test(self, req: dict | None = None) -> dict:
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
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
