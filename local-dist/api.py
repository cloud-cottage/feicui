# local-dist/api.py
"""「斐萃」本地封装分发版 —— **js_api 桥接层**（PyWebView `js_api` 的唯一后端面）。

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
                重命名（同目录同名 ⇒ 拒）＋ **本地**操作记录（`local-dist/var/rename_log.jsonl`）、
                **OCR 试试看**（`src/ocr_rapid.py`，只读辅助：印面篆书不可用 ⇒ 返回值带
                `hint` 诚实提示，UI 原样显示）＋ **纠错建议**（`src/ocr_corrector.py`，
                默认 `suggest` 只给候选；`auto` 需前端显式传，且只改输入框、不动文件）。
                腾讯文档日志 / 百度网盘云盘锁 **未接入**：接口返回值一律带
                `cloud_log=not_connected` / `cloud_lock=not_connected`，UI 上明标。
      - 文件名模板 → `src/validator.py`
  * 所有方法**只返回 JSON 可序列化对象**且**永不抛**（本地用户机器上任何异常都要变成
    `{"ok": false, "msg": …}`，不能让桥断掉）。
  * 口令只在**后端**（本文件 / `.env`），前端只拿到 `{username, is_admin}`。
  * 进度推送：native 窗口模式下由 `app.py` 注入 `window.evaluate_js('onProgress(…)')`。

启动：
    ./venv/bin/python local-dist/app.py            # PyWebView 原生窗口（唯一形态）
    ./venv/bin/python local-dist/selftest.py       # 逻辑层直测（不依赖 GUI）
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

# ── 源码态 / 打包态（PyInstaller）路径解析 ───────────────────────────────────────────
# 打包态由 `local-dist/build/pack_main.py` 在**导入本模块之前**设好两个环境变量：
#   FEICUI_WEBUI_DIR  包内**资源根**（MEIPASS：ui/ src/ assets/ ops/ server/app/ config/）
#   FEICUI_DATA_DIR   用户机**可写目录**（日志 / var / .env / .session.json）
# 源码态两者都不设 ⇒ 行为与此前逐字一致（同目录、仓根父级）。见 `local-dist/build/README.md` §1/§5。
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

from src import paths  # noqa: E402  （目录派生/发现常量单一真源，见 src/paths.py）
from src import pdf_library as lib  # noqa: E402
from src import validator  # noqa: E402
from src import yinyuan_client as yy  # noqa: E402

APP_NAME_BASE = "斐萃 · 本地封装分发版"
APP_VERSION = "0.3.0-pywebview"
#: ── 标题/副标题 **单一真源**（改文案只改这两行；`app.py` 的窗口标题与 `ui/` 均从
#:    `app_info()` 取，HTML 里只留一份同值兜底）────────────────────────────────────
#: 口径（Kevin 2026-10-16 文案统一；2026-10-19 v1.40 三版本命名更名，见 docs/feicui.spec.md §0.5.4）：
#: **PyWebView 本地封装分发版带后缀** ⇒ `「斐萃」玺印解析任务台 · 本地封装分发版`
#: （注意「· 本地封装分发版」前有空格；旧后缀「· 本地电脑版」已被 v1.40 取代）；主标题沿用旧版
#: `local-dist/src/webui.py` L42 的
#: `APP_TITLE_IN_PAGE`（「斐萃」玺印解析任务台）＋ 本地版后缀。**其它页面不加后缀**。
#: 2026-10-20 追加：**按运行期能力**再带 `· Lite` / `· Pro`（同一份代码出两个包，
#: 标题必须一眼看出来跑的是哪个；lite 包把 rapidocr/onnxruntime 全 excludes 掉）。
APP_TITLE_BASE = "「斐萃」玺印解析任务台 · 本地封装分发版"


def ocr_capable() -> bool:
    """运行期 OCR 能力探测（**只 find_spec，不加载模型、不 import onnxruntime**）。

    真源是 `src.field_extract.ocr_capable()`（lite 包 `rapidocr` 与适配层都没有 ⇒ False）；
    它本身只用 stdlib，但**任何异常都当「不可用」**（窗口标题不许因为探测失败而挂），
    并在延迟 import 失败时退回本文件的 find_spec 探测。
    """
    try:
        from src import field_extract as _fe
        return bool(_fe.ocr_capable())
    except Exception:
        try:
            return (importlib.util.find_spec("rapidocr") is not None
                    and importlib.util.find_spec("src.ocr_rapid") is not None)
        except Exception:
            return False


def app_edition() -> str:
    """`Pro`（有 OCR 栈）/ `Lite`（无 OCR 栈）——**逐次实算**，不改环境变量、不打包注入。"""
    return "Pro" if ocr_capable() else "Lite"


def app_title() -> str:
    """当前进程的窗口/页面标题（基础串 ＋ `· Lite|Pro`）。"""
    return f"{APP_TITLE_BASE} · {app_edition()}"


def app_name() -> str:
    """当前进程的应用名/窗口标识（基础串 ＋ `· Lite|Pro`）。"""
    return f"{APP_NAME_BASE} · {app_edition()}"


#: 模块级常量＝**当前进程的实算值**（`app.py` 的 `WINDOW_TITLE`、`selftest`、`domtest` 都引用它；
#: 保持常量语义不断，两个包各自 import 时各得其所）。
APP_TITLE = app_title()
APP_NAME = app_name()
APP_SLOGAN = "数字玺印生成工具"

SESSION_EXPIRE_DAYS = 7
DPI_WHITELIST = (1200, 2400)
DPI_DEFAULT = 1200

# ── tab3：3_Cropped_Tiff 视图/缩略图/本地记录口径（数值取自旧版 `local-dist/src/webui.py`）───
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
#: 缩略图缓存（`local-dist/var/**` 不入库）＋ 本地操作记录（jsonl）
THUMBS_DIR = VAR_DIR / "thumbs"
RENAME_LOG = VAR_DIR / "rename_log.jsonl"
#: 外部依赖状态（**必须如实上报**：腾讯文档日志 / 百度网盘云盘锁 本壳尚未接入）
CLOUD_LOG_STATUS = "not_connected"
CLOUD_LOCK_STATUS = "not_connected"
CLOUD_NOTE = "日志同步（腾讯文档）/ 云盘锁暂未接入：本壳只写本地记录 local-dist/var/rename_log.jsonl"

# ── tab3：OCR 试试看（**只读辅助**：不写文件 / 不写库 / 不改名）──────────────────────
#: OCR 输入面长边。取 1024：印面篆书笔画细，150/400 太小；再往上对「均分 0.24」没有实质改善。
#: 走既有 `_thumb_file()` ⇒ 缓存落 `local-dist/var/thumbs/prev1024/<子目录>/*.png`（不入库）。
OCR_MAX_EDGE = 1024
#: **诚实提示 —— 单一真源**（UI 原样显示，不得改写成「一键得正确释文」）。
#: 口径来自实测（`ops/ocr-rapid/README.md`）：①②类印刷体可靠（0.94–0.9999）；
#: ③类**印面篆书不可用**（248 枚池：非空 60.1%、均分 0.2428；「左軍丞玺」被两引擎一致误读为「左軍丞錄」）。
OCR_HINT = ("印面篆书通用 OCR 不可靠、仅供参考：248 枚实测均分 0.2428（非空仅 60.1%），"
            "真实样本「左軍丞玺」被两引擎一致误读为「左軍丞錄」⇒ 请逐字人工核对后再重命名。")
#: 引擎标签（回给 UI 显示，别让用户以为走的是云端 API）
OCR_ENGINE_LABEL = "rapidocr-onnxruntime · PP-OCRv6 small（本地，无网络）"
#: 可直接送 OCR 的位图后缀（TIFF / 其他 ⇒ 先出 PNG，见 `_ocr_png`）
OCR_DIRECT_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
#: 能力探测缓存（**只探一次**；打包件里 rapidocr 可能整个不在 ⇒ 绝不 per-call import）
_OCR_PROBE: dict[str, object] = {"done": False, "available": False, "reason": ""}


def ocr_available() -> bool:
    """本版本**有没有** OCR 引擎（探测并缓存；缺失不抛，只回 False）。

    为什么要有这一层：阶段 1 打包件（`斐萃-s1.app`）**不收** `rapidocr` 与
    `src/ocr_rapid.py`（阶段 2/3 才收）⇒ tab3 的「OCR 试试看」在 s1 上必须**先置灰/隐藏**，
    不能等用户点下去才吃 `ImportError`（UI 上就是「点了炸」）。
    判据：`importlib.util.find_spec('rapidocr')` 有 + `src.ocr_rapid` 能 import（后者在 s1 里也没有）。
    """
    if not _OCR_PROBE["done"]:
        available, why = False, ""
        try:
            if importlib.util.find_spec("rapidocr") is None:
                why = "本版本未内置 OCR 引擎（rapidocr 未随包提供）"
            else:
                importlib.import_module("src.ocr_rapid")
                available = True
        except Exception as exc:
            why = f"OCR 引擎不可用：{exc.__class__.__name__}: {exc}"
        _OCR_PROBE.update({"done": True, "available": bool(available), "reason": why})
    return bool(_OCR_PROBE["available"])


def ocr_unavailable_note() -> str:
    """能力缺失时的**可读**原因（UI 原样显示；可用时为空串），并给出可执行的替代路径。"""
    if ocr_available():
        return ""
    why = str(_OCR_PROBE.get("reason") or "本版本未内置 OCR 引擎（rapidocr 未随包提供）")
    return f"{why} ⇒ 释文请手动填写；要自动识别请用 斐萃_pro（含 OCR）"

# ── 用户表（**仅后端**；可被 .env 的 FEICUI_USERS 覆盖，格式 `user:pwd:admin|user,...`）──
_DEFAULT_USERS: dict[str, dict] = {
    "ji": {"pwd": "6666", "is_admin": True},
    "pan": {"pwd": "1234", "is_admin": False},
    "test": {"pwd": "test", "is_admin": False},
}


def _load_env() -> dict:
    """读 `local-dist/.env`（不依赖 python-dotenv，缺库也能起）。"""
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
# tab1 一键高清化：整本（或页段）PDF → 高分辨率页图 PDF
# ============================================================
class HighResTask:
    """一次「一键高清化」任务（**单例**：同一时刻只允许一个，见 `FeicuiApi.tab1_highres_start`）。

    实跑逻辑在 `src/highres_pdf.py`（纯逻辑层）；本类只做**状态容器 + 进度推送 + 取消开关**，
    供 `tab1_highres_status` 轮询。`state ∈ {queued, running, done, failed, cancelled}`。
    """

    def __init__(self, pdf: Path, out: Path, dpi: int, page_from: int, page_to: int | None,
                 page_bytes_dir: Path | None, push=None):
        self.id = uuid.uuid4().hex[:12]
        self.pdf = pdf
        self.out = out
        self.dpi = dpi
        self.page_from = page_from
        self.page_to = page_to
        self.page_bytes_dir = page_bytes_dir
        self.cancel_event = threading.Event()
        self.state = "queued"
        self.page = 0                 # 最近完成的页号
        self.pages_total = 0          # 本次**范围内**页数（UI 进度条分母）
        self.pages_done = 0
        self.bytes = 0
        # v2：全页输出口径的计数（渲 / 修复重渲 / 跳过已达标 / 原样保留 / 输出总页数）
        self.rendered_pages = 0
        self.repaired_pages = 0       # 范围外曾高清化、位图丢失 ⇒ 按原 dpi 修复重渲的页数
        self.skipped_pages = 0
        self.passthrough_pages = 0
        self.pdf_pages_total = 0
        self.msg = "排队中"
        self.result: dict | None = None
        self.error = ""
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.finished_at = ""
        self._t0 = time.time()
        self._push = push
        self._lock = threading.Lock()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "task_id": self.id, "state": self.state, "running": self.state in ("queued", "running"),
                "page": self.page, "pages_total": self.pages_total, "pages_done": self.pages_done,
                "bytes": self.bytes, "msg": self.msg, "dpi": self.dpi,
                "rendered_pages": self.rendered_pages, "skipped_pages": self.skipped_pages,
                "repaired_pages": self.repaired_pages,
                "passthrough_pages": self.passthrough_pages,
                "pdf_pages_total": self.pdf_pages_total,
                "pdf": self.pdf.name, "out": str(self.out),
                "page_from": self.page_from, "page_to": self.page_to,
                "page_bytes_dir": str(self.page_bytes_dir) if self.page_bytes_dir else "",
                "result": self.result, "error": self.error,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "elapsed_s": round(time.time() - self._t0, 1),
            }

    def _emit(self) -> None:
        if self._push is None:
            return
        try:
            self._push({"kind": "tab1_highres", **self.snapshot()})
        except Exception:
            pass

    def on_progress(self, rec: dict) -> None:
        """`src.highres_pdf.render_pdf_to_pdf(progress_cb=…)` 的回调（**不许抛**）。"""
        with self._lock:
            self.state = "running"
            self.page = int(rec.get("page") or 0)
            self.pages_total = int(rec.get("pages_total") or self.pages_total)
            self.pages_done = int(rec.get("pages_done") or 0)
            self.bytes = int(rec.get("bytes") or 0)
            self.rendered_pages = int(rec.get("rendered") or self.rendered_pages)
            self.repaired_pages = int(rec.get("repaired") or self.repaired_pages)
            self.skipped_pages = int(rec.get("skipped") or self.skipped_pages)
            self.passthrough_pages = int(rec.get("passthrough") or self.passthrough_pages)
            self.pdf_pages_total = int(rec.get("pdf_pages_total") or self.pdf_pages_total)
            self.msg = f"{rec.get('msg') or ''}（{self.pages_done}/{self.pages_total}）"
        self._emit()

    def finish(self, result: dict) -> None:
        with self._lock:
            self.result = result
            ok = bool(result.get("ok"))
            reason = str(result.get("reason") or "")
            # v2 计数：成功/取消/失败回执都带上（旧键仍在 ⇒ 只加不删）
            for key, attr in (("rendered_pages", "rendered_pages"),
                              ("repaired_pages", "repaired_pages"),
                              ("skipped_pages", "skipped_pages"),
                              ("passthrough_pages", "passthrough_pages"),
                              ("pdf_pages_total", "pdf_pages_total")):
                if result.get(key) is not None:
                    setattr(self, attr, int(result.get(key) or 0))
            if ok:
                self.state = "done"
                self.pages_done = int(result.get("pages_done") or self.pages_done)
                self.bytes = int(result.get("bytes") or self.bytes)
                fix = (f" · 修复 {self.repaired_pages} 页（原 dpi 重渲）"
                       if self.repaired_pages else "")
                self.msg = (f"完成：{self.out.name}（已渲 {self.rendered_pages} 页 · "
                            f"跳过 {self.skipped_pages} 页（已达标）· "
                            f"原样保留 {self.passthrough_pages} 页 · "
                            f"共 {self.pdf_pages_total or '?'} 页，"
                            f"{self.bytes/1024**2:.1f} MB{fix}）")
            elif reason == "CANCELLED":
                self.state = "cancelled"
                self.pages_done = int(result.get("pages_done") or self.pages_done)
                self.msg = (f"已取消（本次已渲 {self.rendered_pages} 页 · 完成 "
                            f"{self.pages_done}/{self.pages_total or '?'} 页，进度保留可续跑）")
            else:
                self.state = "failed"
                self.error = f"{reason}: {result.get('msg') or ''}".strip(": ")
                self.msg = self.error or "失败"
            self.finished_at = datetime.now().isoformat(timespec="seconds")
        self._emit()


# ============================================================
# tab2 一键全自动：逐页「检测 → 字段(OCR) → 裁切」批处理
# ============================================================
class AutoCropTask:
    """一次「tab2 一键全自动」任务（**单例**：同一时刻只允许一个，见 `FeicuiApi.tab2_autocrop_start`）。

    实跑逻辑在 `src/autocrop.py`（纯逻辑层，每页落盘进度 / 断点续跑 / 单页失败不中断）；
    本类只做**状态容器 + 进度推送 + 取消开关**，供 `tab2_autocrop_status` 轮询。
    `state ∈ {queued, running, done, failed, cancelled}`。
    """

    def __init__(self, pdf: Path, dpi: int, page_from: int, page_to: int | None,
                 resume: bool, push=None):
        self.id = uuid.uuid4().hex[:12]
        self.pdf = pdf
        self.dpi = dpi
        self.page_from = page_from
        self.page_to = page_to
        self.resume = resume
        self.cancel_event = threading.Event()
        self.state = "queued"
        self.page = page_from
        self.pages_total = 0
        self.pages_done = 0
        self.pages_skipped = 0
        self.pages_failed = 0
        self.seals_total = 0
        self.current_page_elapsed_s = 0.0
        self.eta_s: float | None = None
        self.dir_key = ""
        self.reading_order = ""
        self.order_source = ""
        self.ocr_available: bool | None = None
        self.msg = "排队中"
        self.result: dict | None = None
        self.error = ""
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.finished_at = ""
        self._t0 = time.time()
        self._push = push
        self._lock = threading.Lock()

    def snapshot(self) -> dict:
        with self._lock:
            running = self.state in ("queued", "running")
            return {
                "task_id": self.id, "state": self.state, "running": running,
                "cancelled": bool(self.state == "cancelled"
                                  or (running and self.cancel_event.is_set())),
                "progress": {
                    "page": self.page, "pages_total": self.pages_total,
                    "pages_done": self.pages_done, "pages_skipped": self.pages_skipped,
                    "pages_failed": self.pages_failed, "seals_total": self.seals_total,
                    "current_page_elapsed_s": round(self.current_page_elapsed_s, 2),
                    "eta_s": self.eta_s},
                # 兼容直读（UI 两种取法都行：`st.pages_done` 或 `st.progress.pages_done`）
                "page": self.page, "pages_total": self.pages_total,
                "pages_done": self.pages_done, "pages_skipped": self.pages_skipped,
                "pages_failed": self.pages_failed, "seals_total": self.seals_total,
                "current_page_elapsed_s": round(self.current_page_elapsed_s, 2),
                "eta_s": self.eta_s,
                "dir_key": self.dir_key, "reading_order": self.reading_order,
                "order_source": self.order_source, "ocr_available": self.ocr_available,
                "pdf": self.pdf.name, "dpi": self.dpi,
                "page_from": self.page_from, "page_to": self.page_to, "resume": self.resume,
                "msg": self.msg, "result": self.result, "error": self.error,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "elapsed_s": round(time.time() - self._t0, 1),
            }

    def _emit(self) -> None:
        if self._push is None:
            return
        try:
            self._push({"kind": "tab2_autocrop", **self.snapshot()})
        except Exception:
            pass

    def on_progress(self, rec: dict) -> None:
        """`src.autocrop.run_autocrop(progress_cb=…)` 的回调（**不许抛**）。"""
        try:
            with self._lock:
                self.state = "running"
                self.page = int(rec.get("page") or self.page)
                self.pages_total = int(rec.get("pages_total") or self.pages_total)
                self.pages_done = int(rec.get("pages_done") or 0)
                self.pages_skipped = int(rec.get("pages_skipped") or 0)
                self.pages_failed = int(rec.get("pages_failed") or 0)
                self.seals_total = int(rec.get("seals_total") or 0)
                self.current_page_elapsed_s = float(rec.get("current_page_elapsed_s") or 0.0)
                eta = rec.get("eta_s")
                self.eta_s = None if eta is None else float(eta)
                self.dir_key = str(rec.get("dir_key") or self.dir_key)
                self.msg = f"第 {self.page}/{self.pages_total or '?'} 页 · 已裁 {self.seals_total} 枚"
            self._emit()
        except Exception:
            pass

    def finish(self, result: dict) -> None:
        with self._lock:
            self.result = result
            ok = bool(result.get("ok"))
            cancelled = bool(result.get("cancelled"))
            self.pages_total = int(result.get("pages_total") or self.pages_total)
            self.pages_done = int(result.get("pages_done") or self.pages_done)
            self.pages_skipped = int(result.get("pages_skipped") or self.pages_skipped)
            self.pages_failed = int(result.get("pages_failed") or self.pages_failed)
            self.seals_total = int(result.get("seals_total") or self.seals_total)
            self.dir_key = str(result.get("dir_key") or self.dir_key)
            self.reading_order = str(result.get("reading_order") or self.reading_order)
            self.order_source = str(result.get("order_source") or self.order_source)
            self.ocr_available = result.get("ocr_available", self.ocr_available)
            self.current_page_elapsed_s = 0.0
            self.eta_s = 0.0
            if ok and cancelled:
                self.state = "cancelled"
                self.msg = f"已取消（完成 {self.pages_done} 页 · 跳过 {self.pages_skipped} 页，进度已保存可续跑）"
            elif ok:
                self.state = "done"
                self.msg = (f"完成：裁 {self.pages_done} 页 / 跳过 {self.pages_skipped} 页 / "
                            f"失败 {self.pages_failed} 页 · 共 {self.seals_total} 枚")
            else:
                self.state = "failed"
                self.error = f"{result.get('reason') or 'ERROR'}: {result.get('msg') or ''}".strip(": ")
                self.msg = self.error or "失败"
            self.finished_at = datetime.now().isoformat(timespec="seconds")
        self._emit()


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
        # tab1 一键高清化（单例任务；见 `HighResTask` / `tab1_highres_start`）
        self._hr_lock = threading.Lock()
        self._hr_task: HighResTask | None = None
        # tab2 切图台：1200dpi 渲页很重 ⇒ 裁切串行（并发第二个请求直接拒，不排队堆内存）
        self._crop_lock = threading.Lock()
        # tab2 一键全自动（单例任务；见 `AutoCropTask` / `tab2_autocrop_start`）
        self._ac_lock = threading.Lock()
        self._ac_task: AutoCropTask | None = None
        # tab1 PDF 快速预览：**内存 LRU（最近 8 张）**，key=pdf 路径+page+dpi+max_w
        # ⇒ 来回翻页不重渲（96dpi 单页 ≈0.1 s 级，但 4.5 GB 的高清 PDF 打开/解码并不免费）
        self._pv_lock = threading.Lock()
        self._pv_cache: "OrderedDict[str, dict]" = OrderedDict()

    # ---------------- 应用信息 ----------------
    def app_info(self, _req: dict | None = None) -> dict:
        env = _load_env()
        name, is_admin = self._session_user()
        return {
            "ok": True, "app": app_name(), "version": APP_VERSION,
            "title": app_title(), "slogan": APP_SLOGAN,
            # 版本形态：**运行期实算**（Lite＝无 rapidocr；Pro＝有）——UI 顶栏/标题栏同源
            "edition": app_edition(), "ocr_capable": ocr_capable(),
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
    def _env_root_info(self) -> dict:
        """`.env` 里上次记住的 `FEICUI_ROOT` 现状（启动提示用，P5）。

        为什么单独抽出来：UI 启动时要能**明确告知**「上次的目录已不存在」，
        而旧版只把它塞进 `app_info.feicui_root_env`（纯字符串，前端无法判断真假）。
        """
        raw = str(_load_env().get("FEICUI_ROOT", "")).strip()
        if not raw:
            return {"env_root": "", "env_root_exists": False, "env_root_verified": False,
                    "env_root_msg": ""}
        p = Path(raw).expanduser()
        exists = p.is_dir()
        ok, msg = (False, "目录不存在") if not exists else lib.verify_feicui_dir(p)
        return {"env_root": str(p), "env_root_exists": bool(exists),
                "env_root_verified": bool(ok), "env_root_msg": msg}

    def session_state(self, _req: dict | None = None) -> dict:
        name, is_admin, root = self._load_session()
        if name:
            self._nav_root = root or self._nav_root
        session_root = root or self._root or ""
        # 会话里的 root 也可能已失效（同步盘卸载/改名）⇒ 一并暴露，前端不得静默进空列表
        root_exists = bool(session_root) and Path(session_root).expanduser().is_dir()
        out = {"ok": True, "logged_in": bool(name), "username": name or "",
               "is_admin": bool(is_admin), "feicui_root": session_root,
               "dir_verified": bool(root and self._root == root),
               "feicui_root_exists": root_exists,
               "home": str(Path.home())}
        out.update(self._env_root_info())
        return out

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
    #: 目录「打不开 / 看起来是空的」的成因（P2 ＋ F2）——前端必须能分辨并给可操作提示，
    #: 否则使用者只会看到一行「（无子目录）」而不知道该去挂载同步盘还是去授权。
    #: `not_dir`＝路径**存在但是文件**（F2 契约纯增量：不与 not_exist 混说）。
    BROWSE_EMPTY_REASONS = ("empty", "all_hidden", "permission", "not_exist", "not_dir")

    def browse(self, req: dict | None = None) -> dict:
        """列目录。

        * `{"home": true}` ⇒ **家目录**（P1：修复「🏠 家目录」其实只是刷新当前目录）；
        * `{"path": "~/x"}` / 绝对路径 ⇒ 列它（`expanduser`，支持 `~`）；
        * 无 `path`（且无 `home`）⇒ 旧语义＝上次浏览过的路径（**向后兼容**，不动老调用方）。
        """
        req = req or {}
        raw = str(req.get("path", "")).strip()
        want_home = bool(req.get("home"))
        home = str(Path.home())
        # F3：原「path = Path(raw or self._nav_root)」是死赋值（try 内三分支全覆写）。
        # 无 path（且无 home）⇒ 旧语义＝上次浏览过的路径，这就是这里的初值本身
        # （兼作 except 分支的展示兜底，Pyright 亦不再报 possibly-unbound）。
        path = Path(self._nav_root)
        try:
            if want_home:
                path = Path(home)
            elif raw:
                path = Path(raw).expanduser()
            path = path.resolve()
            if not path.exists():
                return {"ok": False, "reason": "not_exist", "path": str(path), "entries": [],
                        "parent": str(path.parent), "home": home, "exists": False,
                        "msg": f"目录不存在：{path}"}
            if not path.is_dir():          # F2：存在但是文件 ⇒ 单独成因，文案不冒充「不存在」
                return {"ok": False, "reason": "not_dir", "path": str(path), "entries": [],
                        "parent": str(path.parent), "home": home, "exists": True,
                        "msg": f"这是文件不是目录：{path}"}
            all_dirs = [e.name for e in path.iterdir() if e.is_dir()]
            entries = sorted(n for n in all_dirs if not n.startswith("."))
            hidden = sorted(n for n in all_dirs if n.startswith("."))
            reason = "" if entries else ("all_hidden" if hidden else "empty")
            self._nav_root = str(path)
            return {"ok": True, "path": str(path), "parent": str(path.parent),
                    "entries": entries, "is_feicui": path.name == lib.FEICUI_NAME,
                    "home": home, "reason": reason,
                    "hidden_count": len(hidden), "dir_count": len(all_dirs),
                    "is_home": str(path) == home}
        except PermissionError:
            return {"ok": False, "reason": "permission", "path": str(path), "entries": [],
                    "parent": str(path.parent), "home": home, "need_auth": True,
                    "msg": f"无权限访问该目录：{path}"
                           "（macOS 需在「系统设置 → 隐私与安全性 → 文件与文件夹」授权）"}
        except Exception as exc:
            return {"ok": False, "reason": "error", "entries": [], "path": raw,
                    "msg": f"{exc.__class__.__name__}: {exc}"}

    def _find_roots(self) -> list[str]:
        home = Path.home()
        roots = [str(home / n) for n in ("Downloads", "Documents", "Desktop")]
        roots += [str(r) for r in paths.cloud_storage_roots()]   # F1：云盘根单一真源在 paths
        roots.append("/Volumes")
        roots.append(str(home))
        return roots

    def find_feicui_dirs(self, req: dict | None = None) -> dict:
        """自动发现本机所有**通过校验**的 `feicui` 目录（P4）。

        扫 `~`、`~/Downloads`、`~/Documents`、`~/Desktop`、`~/Library/CloudStorage/*`、
        `/Volumes/*`，深度 ≤ `max_depth`（默认 4）；跳过 `FIND_SKIP` 与隐藏目录，
        符号链接**按 realpath 去重**防回环。返回 candidates（按 mtime 倒序）+ 扫描读数。
        """
        req = req or {}
        max_depth = int(req.get("max_depth") or 4)
        timeout_s = float(req.get("timeout_s") or 8.0)
        roots = [str(r) for r in (req.get("roots") or self._find_roots())]
        # 展开通配（`/Volumes/*`、`~/Library/CloudStorage/*` 这类带 * 的根）
        expanded: list[str] = []
        for r in roots:
            rp = Path(r).expanduser()
            if any(ch in str(rp) for ch in "*?["):
                expanded.extend(sorted(str(p) for p in Path(rp.anchor or "/").glob(str(rp.relative_to(rp.anchor)))))
            else:
                expanded.append(str(rp))
        roots = expanded
        t0 = time.time()
        deadline = t0 + timeout_s
        visited: set[str] = set()
        candidates: list[dict] = []
        seen: set[str] = set()
        skipped: list[dict] = []
        scanned = 0
        truncated = False
        for root in roots:
            if time.time() > deadline:
                truncated = True
                break
            rp = Path(root)
            if not rp.is_dir():
                continue
            stack: list[tuple[Path, int]] = [(rp, 0)]
            while stack:
                cur, dep = stack.pop()
                if time.time() > deadline:
                    truncated = True
                    break
                try:
                    key = str(cur.resolve())
                except OSError:
                    continue
                if key in visited:          # 符号链接回环 / 重复根 ⇒ 不重复走
                    continue
                visited.add(key)
                scanned += 1
                try:
                    with os.scandir(cur) as it:
                        items = list(it)
                except (PermissionError, OSError) as exc:
                    skipped.append({"path": str(cur), "why": exc.__class__.__name__})
                    continue
                for e in items:
                    try:
                        if not e.is_dir():
                            continue
                    except OSError:
                        continue
                    nm = e.name
                    if nm.startswith(".") or nm in paths.FIND_SKIP:   # F1：跳过名单单一真源
                        continue
                    child = Path(e.path)
                    if nm == lib.FEICUI_NAME:
                        try:
                            rpath = str(child.resolve())
                        except OSError:
                            continue
                        if rpath in seen:
                            continue
                        ok, msg = lib.verify_feicui_dir(child)
                        if ok:
                            seen.add(rpath)
                            try:
                                mt = child.stat().st_mtime
                            except OSError:
                                mt = 0.0
                            candidates.append({
                                "path": rpath, "name": nm, "verified": True, "msg": msg,
                                "mtime": mt,
                                "mtime_iso": datetime.fromtimestamp(mt).isoformat(timespec="seconds")
                                if mt else "",
                            })
                        elif bool(req.get("include_bad")):
                            seen.add(rpath)
                            candidates.append({"path": rpath, "name": nm, "verified": False,
                                               "msg": msg, "mtime": 0.0, "mtime_iso": ""})
                        continue               # feicui 的子目录里不会有 feicui，不再下钻
                    if dep + 1 <= max_depth:
                        stack.append((child, dep + 1))
        candidates.sort(key=lambda c: (-float(c.get("mtime") or 0), c["path"]))
        return {"ok": True, "roots": roots, "max_depth": max_depth,
                "candidates": candidates, "count": len(candidates),
                "scanned_dirs": scanned, "elapsed_s": round(time.time() - t0, 3),
                "timeout_s": timeout_s, "truncated": truncated,
                "skipped_count": len(skipped), "skipped": skipped[:10]}

    def verify_dir(self, req: dict | None = None) -> dict:
        """校验并（通过后）记住 feicui 根：`src/pdf_library.verify_feicui_dir` 逐字复用。"""
        req = req or {}
        path = str(req.get("path", "")).strip()
        if not path:
            return {"ok": False, "msg": "未指定目录"}
        target = Path(path).expanduser()
        ok, msg = lib.verify_feicui_dir(target)
        if not ok:
            # P6：把 verify 的**原始 msg** 原样带回（前端要显示原文，不许改写/吞咽），
            # 并标出「缺标准子目录 / 根目录有文件」⇒ 前端引导到「🛠 创建标准子目录」
            missing = bool(target.is_dir() and target.name == lib.FEICUI_NAME
                           and ("必须恰好包含" in msg or "不能包含文件" in msg))
            return {"ok": False, "msg": msg, "path": str(target), "raw_msg": msg,
                    "need_subdirs": missing, "exists": target.is_dir()}
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
        meta = []
        for r in res["rows"]:
            dk, dk_src = lib.resolve_dir_key(Path(r.path), book={"book_name": r.book_name})
            meta.append({"filename": r.filename, "dynasty": r.dynasty or "", "author": r.author or "",
                         "notes": r.notes or "", "page_count": r.page_count,
                         "scan_dpi": r.scan_dpi, "probe_error": r.probe_error,
                         "reading_order": r.reading_order or "",
                         "true_dpi": r.true_dpi,
                         "book_name": r.book_name or "",
                         "dir_key": dk, "dir_key_source": dk_src,
                         "updated_at": r.updated_at})
        # 朝代下拉值域：**优先 yinyuan**（/dynasties 的 items[].value，24h 缓存），
        # 拿不到（无 key / 无网 / 缓存空）⇒ 回落本地 15 枚举（`lib.DYNASTY_OPTIONS`）。
        # ⚠️ 这里**只读缓存、不打网络**：tab1 扫描主流程不许被 8 s 超时卡住；
        #    联网刷新在 `yinyuan_status` / `yinyuan_connect` 的后台预热线程里做。
        dyn = self._yy_dynasty_safe()
        return {"ok": True, "root": res["root"], "rows": rows, "items": meta,
                "stats": res["stats"], "probe_available": res["probe_available"],
                "dynasty_options": dyn["items"], "dynasty_source": dyn["source"],
                "reading_order_options": list(lib.READING_ORDER_OPTIONS),
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
        """保存书级元数据（含 **book_name**）⇒ 书名变了就**自动改名迁移**旧目录。

        返回 `{ok, msg, book_name, dir_key, dir_key_source, migration?}`；`migration` ＝
        `{ok, msg, from, to, files, bytes, status}`（只在本次书名变化时出现，UI 据此提示
        「目录已从 X 迁移到 Y（N 件 / M MB）」或红条失败原因）。

        旧目录键的取法（不读已退场的 `config/book_dir_keys.json`）：
          ① `pdf_meta.<书>.dir_key_migrations` 最后一条的 `to`（且盘上确实存在）⇒ 说明上轮迁到那儿；
          ② `3_Cropped_Tiff/<键>/_fields.json` 的 `pdf_name` 指向本 PDF ⇒ 切图 sidecar 自带来源；
          ③ 文件名主名（＝未确认书名时的新产物目录）。
        """
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        filename = str(req.get("filename", "")).strip()
        if not filename:
            return {"ok": False, "msg": "未指定文件"}
        has_book_name = "book_name" in req
        try:
            prev = (lib.load_meta().get("books") or {}).get(filename) or {}
        except Exception:
            prev = {}
        try:
            ok, msg = lib.update_book_meta(
                filename,
                dynasty=req.get("dynasty"),
                author=req.get("author"),
                notes=req.get("notes"),
                reading_order=req.get("reading_order"),
                # 只有**请求里带了**该键才动它（缺键＝不改；空串＝清空 ⇒ 回落页面尺寸推算）
                true_dpi=(req.get("true_dpi") if "true_dpi" in req else None),
                # 同上：缺键＝不改书名；空串＝清空（目录键回落文件名）
                book_name=(req.get("book_name") if has_book_name else None),
            )
        except Exception as exc:
            return {"ok": False, "msg": f"保存失败：{exc.__class__.__name__}: {exc}"}
        if not ok:
            return {"ok": False, "msg": msg}

        root = self._root_path()
        pdf = root / lib.ORIGINAL_DIR / filename
        if not pdf.is_file():
            pdf = self._resolve_pdf(filename) or pdf
        new_key, new_src = lib.resolve_dir_key(pdf, root=root)
        out: dict = {"ok": True, "msg": msg, "book_name": lib.validate_book_name(
            req.get("book_name"))[1] or "", "dir_key": new_key, "dir_key_source": new_src}

        if has_book_name:
            prev_name = lib.validate_book_name(prev.get("book_name"))[1] or ""
            now_name = out["book_name"]
            if prev_name != now_name:
                old_key = self._old_dir_key(filename, prev)
                if old_key and old_key != new_key:
                    m_ok, m_msg, m_stats = lib.migrate_dir_key(
                        root, old_key, new_key, book_key=filename)
                    out["migration"] = {
                        "ok": bool(m_ok), "msg": m_msg, "from": old_key, "to": new_key,
                        "files": int(m_stats.get("files") or 0),
                        "bytes": int(m_stats.get("bytes") or 0),
                        "status": m_stats.get("status") or "",
                    }
                    out["msg"] = (msg if m_ok else f"{msg}（目录迁移未完成：{m_msg}）")
        return out

    def _old_dir_key(self, filename: str, prev: dict | None = None) -> str:
        """本书**旧目录键**（迁移用；**不读** `config/book_dir_keys.json`）。见 `tab1_save_meta`。"""
        root = self._root_path()
        try:
            rows = (prev or {}).get("dir_key_migrations") or []
            if isinstance(rows, list):
                for row in reversed(rows):
                    to = str((row or {}).get("to") or "").strip()
                    if to and (root / lib.TIFF_DIR / to).is_dir():
                        return to
            found = lib.find_legacy_dir_key(root, root / lib.ORIGINAL_DIR / filename)
            if found:
                return found
        except Exception:
            pass
        return Path(filename).stem

    # ---------------- tab1 一键高清化（Phase A：后端与契约；UI 另单）----------------
    #: dpi 白名单（Kevin 2026-10-20 补充口径）：**只三档**，默认 1200。
    #: ⚠️ 1200 的 PNG **比 600 更小**（印谱实测 13.3 MB vs 15.5 MB/页）—— 别"优化"成 600。
    HIGHRES_DPI_ALLOWED = (300, 600, 1200)
    HIGHRES_DPI_DEFAULT = 1200

    def _src_module(self, name: str):
        """延迟 import 逻辑层模块（`src/highres_pdf|seal_detect|seal_crop`）。

        延迟的理由：这几个模块在 import 期就要 `pymupdf / cv2 / numpy / tifffile`；
        放模块顶部会让**整个 app 起不来**（也让只测编排的 selftest 变重）。
        """
        try:
            mod = importlib.import_module(f"src.{name}")
            return mod, None
        except Exception as exc:
            return None, {"ok": False, "reason": "DEPS_MISSING",
                          "msg": f"逻辑层 {name} 不可用：{exc.__class__.__name__}: {exc}"}

    def _resolve_pdf(self, raw: str | None) -> Path | None:
        """PDF 定位（宽容）：绝对/相对路径 ⇒ 原样；纯文件名 ⇒ 依次找 `1_Original_PDF`、
        `2_HighRes_PDF` 顶层、`2_HighRes_PDF/<目录键>/`（切图台的源就是高清 PDF）。"""
        name = str(raw or "").strip()
        if not name:
            return None
        p = Path(name).expanduser()
        if p.is_file():
            return p
        if p.is_absolute():
            return None
        root = self._root_path()
        cands = [root / lib.ORIGINAL_DIR / name, root / lib.HIGHRES_DIR / name]
        try:
            cands += sorted((root / lib.HIGHRES_DIR).glob(f"*/{name}"))
        except Exception:
            pass
        for c in cands:
            if c.is_file():
                return c
        return None

    def tab1_highres_start(self, req: dict | None = None) -> dict:
        """启动「一键高清化」：源 PDF ⇒ `2_HighRes_PDF/<目录键>/<书名>-HighRes.pdf`（后台线程）。

        契约：`{pdf, dpi=1200, page_from, page_to, keep_page_pngs=true, overwrite=false}`
        ⇒ `{ok, task_id, out, dpi, pages_total?, note}`；已运行 ⇒ `{ok:false, reason:'BUSY'}`。
        **1100 页级的书 ≈ 6 s/页**（本机实测）⇒ 一律异步，UI 轮询 `tab1_highres_status`。

        v2 口径（Zang 定，见 `src/highres_pdf.py` 模块 docstring）：
        * 输出 PDF **恒含源 PDF 全部页**（第 i 页 ≡ 源第 i 页，页码锚定，供 tab2 按页索引切图）；
          `page_from/page_to` 只决定**哪些页渲高清**，范围外的页要么嵌已存高清位图（曾做过），
          要么 `insert_pdf` 原样复制（从未做过的 ⇒ 不重渲、不降质、保留文字层）；
        * **可反复实施**：页级 dpi 登记表（进度 schema v2）＋ 位图可得性
          （页缓存 → 旧 out_pdf 同页 → 重渲）⇒ 已达标页跳过不重做，`rendered_pages` 为 0 也算成功；
        * **范围外曾高清化的页绝不降级**：位图丢了（缓存/旧件都没了）⇒ 按 unit 记录的 dpi
          **修复重渲**，计入 `repaired_pages`（缺失档位记录才回落本次 dpi，回执 `note` 标明）；
          计数恒闭合 `rendered + repaired + skipped + passthrough == pdf_pages_total`；
        * 状态/回执新增 `rendered_pages` / `repaired_pages` / `skipped_pages` / `passthrough_pages` /
          `pdf_pages_total`（旧键全保留）；`pages_total` 仍是**本次范围内**页数（进度条分母）；
        * `overwrite=true` ⇒ 先清 out_pdf ＋ 进度 ⇒ 全量重渲（默认是续跑/增量）。
        """

        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        pdf = self._resolve_pdf(req.get("pdf") or req.get("filename") or req.get("name"))
        if pdf is None:
            return {"ok": False, "reason": "PDF_NOT_FOUND",
                    "msg": f"找不到 PDF：{req.get('pdf') or req.get('filename') or ''!r}"
                           f"（可给绝对路径，或 1_Original_PDF 下的文件名）"}
        try:
            dpi = int(req.get("dpi") or self.HIGHRES_DPI_DEFAULT)
        except Exception:
            return {"ok": False, "reason": "BAD_DPI", "dpi": req.get("dpi"),
                    "allowed": list(self.HIGHRES_DPI_ALLOWED), "msg": "dpi 必须是整数"}
        if dpi not in self.HIGHRES_DPI_ALLOWED:
            return {"ok": False, "reason": "BAD_DPI", "dpi": dpi,
                    "allowed": list(self.HIGHRES_DPI_ALLOWED),
                    "msg": f"dpi 只支持 {list(self.HIGHRES_DPI_ALLOWED)}（默认 "
                           f"{self.HIGHRES_DPI_DEFAULT}；1200 的 PNG 反而比 600 小，别降档）"}
        try:
            page_from = int(req.get("page_from") or 1)
            raw_to = req.get("page_to")
            page_to = None if raw_to in (None, "") else int(raw_to)
        except Exception:
            return {"ok": False, "reason": "BAD_RANGE", "msg": "page_from / page_to 必须是整数"}
        if page_from < 1 or (page_to is not None and page_to < page_from):
            return {"ok": False, "reason": "BAD_RANGE",
                    "msg": f"页区间不合法：{page_from}–{page_to}"}

        keep_pngs = bool(req.get("keep_page_pngs", True))
        dir_key = self._dir_key_of(pdf.name)
        out_dir = self._root_path() / lib.HIGHRES_DIR / dir_key
        out_pdf = out_dir / f"{pdf.stem}-HighRes.pdf"
        page_bytes_dir = (VAR_DIR / "highres_pages" / dir_key / pdf.stem) if keep_pngs else None

        with self._hr_lock:                       # 单例：查-建 在同一把锁里，避免双起
            cur = self._hr_task
            if cur is not None and cur.state in ("queued", "running"):
                return {"ok": False, "reason": "BUSY", "task_id": cur.id,
                        "msg": f"已有高清化任务在跑（{cur.pages_done}/{cur.pages_total or '?'} 页）",
                        "status": cur.snapshot()}
            hr, err = self._src_module("highres_pdf")
            if err:
                return err
            if bool(req.get("overwrite")):        # 显式重来：清产物与进度（默认是**续跑**）
                for p in (out_pdf, Path(str(out_pdf) + ".progress.json")):
                    try:
                        if p.is_file():
                            p.unlink()
                    except Exception:
                        pass
            task = HighResTask(pdf, out_pdf, dpi, page_from, page_to, page_bytes_dir,
                               push=self.jobs._push)
            self._hr_task = task
            threading.Thread(target=self._highres_run, args=(task, hr), daemon=True,
                             name=f"highres-{task.id}").start()

        return {"ok": True, "task_id": task.id, "out": str(out_pdf), "dpi": dpi,
                "page_from": page_from, "page_to": page_to,
                "keep_page_pngs": keep_pngs,
                "page_bytes_dir": str(page_bytes_dir) if page_bytes_dir else "",
                "msg": "已开始高清化（后台线程，UI 不阻塞）",
                "note": "≈6 s/页（本机实测）；进度见 tab1_highres_status / onProgress(kind=tab1_highres)"}

    def _highres_run(self, task: HighResTask, hr) -> None:
        """后台线程体：跑逻辑层 ⇒ 把结果交回 `task.finish`（**不许抛出去**）。"""
        try:
            res = hr.render_pdf_to_pdf(
                task.pdf, task.out, dpi=task.dpi,
                page_from=task.page_from, page_to=task.page_to,
                page_bytes_dir=task.page_bytes_dir,
                progress_cb=task.on_progress, cancel_event=task.cancel_event,
                size_limit_bytes=int(getattr(hr, "DEFAULT_SIZE_LIMIT_BYTES", 15 * 1024 ** 3)),
            )
        except Exception as exc:
            res = {"ok": False, "reason": "ERROR", "msg": f"{exc.__class__.__name__}: {exc}",
                   "pages_done": task.pages_done}
        task.finish(res)

    def tab1_highres_status(self, _req: dict | None = None) -> dict:
        """轮询状态：`{running, page, pages_total, pages_done, bytes, msg, result, …}`。"""
        task = self._hr_task
        if task is None:
            return {"ok": True, "running": False, "state": "idle", "page": 0, "pages_total": 0,
                    "pages_done": 0, "bytes": 0, "msg": "空闲（未跑过高清化）", "result": None}
        return {"ok": True, **task.snapshot()}

    def tab1_highres_cancel(self, _req: dict | None = None) -> dict:
        """请求取消（当前页渲完后停；**进度与页缓存保留**，可续跑）。"""
        task = self._hr_task
        if task is None or task.state not in ("queued", "running"):
            return {"ok": False, "reason": "IDLE", "msg": "没有在跑的高清化任务"}
        task.cancel_event.set()
        return {"ok": True, "task_id": task.id,
                "msg": f"已请求取消（完成 {task.pages_done}/{task.pages_total or '?'} 页，进度保留可续跑）"}

    # ---------------- tab1 PDF 快速预览（低清缩略；先看清内容再定「从第几页开始高清化」）----------------
    #: 预览 dpi：**一律低清**（96 左右）。**绝不用 1200dpi 渲整页**（≈6 s/页、吃 GB 内存）。
    PREVIEW_DPI_DEFAULT = 96
    PREVIEW_DPI_MIN, PREVIEW_DPI_MAX = 24, 200   # 下限 36⇒24：批量缩略图 24dpi 也够看排版
    PREVIEW_MAX_W_DEFAULT = 760
    PREVIEW_CACHE_SIZE = 24              # 内存 LRU：最近 24 张（8⇒24：批量一屏最多 10 张，与单页共池）
    #: 批量预览（一「屏」1–10 张，2 行 × 5 列）：小图 max_w 240 ⇒ 72dpi 下单页 <0.1s、整屏 <1.5s。
    PREVIEW_BATCH_COUNT_DEFAULT = 10
    PREVIEW_BATCH_COUNT_MAX = 10         # 单屏上限 10 页（用户裁定）
    PREVIEW_BATCH_MAX_W_DEFAULT = 240

    @staticmethod
    def _pv_fitz():
        """PyMuPDF 延迟取（`pymupdf` 新名优先，回落老 `fitz`）；取不到 ⇒ 结构化错误，不抛。"""
        for name in ("pymupdf", "fitz"):
            try:
                return importlib.import_module(name), None
            except Exception:
                continue
        return None, {"ok": False, "reason": "RENDER_FAILED",
                      "msg": "缺少 PyMuPDF（pymupdf），无法渲染预览"}

    def _pv_cache_get(self, key: str) -> dict | None:
        with self._pv_lock:
            hit = self._pv_cache.get(key)
            if hit is not None:
                self._pv_cache.move_to_end(key)
            return hit

    def _pv_cache_put(self, key: str, val: dict) -> None:
        with self._pv_lock:
            self._pv_cache[key] = val
            self._pv_cache.move_to_end(key)
            while len(self._pv_cache) > self.PREVIEW_CACHE_SIZE:
                self._pv_cache.popitem(last=False)      # 淘汰最久未用

    def tab1_preview(self, req: dict | None = None) -> dict:
        """tab1 单页低清预览：`{pdf, page=1, dpi=96, max_w=760}` ⇒ base64 PNG。

        契约：`{ok, page, total, png_b64, px_w, px_h, page_mm_w, page_mm_h, dpi, dpi_used,
        cached, elapsed_s}`；失败一律**结构化**（`PDF_NOT_FOUND` / `PAGE_OUT_OF_PDF` /
        `RENDER_FAILED`），**绝不抛 500 / 不炸桥**。dpi 夹紧到 24–200（超范围不报错）；
        宽度超过 `max_w` ⇒ 降低**有效 dpi** 等比缩（只渲一次，比「先渲大图再缩」省内存）；
        缓存与 `tab1_preview_batch` **共池**（同 key 口径，容量见 `PREVIEW_CACHE_SIZE`）。
        """
        t0 = time.perf_counter()
        req = req or {}
        raw = req.get("pdf") or req.get("filename") or req.get("name")
        pdf = self._resolve_pdf(raw)
        if pdf is None:
            return {"ok": False, "reason": "PDF_NOT_FOUND", "page": req.get("page"),
                    "msg": f"找不到 PDF：{str(raw or '')!r}"
                           f"（可给绝对路径，或 1_Original_PDF 下的文件名）"}
        raw_page = req.get("page")
        if raw_page in (None, ""):
            page = 1
        else:
            try:
                page = int(raw_page)
            except Exception:
                page = 1
        try:
            dpi = int(req.get("dpi") or self.PREVIEW_DPI_DEFAULT)
        except Exception:
            dpi = self.PREVIEW_DPI_DEFAULT
        dpi = max(self.PREVIEW_DPI_MIN, min(self.PREVIEW_DPI_MAX, dpi))   # 夹紧，不报错
        try:
            max_w = int(req.get("max_w") or self.PREVIEW_MAX_W_DEFAULT)
        except Exception:
            max_w = self.PREVIEW_MAX_W_DEFAULT
        max_w = max(200, min(2400, max_w))

        key = f"{pdf}|{page}|{dpi}|{max_w}"
        hit = self._pv_cache_get(key)
        if hit is not None:
            return {**hit, "cached": True,
                    "elapsed_s": round(time.perf_counter() - t0, 3)}

        fitz, ferr = self._pv_fitz()
        if fitz is None:
            return {**(ferr or {}), "page": page}
        try:
            doc = fitz.open(str(pdf))
        except Exception as exc:
            return {"ok": False, "reason": "RENDER_FAILED", "page": page,
                    "msg": f"打开 PDF 失败：{exc.__class__.__name__}: {exc}"}
        try:
            total = int(doc.page_count)
            if page < 1 or page > total:
                return {"ok": False, "reason": "PAGE_OUT_OF_PDF", "page": page,
                        "total": total, "msg": f"第 {page} 页超出范围（本书共 {total} 页）"}
            pg = doc[page - 1]
            rect = pg.rect
            mm_w = round(rect.width / 72.0 * 25.4, 1)
            mm_h = round(rect.height / 72.0 * 25.4, 1)
            dpi_used = float(dpi)
            if rect.width > 0 and rect.width * dpi / 72.0 > max_w:
                dpi_used = max(float(self.PREVIEW_DPI_MIN), max_w * 72.0 / rect.width)
            # ⚠️ 本机 PyMuPDF 的 `get_pixmap(dpi=…)` 只吃 **int**（float ⇒ fz_pixmap_xres_set
            #    TypeError）⇒ 向下取整（保证宽度不超 max_w）。
            dpi_used = float(max(self.PREVIEW_DPI_MIN, int(dpi_used)))
            pix = pg.get_pixmap(dpi=int(dpi_used), alpha=False, colorspace=fitz.csRGB)
            png = pix.tobytes("png")
            px_w, px_h = int(pix.width), int(pix.height)
        except Exception as exc:
            return {"ok": False, "reason": "RENDER_FAILED", "page": page,
                    "msg": f"渲染第 {page} 页失败：{exc.__class__.__name__}: {exc}"}
        finally:
            try:
                doc.close()
            except Exception:
                pass

        out = {"ok": True, "page": page, "total": total,
               "png_b64": base64.b64encode(png).decode("ascii"),
               "px_w": px_w, "px_h": px_h,
               "page_mm_w": mm_w, "page_mm_h": mm_h,
               "dpi": dpi, "dpi_used": round(dpi_used, 1),
               "pdf": str(pdf), "cached": False}
        self._pv_cache_put(key, dict(out))
        return {**out, "elapsed_s": round(time.perf_counter() - t0, 3)}

    def tab1_preview_batch(self, req: dict | None = None) -> dict:
        """tab1 批量低清预览（一「屏」最多 10 张）：`{pdf, page_from=1, count=10, dpi=72, max_w=240}`。

        契约：`{ok, total, start_page, count, count_returned,
        pages:[{page, png_b64, px_w, px_h, dpi, dpi_used, cached}], dpi, max_w, cached,
        elapsed_s}`。与 `tab1_preview` **共享同一 LRU 池**（key 同口径 `pdf|page|dpi|max_w`，
        单页渲过的页批量直接命中、反之亦然）；窗口越界**自动截到 total**（不足处**不补占位**，
        `count_returned` 反映实际张数；`page_from` 整个越出 ⇒ 空列表）；失败一律**结构化**
        （`PDF_NOT_FOUND` / `RENDER_FAILED`），**绝不抛**。count 夹紧 1–10、dpi 夹紧 24–200
        （超范围不报错）。逐页低 dpi 渲染（**绝不用 1200dpi 渲整页**）。
        """
        t0 = time.perf_counter()
        req = req or {}
        raw = req.get("pdf") or req.get("filename") or req.get("name")
        pdf = self._resolve_pdf(raw)
        if pdf is None:
            return {"ok": False, "reason": "PDF_NOT_FOUND", "page_from": req.get("page_from"),
                    "msg": f"找不到 PDF：{str(raw or '')!r}"
                           f"（可给绝对路径，或 1_Original_PDF 下的文件名）"}
        try:
            page_from = int(req.get("page_from") or 1)
        except Exception:
            page_from = 1
        page_from = max(1, page_from)
        raw_count = req.get("count")
        if raw_count in (None, ""):
            raw_count = self.PREVIEW_BATCH_COUNT_DEFAULT
        try:
            count = int(raw_count)                           # 0/负数照收，下面真夹紧（1–10）
        except Exception:
            count = self.PREVIEW_BATCH_COUNT_DEFAULT         # 非数字 ⇒ 默认
        count = max(1, min(self.PREVIEW_BATCH_COUNT_MAX, count))     # 单屏上限 10
        try:
            dpi = int(req.get("dpi") or self.PREVIEW_DPI_DEFAULT)
        except Exception:
            dpi = self.PREVIEW_DPI_DEFAULT
        dpi = max(self.PREVIEW_DPI_MIN, min(self.PREVIEW_DPI_MAX, dpi))   # 夹紧，不报错
        try:
            max_w = int(req.get("max_w") or self.PREVIEW_BATCH_MAX_W_DEFAULT)
        except Exception:
            max_w = self.PREVIEW_BATCH_MAX_W_DEFAULT
        max_w = max(80, min(2400, max_w))

        fitz, ferr = self._pv_fitz()
        if fitz is None:
            return {**(ferr or {}), "page_from": page_from}
        try:
            doc = fitz.open(str(pdf))
        except Exception as exc:
            return {"ok": False, "reason": "RENDER_FAILED", "page_from": page_from,
                    "msg": f"打开 PDF 失败：{exc.__class__.__name__}: {exc}"}
        pages: list[dict] = []
        try:
            total = int(doc.page_count)
            for page in range(page_from, min(total, page_from + count - 1) + 1):
                if page < 1:
                    continue
                key = f"{pdf}|{page}|{dpi}|{max_w}"       # 与单页端点**同 key** ⇒ 同一缓存池
                hit = self._pv_cache_get(key)
                if hit is not None:
                    pages.append({**hit, "cached": True})
                    continue
                try:
                    pg = doc[page - 1]
                    rect = pg.rect
                    dpi_used = float(dpi)
                    if rect.width > 0 and rect.width * dpi / 72.0 > max_w:
                        dpi_used = max(float(self.PREVIEW_DPI_MIN), max_w * 72.0 / rect.width)
                    dpi_used = float(max(self.PREVIEW_DPI_MIN, int(dpi_used)))
                    pix = pg.get_pixmap(dpi=int(dpi_used), alpha=False, colorspace=fitz.csRGB)
                    entry = {"page": page, "total": total,
                             "png_b64": base64.b64encode(pix.tobytes("png")).decode("ascii"),
                             "px_w": int(pix.width), "px_h": int(pix.height),
                             "dpi": dpi, "dpi_used": round(dpi_used, 1), "pdf": str(pdf)}
                except Exception as exc:
                    return {"ok": False, "reason": "RENDER_FAILED", "page_from": page_from,
                            "total": total, "pages": pages, "count_returned": len(pages),
                            "msg": f"渲染第 {page} 页失败：{exc.__class__.__name__}: {exc}",
                            "elapsed_s": round(time.perf_counter() - t0, 3)}
                self._pv_cache_put(key, dict(entry))
                pages.append({**entry, "cached": False})
        finally:
            try:
                doc.close()
            except Exception:
                pass

        out = {"ok": True, "total": total, "start_page": page_from, "count": count,
               "count_returned": len(pages), "pages": pages,
               "dpi": dpi, "max_w": max_w, "pdf": str(pdf),
               "cached": bool(pages) and all(p["cached"] for p in pages)}
        return {**out, "elapsed_s": round(time.perf_counter() - t0, 3)}

    # ---------------- tab2：2_HighRes_PDF ----------------
    def _dir_key_for(self, pdf) -> tuple[str, str]:
        """目录键**单一入口**：tab1 人工确认书名（`manual`）优先，否则文件名（`filename-fallback`）。

        口径真源＝`src/pdf_library.resolve_dir_key`（**不再读** `config/book_dir_keys.json`）。
        """
        return lib.resolve_dir_key(pdf, root=self._root_path())

    def _dir_key_of(self, pdf_name: str) -> str:
        """按 PDF 名取目录键（tab1 一键高清化的落点用）；取不到 ⇒ 文件名主名。"""
        pdf = self._resolve_pdf(pdf_name) or Path(str(pdf_name))
        return self._dir_key_for(pdf)[0]

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

    def tab2_list_sources(self, _req: dict | None = None) -> dict:
        """切图台的**源列表**：`2_HighRes_PDF/**/*.pdf`（递归）。

        ⇒ `{ok, dir, items:[{name, rel, path, dir_key, dir_key_source, bytes, size_mb,
        mtime, pages}], count, note}`。

        口径：
          * 目录键＝**tab1 人工确认的书名**（`src/pdf_library.resolve_dir_key`）；未确认 ⇒
            文件名主名并标 `dir_key_source='filename-fallback'`（UI 提示「建议去 tab1 确认书名」）；
            **不再读** `config/book_dir_keys.json`（ISBN 命名退场）；
          * `in_dir` ＝ 该 PDF 实际所在的 `2_HighRes_PDF/<子目录>/`（可能是旧目录键，仅供诊断）；
          * 页数用 pymupdf **惰性**打开取 `page_count`，打不开/无库 ⇒ `null`（**不抛**）；
          * 结构化返回，任何异常都变成 `{ok:false, msg}`（桥不许断）。
        """
        miss = self._need_root()
        if miss:
            return miss
        root = self._root_path()
        base = root / lib.HIGHRES_DIR
        try:
            files = (sorted((p for p in base.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"),
                            key=lambda p: str(p).lower()) if base.is_dir() else [])
        except Exception as exc:
            return {"ok": False, "reason": "SCAN_FAILED", "dir": str(base),
                    "msg": f"扫描 2_HighRes_PDF 失败：{exc.__class__.__name__}: {exc}"}

        items: list[dict] = []
        for p in files:
            try:
                stt = p.stat()
            except Exception:
                continue
            dir_key, source = self._dir_key_for(p)
            in_dir = ""
            try:
                if p.parent != base and p.parent.parent == base:
                    in_dir = p.parent.name
            except Exception:
                in_dir = ""
            pages = None
            for mod_name in ("pymupdf", "fitz"):   # 老工程 venv 两种模块名都有
                try:
                    doc = importlib.import_module(mod_name).open(str(p))
                    try:
                        pages = int(doc.page_count)
                    finally:
                        doc.close()
                    break
                except Exception:
                    continue
            rel = p.name
            try:
                rel = str(p.relative_to(base))
            except Exception:
                pass
            items.append({
                "name": p.name, "rel": rel, "path": str(p),
                "dir_key": dir_key or p.stem, "dir_key_source": source or "filename-fallback",
                "in_dir": in_dir,
                "bytes": int(stt.st_size), "size_mb": round(stt.st_size / 1024 / 1024, 2),
                "mtime": datetime.fromtimestamp(stt.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "pages": pages,
            })
        return {"ok": True, "dir": str(base), "items": items, "count": len(items),
                "note": ("页数由 pymupdf 惰性读取（打不开 ⇒ null）；目录键＝tab1 人工确认的书名"
                         "（未确认 ⇒ 文件名，source=filename-fallback）")}

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
            book, _ms, _mk = lib.resolve_book_meta(name)   # 五级键回落（高清化名也能读到元数据）
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

    # ---------------- tab2 切图台（Phase A：检测 ⇒ 人工微调 ⇒ 1200dpi 裁切）----------------
    def tab2_detect(self, req: dict | None = None) -> dict:
        """自动检测红印：`{pdf, page, dpi=400}` ⇒ `{ok, boxes:[{x1,y1,x2,y2,idx,…}], count,
        elapsed_s, preview_png_b64, size, dpi, boxes_dpi}`。

        * **坐标系统＝400dpi**（与库内 `stamps` bbox 同系；`dpi` 默认 400，改了就对不上库）；
        * `preview_png_b64`：整页**降采样到宽 ≤1000px** 并画好框（UI 画布直接用，免前端重复渲染）；
        * 同步执行（400dpi 渲 + 检测 ≈ 0.2–0.5 s），**不占 UI 线程锁**。
        """
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        pdf = self._resolve_pdf(req.get("pdf") or req.get("filename"))
        if pdf is None:
            return {"ok": False, "reason": "PDF_NOT_FOUND",
                    "msg": f"找不到 PDF：{req.get('pdf') or req.get('filename') or ''!r}"}
        try:
            page = int(req.get("page") or 0)
        except Exception:
            return {"ok": False, "reason": "BAD_PAGE", "msg": "page 必须是整数（1-based）"}
        if page < 1:
            return {"ok": False, "reason": "BAD_PAGE", "msg": "page 从 1 开始"}
        try:
            dpi = int(req.get("dpi") or 400)
        except Exception:
            return {"ok": False, "reason": "BAD_DPI", "msg": "dpi 必须是整数"}
        sd, err = self._src_module("seal_detect")
        if err:
            return err
        t0 = time.time()
        try:
            img = sd.render_page(pdf, page, dpi)
        except IndexError as exc:
            return {"ok": False, "reason": "BAD_PAGE", "msg": str(exc), "page": page}
        except Exception as exc:
            return {"ok": False, "reason": "ERROR",
                    "msg": f"渲页失败：{exc.__class__.__name__}: {exc}", "page": page}
        try:
            boxes = sd.detect_seals(img)
        except Exception as exc:
            return {"ok": False, "reason": "ERROR",
                    "msg": f"检测失败：{exc.__class__.__name__}: {exc}", "page": page}
        preview, pw, ph = self._preview_with_boxes(img, boxes)
        return {"ok": True, "pdf": str(pdf), "pdf_name": pdf.name, "page": page,
                "dpi": int(dpi), "boxes_dpi": 400,
                "size": [int(img.shape[1]), int(img.shape[0])],
                "boxes": boxes, "count": len(boxes),
                "preview_png_b64": preview, "preview_size": [pw, ph],
                "preview_scale": round(ph / max(img.shape[0], 1), 4),
                "elapsed_s": round(time.time() - t0, 2)}

    @staticmethod
    def _preview_with_boxes(img, boxes, max_w: int = 1000) -> tuple[str, int, int]:
        """整页图 → 降采样 + 画框 → **base64 PNG**（UI 画布直接用；失败返回空串，不抛）。"""
        try:
            import cv2  # 延迟 import（与逻辑层同栈）
            h, w = img.shape[:2]
            scale = min(1.0, float(max_w) / max(w, 1))
            small = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                               interpolation=cv2.INTER_AREA) if scale < 1.0 else img.copy()
            for b in boxes or []:
                x1 = int(round(float(b["x1"]) * scale))
                y1 = int(round(float(b["y1"]) * scale))
                x2 = int(round(float(b["x2"]) * scale))
                y2 = int(round(float(b["y2"]) * scale))
                cv2.rectangle(small, (x1, y1), (x2, y2), (0, 200, 255), 2)      # 橙：自动框
                cv2.putText(small, str(b.get("idx", "")), (x1 + 3, max(y1 - 4, 12)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1, cv2.LINE_AA)
            ok, buf = cv2.imencode(".png", small)
            if not ok:
                return "", small.shape[1], small.shape[0]
            return base64.b64encode(buf.tobytes()).decode("ascii"), small.shape[1], small.shape[0]
        except Exception:
            return "", 0, 0

    # ---------------- tab2 字段提取（释文 / 状态字 / 编号 + 阅读顺序）----------------
    def tab2_extract(self, req: dict | None = None) -> dict:
        """自动检测 + **字段提取**：`{pdf, page, dpi=400, reading_order='auto', boxes?}` ⇒
        `{ok, boxes, count, seals:[…三字段…], reading_order, order_source, dropped, preview_png_b64}`。

        * 算法在 `src/field_extract.py`（PoC 逐条移植；四轮过滤/就近归属/分类/阅读顺序/纠错口径）；
        * `boxes` 可传（人工微调后的框）⇒ 只做 OCR 归属，不重检测；
        * `reading_order='auto'` ⇒ 按编号序列推断（`order_source='code-sequence'`）；
          显式传 `rtl-ttb` 等 ⇒ `order_source='manual'`；
        * 预览图把三类字段用**不同颜色**标出（释文/状态/编号），并标读数与 P-C-R。
        * **无 OCR 能力时优雅降级**（阶段 1 包 `斐萃_lite.app`：`rapidocr` 不在包里）⇒ 仍返回
          `ok: True`，只做红印检测得到 `boxes`，`seals` 三字段为空串、`ocr_available=False`、
          `fields_manual=True`、`note` 提示手动填写或改用 `斐萃_pro`；**绝不抛 `ModuleNotFoundError`**。
          阅读顺序无法由编号推断 ⇒ 用本书元数据（`order_source='book-meta'`）或回落 `ltr-ttb`（`fallback`）。
        """
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        pdf = self._resolve_pdf(req.get("pdf") or req.get("filename"))
        if pdf is None:
            return {"ok": False, "reason": "PDF_NOT_FOUND",
                    "msg": f"找不到 PDF：{req.get('pdf') or req.get('filename') or ''!r}"}
        try:
            page = int(req.get("page") or 0)
        except Exception:
            return {"ok": False, "reason": "BAD_PAGE", "msg": "page 必须是整数（1-based）"}
        if page < 1:
            return {"ok": False, "reason": "BAD_PAGE", "msg": "page 从 1 开始"}
        try:
            dpi = int(req.get("dpi") or 400)
        except Exception:
            return {"ok": False, "reason": "BAD_DPI", "msg": "dpi 必须是整数"}
        fe, err = self._src_module("field_extract")
        if err:
            return err
        t0 = time.time()
        try:
            img = fe.render_page(pdf, page, dpi)
        except IndexError as exc:
            return {"ok": False, "reason": "BAD_PAGE", "msg": str(exc), "page": page}
        except Exception as exc:
            return {"ok": False, "reason": "ERROR",
                    "msg": f"渲页失败：{exc.__class__.__name__}: {exc}", "page": page}
        boxes_in = req.get("boxes") if isinstance(req.get("boxes"), list) and req.get("boxes") else None
        # 能力闸先判：lite 包（阶段 1）没有 rapidocr ⇒ 只做红印检测，字段留空交人工填
        ocr_ok = ocr_available()
        book, meta_source, meta_key = lib.resolve_book_meta(pdf)   # 五级键回落
        order_req = str(req.get("reading_order") or "auto").strip().lower()
        fe_order, order_override = str(req.get("reading_order") or "auto"), ""
        if not ocr_ok and order_req == "auto":
            # 无编号可推断 ⇒ 用**书级元数据**（与 tab2_crop 的 auto 口径一致），没有才回落 ltr-ttb
            bm_order = getattr(fe, "normalize_reading_order", lambda _v: None)(book.get("reading_order") or "")
            if bm_order:
                fe_order, order_override = bm_order, "book-meta"
        try:
            fields = fe.extract_fields(img, boxes_in,
                                       reading_order=fe_order,
                                       authoritative=req.get("authoritative"))
        except Exception as exc:
            return {"ok": False, "reason": "ERROR",
                    "msg": f"字段提取失败：{exc.__class__.__name__}: {exc}", "page": page}
        if not fields.get("ok"):
            return {**fields, "pdf": str(pdf), "pdf_name": pdf.name, "page": page, "dpi": int(dpi)}
        ocr_ok = bool(fields.get("ocr_available", ocr_ok))
        seals = fields.get("seals") or []
        preview, pw, ph = self._preview_with_fields(img, seals)
        boxes = [{"x1": s["box"][0], "y1": s["box"][1], "x2": s["box"][2], "y2": s["box"][3],
                  "idx": s.get("read_order") or s.get("idx")} for s in seals]
        order_source = order_override or fields.get("order_source")
        if not ocr_ok:
            note = (f"本版不含 OCR（斐萃_lite）：本次只做了红印检测（{len(boxes)} 枚），"
                    "释文/状态/编号请手动填写（字段仍随裁切写入 _fields.json）；"
                    "要自动识别请用 斐萃_pro（含 OCR）")
        else:
            note = "字段仅供参考：纠错只认权威词表与同页多数票（≥3），其余原样输出"
        return {"ok": True, "pdf": str(pdf), "pdf_name": pdf.name, "page": page,
                "dpi": int(dpi), "boxes_dpi": 400,
                "size": fields.get("size") or [int(img.shape[1]), int(img.shape[0])],
                "boxes": boxes, "count": len(boxes), "seals": seals,
                "reading_order": fields.get("reading_order"),
                "order_source": order_source,
                "ocr_available": ocr_ok, "fields_manual": (not ocr_ok),
                "book_meta": {"dynasty": book.get("dynasty") or "",
                              "author": book.get("author") or "",
                              "reading_order": book.get("reading_order") or "auto",
                              "meta_source": meta_source, "meta_key": meta_key},
                "dropped": fields.get("dropped"), "dropped_texts": fields.get("dropped_texts"),
                "far_limit": fields.get("far_limit"), "ocr_items": fields.get("ocr_items"),
                "preview_png_b64": preview, "preview_size": [pw, ph],
                "preview_scale": round(ph / max(int(img.shape[0]), 1), 4),
                "elapsed_s": round(time.time() - t0, 2),
                "note": note}

    @staticmethod
    def _preview_with_fields(img, seals, max_w: int = 1000) -> tuple[str, int, int]:
        """整页图 + 印章框 + **三类字段框（分色）** + 读数/释文标签 ⇒ base64 PNG（失败返回空串）。"""
        try:
            import cv2  # 延迟 import
            h, w = img.shape[:2]
            scale = min(1.0, float(max_w) / max(w, 1))
            small = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                               interpolation=cv2.INTER_AREA) if scale < 1.0 else img.copy()
            colors = {"inscription": (200, 120, 0), "status": (0, 140, 255), "code": (180, 0, 180)}

            def px(b):
                x1, y1, x2, y2 = (float(v) for v in b[:4])
                return (int(round(x1 * scale)), int(round(y1 * scale)),
                        int(round(x2 * scale)), int(round(y2 * scale)))

            for s in seals or []:
                x1, y1, x2, y2 = px(s.get("box") or [0, 0, 0, 0])
                cv2.rectangle(small, (x1, y1), (x2, y2), (0, 180, 0), 2)        # 绿：印章
                tag = f"#{s.get('read_order') or ''} C{s.get('c', '?')}-R{s.get('r', '?')}"
                cv2.putText(small, tag, (x1 + 3, max(y1 - 5, 12)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 180, 0), 1, cv2.LINE_AA)
                for tb in s.get("text_boxes") or []:
                    bx1, by1, bx2, by2 = px(tb.get("box"))
                    col = colors.get(tb.get("kind"), (120, 120, 120))
                    cv2.rectangle(small, (bx1, by1), (bx2, by2), col, 2)       # 分色：三类字段
                label = f"{(s.get('inscription') or '-')}｜{(s.get('status') or '-')}｜{(s.get('code') or '-')}"
                cv2.putText(small, label, (x1, min(y2 + 22, small.shape[0] - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 220), 2, cv2.LINE_AA)
            ok, buf = cv2.imencode(".png", small)
            if not ok:
                return "", small.shape[1], small.shape[0]
            return base64.b64encode(buf.tobytes()).decode("ascii"), small.shape[1], small.shape[0]
        except Exception:
            return "", 0, 0

    def tab2_crop(self, req: dict | None = None) -> dict:
        """按框裁切：`{pdf, page, boxes, dpi=1200, cr_from_boxes?, reading_order?, fields?, per_seal_json?}` ⇒
        `{ok, outputs:[{name,path,bytes,naming,…}], skipped, dir_key, dir_key_source, reading_order,
        order_source, fields_sidecar, …}`。

        * `boxes` 在 **400dpi 坐标系**（＝检测输出 / 库内 bbox）；按 `dpi/400` 等比放大后裁；
        * **命名两层**：`fields[].code` 非空 ⇒ `<编号>_P<页>_C<列>_R<行>_<释文>_<朝代>_<作者>.tiff`，
          否则回落 `P<页>-C<列>-R<行>.tiff`（旧名，保兼容）；清洗/截断规则见 `src/seal_crop.py` docstring；
        * **C/R 方向**跟随 `reading_order`（`rtl` ⇒ **右列 C1**）；`'auto'`/缺省 ⇒ 取本书元数据
          （tab1「阅读顺序」），再不行回落 `ltr-ttb`（＝改动前行为）。`cr_from_boxes` 优先级最高；
        * `fields` 与 `boxes` 同序（tab2 字段区编辑后的值）⇒ 裁完落 `<目录键>/_fields.json`
          （按页合并；含 `naming` 与字段原值），`per_seal_json=true` 另写每枚 `.json`；
        * **一次调用请传本页全部框**：C/R 按**本次框集合**的网格位次排序 ⇒ 分多次各传一枚会各自
          从 `C1-R1` 起、同名互相覆盖（UI 应攒齐整页框后一次提交）；
        * 目录键＝**tab1 人工确认的书名**（`manual`）；未确认 ⇒ PDF 文件名（`filename-fallback`，
          UI 提示「建议去 tab1 确认书名」）——**不再走 ISBN / 旧配置表**；
        * **物理尺寸（mm）**：本书元数据 `true_dpi`（tab1 人工填的真实 dpi）非空 ⇒ `manual-dpi`
          口径，否则用渲染页 `page.rect` ⇒ `page-box`；`outputs[]` 每项带
          `width_mm/height_mm/size_source`（整数 mm），TIFF 内另写 `XResolution/YResolution/
          ResolutionUnit` ＋ 单条 `ImageDescription(270)`；
        * **串行**：另一单裁切在跑 ⇒ 直接 `{ok:false, reason:'BUSY'}`（不排队堆 1200dpi 页图）。
        """
        miss = self._need_root()
        if miss:
            return miss
        req = req or {}
        pdf = self._resolve_pdf(req.get("pdf") or req.get("filename"))
        if pdf is None:
            return {"ok": False, "reason": "PDF_NOT_FOUND",
                    "msg": f"找不到 PDF：{req.get('pdf') or req.get('filename') or ''!r}"}
        boxes = req.get("boxes") or []
        if not isinstance(boxes, list) or not boxes:
            return {"ok": False, "reason": "NO_BOXES", "msg": "没有可裁的框（先检测或手动画框）"}
        try:
            page = int(req.get("page") or 0)
        except Exception:
            return {"ok": False, "reason": "BAD_PAGE", "msg": "page 必须是整数（1-based）"}
        sc, err = self._src_module("seal_crop")
        if err:
            return err
        book, meta_source, meta_key = lib.resolve_book_meta(pdf)   # 五级键回落（高清化名/目录键）
        dir_key, dir_key_source = self._dir_key_for(pdf)           # tab1 书名 ／ 文件名（不再读旧表）
        fields_req = req.get("fields")
        seals_hint = []
        if isinstance(fields_req, list):
            for i, f in enumerate(fields_req):
                if not isinstance(f, dict):
                    continue
                row = dict(f)
                b = boxes[i] if i < len(boxes) else None
                if isinstance(b, dict):
                    row["box"] = [b.get("x1"), b.get("y1"), b.get("x2"), b.get("y2")]
                seals_hint.append(row)
        order, order_source = self._resolve_reading_order(req.get("reading_order"), book, seals_hint)
        if not self._crop_lock.acquire(blocking=False):
            return {"ok": False, "reason": "BUSY", "msg": "上一单裁切还在跑（1200dpi 渲页很重）"}
        try:
            res = sc.crop_page(pdf, page, boxes,
                               self._root_path() / lib.TIFF_DIR,
                               pdf_name=pdf.name,
                               dpi=int(req.get("dpi") or 1200),
                               cr_from_boxes=req.get("cr_from_boxes"),
                               reading_order=order,
                               fields=req.get("fields"),
                               per_seal_json=bool(req.get("per_seal_json")),
                               order_source=order_source,
                               dynasty=book.get("dynasty"),
                               author=book.get("author"),
                               true_dpi=book.get("true_dpi"),
                               dir_key=dir_key,
                               dir_key_source=dir_key_source)
        except Exception as exc:
            return {"ok": False, "reason": "ERROR", "msg": f"{exc.__class__.__name__}: {exc}"}
        finally:
            self._crop_lock.release()
        if isinstance(res, dict):                                   # 诊断：朝代/作者取自哪级键
            res.setdefault("meta_source", meta_source)
            res.setdefault("meta_key", meta_key)
            res.setdefault("dir_key", dir_key)
            res.setdefault("dir_key_source", dir_key_source)
            res.setdefault("book_meta", {"dynasty": book.get("dynasty") or "",
                                         "author": book.get("author") or "",
                                         "meta_source": meta_source, "meta_key": meta_key})
        return res

    @staticmethod
    def _resolve_reading_order(raw, book: dict, seals=None) -> tuple[str, str]:
        """⇒ `(reading_order, order_source∈{manual,code-sequence,book-meta,fallback})`。

        `raw` 显式合法 ⇒ 原样（`manual`，用户意图优先）；`auto`/空 ⇒ **按编号序列推断**
        （`fields[].code` 至少 2 枚且都带框 ⇒ `code-sequence`）→ 本书元数据（`book-meta`）→
        `ltr-ttb`（`fallback`，＝改动前行为）。

        ⚠ 语义分界（`ctOrderForCrop` 与后端必须同口径）：**下拉停在 `auto` ⇒ 前端只传 `'auto'`**，
        由后端在这里推断；**不要把上一轮 `tab2_extract` 的推断值当显式值回传** —— 那会把
        `order_source` 误标成 `manual`，抹掉「这个顺序是机器推的还是人选的」这一信息。
        """
        try:
            from src.field_extract import normalize_reading_order, infer_reading_order
        except Exception:
            normalize_reading_order = lambda v: v if v in ("rtl-ttb", "ltr-ttb", "rtl-btt", "ltr-btt") else None  # noqa: E731
            infer_reading_order = None
        raw_s = str(raw or "").strip().lower()
        if raw_s and raw_s != "auto":
            ord_ = normalize_reading_order(raw_s)
            if ord_:
                return ord_, "manual"
        coded = [s for s in (seals or []) if isinstance(s, dict)
                 and str(s.get("code") or "").strip() and s.get("box")]
        if infer_reading_order is not None and len(coded) >= 2:
            ord_, src = infer_reading_order(coded)
            if src == "code-sequence" and ord_:
                return ord_, "code-sequence"
        meta_ord = normalize_reading_order((book or {}).get("reading_order"))
        if meta_ord:
            return meta_ord, "book-meta"
        return "ltr-ttb", "fallback"

    # ---------------- tab2 一键全自动（检测 → OCR → 裁切，逐页落盘 / 断点续跑 / 可取消）----------------
    #: 全自动的切图 dpi（默认 1200，与人工裁切同档；600 只是省时试跑用）
    AUTOCROP_DPI_DEFAULT = 1200
    AUTOCROP_DPI_ALLOWED = (300, 600, 1200, 2400)

    def tab2_autocrop_start(self, req: dict | None = None) -> dict:
        """一键全自动：`{pdf, page_from?, page_to?, dpi?, resume?}` ⇒ `{ok, job:{…}}`。

        * 后台线程跑 `src.autocrop.run_autocrop`（**UI 不阻塞**），进度见 `tab2_autocrop_status`；
        * **单例**：已在跑 ⇒ `{ok:false, reason:'BUSY', job:…}`（不排队：1200dpi 页图很吃内存）；
        * `resume=True`（默认）⇒ 进度文件里已裁完的页直接跳过（断点续跑）；`resume=False` ⇒ 全重跑；
        * 全程**不向 UI 抛栈**：异常一律折成 `{ok:false, reason, msg}`。
        """
        try:
            miss = self._need_root()
            if miss:
                return miss
            req = req or {}
            pdf = self._resolve_pdf(req.get("pdf") or req.get("filename") or req.get("name"))
            if pdf is None:
                return {"ok": False, "reason": "PDF_NOT_FOUND",
                        "msg": f"找不到 PDF：{req.get('pdf') or req.get('filename') or ''!r}"
                               f"（可给绝对路径，或 2_HighRes_PDF 下的文件名）"}
            try:
                dpi = int(req.get("dpi") or self.AUTOCROP_DPI_DEFAULT)
            except Exception:
                return {"ok": False, "reason": "BAD_DPI", "dpi": req.get("dpi"),
                        "allowed": list(self.AUTOCROP_DPI_ALLOWED), "msg": "dpi 必须是整数"}
            if dpi not in self.AUTOCROP_DPI_ALLOWED:
                return {"ok": False, "reason": "BAD_DPI", "dpi": dpi,
                        "allowed": list(self.AUTOCROP_DPI_ALLOWED),
                        "msg": f"dpi 只支持 {list(self.AUTOCROP_DPI_ALLOWED)}"
                               f"（默认 {self.AUTOCROP_DPI_DEFAULT}）"}
            try:
                page_from = int(req.get("page_from") or 1)
                raw_to = req.get("page_to")
                page_to = None if raw_to in (None, "") else int(raw_to)
            except Exception:
                return {"ok": False, "reason": "BAD_RANGE", "msg": "page_from / page_to 必须是整数"}
            if page_from < 1 or (page_to is not None and page_to < page_from):
                return {"ok": False, "reason": "BAD_RANGE",
                        "msg": f"页区间不合法：{page_from}–{page_to}"}
            resume = bool(req.get("resume", True))
            ac, err = self._src_module("autocrop")
            if err:
                return err
            dir_key, dir_key_source = self._dir_key_for(pdf)
            with self._ac_lock:                      # 单例：查-建 在同一把锁里，避免双起
                cur = self._ac_task
                if cur is not None and cur.state in ("queued", "running"):
                    return {"ok": False, "reason": "BUSY", "job": cur.snapshot(),
                            "msg": f"已有全自动任务在跑（第 {cur.page}/{cur.pages_total or '?'} 页）"}
                task = AutoCropTask(pdf, dpi, page_from, page_to, resume, push=self.jobs._push)
                task.dir_key = dir_key
                self._ac_task = task
                threading.Thread(target=self._autocrop_run,
                                 args=(task, ac, dir_key, dir_key_source),
                                 daemon=True, name=f"autocrop-{task.id}").start()
            return {"ok": True, "job": task.snapshot(),
                    "dir_key": dir_key, "dir_key_source": dir_key_source,
                    "page_from": page_from, "page_to": page_to, "dpi": dpi, "resume": resume,
                    "msg": "已开始全自动（后台线程；每页裁完即落盘，可随时取消/续跑）",
                    "note": "进度见 tab2_autocrop_status / onProgress(kind=tab2_autocrop)"}
        except Exception as exc:                     # noqa: BLE001 —— 端点兜底：永不向 UI 抛栈
            return {"ok": False, "reason": "ERROR",
                    "msg": f"启动失败：{exc.__class__.__name__}: {exc}"}

    def _autocrop_run(self, task: AutoCropTask, ac, dir_key: str, dir_key_source: str) -> None:
        """后台线程体：跑逻辑层 ⇒ 把结果交回 `task.finish`（**不许抛出去**）。"""
        try:
            res = ac.run_autocrop(task.pdf, self._root_path(),
                                  dpi=task.dpi, detect_dpi=ac.DETECT_DPI,
                                  page_from=task.page_from, page_to=task.page_to,
                                  resume=task.resume,
                                  progress_cb=task.on_progress,
                                  cancel_flag=task.cancel_event.is_set,
                                  dir_key=dir_key, dir_key_source=dir_key_source)
        except Exception as exc:
            res = {"ok": False, "reason": "ERROR", "msg": f"{exc.__class__.__name__}: {exc}",
                   "pages_done": task.pages_done}
        try:
            task.finish(res)
        except Exception:
            pass

    def tab2_autocrop_status(self, _req: dict | None = None) -> dict:
        """轮询：`{ok, running, cancelled, state, progress:{page, pages_total, pages_done,
        seals_total, current_page_elapsed_s, eta_s}, dir_key, msg, result}`。"""
        try:
            task = self._ac_task
            if task is None:
                return {"ok": True, "running": False, "cancelled": False, "state": "idle",
                        "progress": {"page": 0, "pages_total": 0, "pages_done": 0,
                                     "pages_skipped": 0, "pages_failed": 0, "seals_total": 0,
                                     "current_page_elapsed_s": 0.0, "eta_s": None},
                        "dir_key": "", "msg": "空闲（还没跑过全自动）", "result": None}
            return {"ok": True, **task.snapshot()}
        except Exception as exc:                     # noqa: BLE001
            return {"ok": False, "running": False, "cancelled": False, "reason": "ERROR",
                    "msg": f"状态读取失败：{exc.__class__.__name__}: {exc}"}

    def tab2_autocrop_cancel(self, _req: dict | None = None) -> dict:
        """请求取消（当前页写盘后停；**已裁页与进度保留**，可就地续跑）。"""
        try:
            task = self._ac_task
            if task is None or task.state not in ("queued", "running"):
                return {"ok": False, "reason": "IDLE", "msg": "没有在跑的全自动任务"}
            task.cancel_event.set()
            return {"ok": True, "job": task.snapshot(),
                    "msg": f"已请求取消（完成 {task.pages_done} 页 · 进度保留可续跑）"}
        except Exception as exc:                     # noqa: BLE001
            return {"ok": False, "reason": "ERROR",
                    "msg": f"取消失败：{exc.__class__.__name__}: {exc}"}

    def open_in_finder(self, req: dict | None = None) -> dict:
        """在**系统文件管理器**里定位产物（macOS 访达 / Windows 资源管理器 / Linux xdg-open；失败只报错，不抛）。"""
        req = req or {}
        p = Path(str(req.get("path", "")))
        if not p.exists():
            return {"ok": False, "msg": "路径不存在"}
        try:
            if sys.platform == "win32":
                # 资源管理器：目录 ⇒ `explorer <dir>`；文件 ⇒ `explorer /select,<file>`（打开父目录并选中它）
                subprocess.Popen(["explorer", f"/select,{p}"] if p.is_file() else ["explorer", str(p)])
                return {"ok": True, "msg": "已在资源管理器打开"}
            if sys.platform != "darwin":
                subprocess.Popen(["xdg-open", str(p)])
                return {"ok": True, "msg": "已打开"}
            subprocess.Popen(["open", "-R" if p.is_file() else "", str(p)] if p.is_file()
                             else ["open", str(p)])
            return {"ok": True, "msg": "已在访达打开"}
        except Exception as exc:
            return {"ok": False, "msg": f"{exc.__class__.__name__}: {exc}"}

    # ---------------- tab3：3_Cropped_Tiff ----------------
    def _tab3_dir_meta(self, root: Path, subs: list[str]) -> dict:
        """tab3 的**目录键视图**：新键（tab1 书名）＋ **旧键只读展示**。

        ⇒ `{books:[{filename,dir_key,dir_key_source,dir_exists,legacy_dir_key,legacy_dir_exists}],
        subdir_meta:[{dir_key,files,legacy,legacy_of,read_only}], legacy_dir_keys:{旧键:PDF名}}`。

        * 新键 ＝ `resolve_dir_key`（`manual` / `filename-fallback`）；
        * 旧键 ＝ `find_legacy_dir_key`（`_fields.json` 的 `pdf_name` 回指）—— **只读展示**，
          **不自动迁**（自动迁只发生在 tab1 保存书名那一刻，见 `tab1_save_meta`）；
        * 与任何 PDF 都对不上的子目录照旧列出（`dir_key_source='unregistered'`）。
        """
        books: list[dict] = []
        legacy_dir_keys: dict[str, str] = {}
        try:
            pdfs = lib.list_pdf_files(root)
        except Exception:
            pdfs = []
        for p in pdfs:
            try:
                dk, src = lib.resolve_dir_key(p, root=root)
                legacy = lib.find_legacy_dir_key(root, p)
            except Exception:
                dk, src, legacy = p.stem, "filename-fallback", ""
            legacy_exists = bool(legacy) and (root / lib.TIFF_DIR / legacy).is_dir()
            if legacy and legacy != dk and legacy_exists:
                legacy_dir_keys[legacy] = p.name
            books.append({"filename": p.name, "dir_key": dk, "dir_key_source": src,
                          "dir_exists": (root / lib.TIFF_DIR / dk).is_dir(),
                          "legacy_dir_key": legacy if legacy_exists and legacy != dk else "",
                          "legacy_dir_exists": bool(legacy_exists and legacy != dk)})
        subdir_meta = []
        for s in subs:
            try:
                n = len(lib.list_tiff_files(root, s))
            except Exception:
                n = 0
            subdir_meta.append({"dir_key": s, "files": n, "legacy": s in legacy_dir_keys,
                                "legacy_of": legacy_dir_keys.get(s, ""),
                                "read_only": s in legacy_dir_keys})
        return {"books": books, "subdir_meta": subdir_meta, "legacy_dir_keys": legacy_dir_keys}

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
            parsed = validator.parse_tiff_name(n)      # 旧模板 + 切图台新命名（兼容解析）
            files.append({
                "name": n, "size_mb": round(stt.st_size / 1024 / 1024, 2),
                "mtime": datetime.fromtimestamp(stt.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "standard": parsed is not None,
                "naming": (parsed or {}).get("naming") or "",
                "page": (parsed or {}).get("page"), "col": (parsed or {}).get("col"),
                "row": (parsed or {}).get("row"),
                "shiwen": (parsed or {}).get("shiwen") or "",
                "dynasty": (parsed or {}).get("dynasty") or "",
                "author": (parsed or {}).get("author") or "",
                "path": str(f),
            })
        name, is_admin = self._session_user()
        dir_meta = self._tab3_dir_meta(root, subs)
        cur_src = "unregistered"
        for b in dir_meta["books"]:
            if b["dir_key"] == cur:
                cur_src = b["dir_key_source"]
                break
        else:
            if cur in dir_meta["legacy_dir_keys"]:
                cur_src = "legacy"
        legacy_of_cur = dir_meta["legacy_dir_keys"].get(cur, "")
        if legacy_of_cur:
            for f in files:
                f["legacy_dir_key"] = cur
        return {"ok": True, "root": str(root), "tab": lib.TIFF_DIR, "subdirs": subs,
                "current": cur, "files": files,
                "count": len(files), "template": f"{validator.PREFIX}释文-朝代-作者{validator.SUFFIX}",
                "dir_key": cur, "dir_key_source": cur_src,
                "dir_key_book": next((b["filename"] for b in dir_meta["books"]
                                      if b["dir_key"] == cur), ""),
                "dir_key_legacy": legacy_of_cur,
                "dir_key_current_exists": bool(cur) and any(b["dir_key"] == cur and b["dir_exists"]
                                                           for b in dir_meta["books"]),
                "books": dir_meta["books"], "subdir_meta": dir_meta["subdir_meta"],
                "legacy_dir_keys": dir_meta["legacy_dir_keys"],
                "view_cfg": TAB3_VIEW_CFG, "view_default": TAB3_VIEW_DEFAULT,
                "thumb_max": TIFF_THUMB_MAX, "preview_max": TIFF_PREVIEW_MAX,
                "limits": {"shiwen_max": validator.SHIWEN_MAX, "author_max": validator.AUTHOR_MAX},
                "operator": name, "is_admin": bool(is_admin),
                "ocr_available": ocr_available(), "ocr_note": ocr_unavailable_note(),
                "corrector_available": True,          # 纠错层纯 stdlib（不依赖 OCR 引擎）
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
            return {"ok": False, "msg": "占位图 local-dist/assets/test_seal.tiff 不存在"}
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
        """缩略图/预览 PNG（带 mtime 缓存，落在 `local-dist/var/thumbs/`，不入库）。"""
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

    # ---- tab3 OCR（辅助面：只读，不写文件 / 不写库 / 不改名）----
    def _ocr_png(self, src: Path, sub: str) -> tuple[Path | None, str]:
        """OCR 输入面：位图（png/jpg/…）直用；TIFF 及其他 ⇒ 出 PNG（缓存，长边 OCR_MAX_EDGE）。"""
        if src.suffix.lower() in OCR_DIRECT_SUFFIXES:
            return src, "direct"
        png, engine, msg = self._thumb_file(src, sub, OCR_MAX_EDGE)
        return png, (engine or msg or "unknown")

    def tab3_ocr(self, req: dict | None = None) -> dict:
        """对当前选中裁切件跑**本地**通用 OCR（只读；绝不改文件、不写库、不改名）。

        可靠性口径（**必须如实反映到 UI**，见 `ops/ocr-rapid/README.md`）：
          ①②类（印刷体 / 版权页 / 边款释文）通用 OCR **可靠**（实测分数 0.94–0.9999）；
          ③类（**印面篆书**）通用 OCR **不可用** —— 248 枚池：非空 60.1%、均分 0.2428，
          真实样本「左軍丞玺」被两引擎一致误读为「左軍丞錄」。
        故本方法只回**原始读数**，诚实提示由 `hint` 一并返回（`OCR_HINT` 单一真源），
        UI 原样显示 ⇒ **不得**让用户以为一键可得正确释文。

        返回：`{ok, texts, scores, elapsed_s, engine, text, hint, …}`；异常一律
        `{ok: false, msg}`（本层永不抛 —— 与 `api.py` 全局纪律一致）。
        """
        t0 = time.time()
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
        base = {"texts": [], "scores": [], "text": "", "elapsed_s": 0.0,
                "engine": OCR_ENGINE_LABEL, "hint": OCR_HINT}
        # **能力闸**：阶段 1 打包件没有 OCR 栈 ⇒ 结构化拒绝（绝不 import 之后才炸）
        if not ocr_available():
            body = dict(base)
            body.update({"ok": False, "reason": "OCR_UNAVAILABLE", "code": "OCR_UNAVAILABLE",
                         "msg": "本版本不含 OCR 引擎（斐萃_lite / 阶段 1 包未内置 rapidocr）："
                                "OCR 试试看不可用，释文请手动填写；要自动识别请用斐萃_pro。"})
            return body
        if not name or not src.is_file():
            return {"ok": False, "msg": f"文件不存在：{name or '（空）'}", "code": "missing", **base}
        try:
            png, how = self._ocr_png(src, sub)
        except Exception as exc:
            return {"ok": False, "code": "render_failed", "input_via": "",
                    "msg": f"出图失败，无法 OCR：{exc.__class__.__name__}: {exc}", **base}
        if png is None:
            return {"ok": False, "code": "render_failed", "input_via": "",
                    "msg": f"出图失败，无法 OCR：{how}", **base}
        try:
            # ⚠ **必须走 `importlib`**（2026-10-18 修复）：PyInstaller 的 AST 分析会追踪
            #   **函数体内**的 `import` 语句 ⇒ 写成 `from src import ocr_rapid` 时，
            #   即使阶段 1 的 `datas`/`hiddenimports` 都没列它，`src/ocr_rapid.py` 照样被收进 PYZ
            #   ⇒ 它 import rapidocr ⇒ 触发 `hook-onnxruntime.py`/`hook-shapely.py`
            #   ⇒ s1 从 210 MB 涨到 298 MB（onnxruntime 70 MB ＋ shapely 4.3 MB ＋ pyclipper ＋ 模型）。
            #   动态 import 不做静态分析；阶段 2/3 仍拿得到（spec 的 `if WITH_OCR:` 已列 hiddenimport）。
            ocr_rapid = importlib.import_module("src.ocr_rapid")
            res = ocr_rapid.ocr_image(str(png))
            engine_id = ocr_rapid.OCR_ENGINE_NAME
        except Exception as exc:
            return {"ok": False, "code": "ocr_error", "input_via": how,
                    "msg": f"OCR 失败：{exc.__class__.__name__}: {exc}", **base}
        texts = [str(t) for t in (res.get("texts") or [])]
        scores = []
        for s in (res.get("scores") or []):
            try:
                scores.append(round(float(s), 4))
            except Exception:
                scores.append(0.0)
        elapsed = round(time.time() - t0, 2)
        return {
            "ok": True, "subdir": sub, "name": name,
            "texts": texts, "scores": scores, "text": "".join(texts),
            "elapsed_s": elapsed, "engine": OCR_ENGINE_LABEL, "engine_id": engine_id,
            "input_via": how, "n": len(texts),
            "mean_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "empty": not texts,
            "hint": OCR_HINT,
            "note": "" if texts else "未识别到文字（印面篆书常见，不代表该件无字）",
        }

    def tab3_correct(self, req: dict | None = None) -> dict:
        """对一段释文给**纠错建议**（`src/ocr_corrector.py`；默认 `mode='suggest'`）。

        红线（Kevin 定，逐条落在返回值里）：
          * `suggest`（默认）**只给候选、不改字**；`auto` 必须由前端**显式**传（UI 复选框默认关），
            且**只改输入框文本，绝不动文件**；
          * 字表只有 2 条 `verified=true`（`錄→鈢`、`鮮→鲜`）⇒ 一并回 `map` 复核状态，
            别让用户以为字表已审完（`review_status` / `n_verified`）。
        返回：`{ok, mode, raw, corrected, hits, stats, map}`；异常 ⇒ `{ok: false, msg, hits: []}`。
        """
        req = req or {}
        text = str(req.get("text", ""))
        mode = str(req.get("mode", "suggest")).strip() or "suggest"
        try:
            from src import ocr_corrector
            res = ocr_corrector.correct(text, mode=mode)
            try:
                mm = ocr_corrector.map_summary(ocr_corrector.load_map())
            except Exception:
                mm = {}
        except Exception as exc:
            return {"ok": False, "mode": mode, "hits": [], "raw": text, "corrected": text,
                    "msg": f"纠错失败：{exc.__class__.__name__}: {exc}"}
        keys = ("pos", "from", "to", "rule_id", "source", "confidence",
                "verified", "applied", "skip_reason", "note")
        hits = [{k: h.get(k) for k in keys} for h in (res.get("hits") or [])]
        return {
            "ok": True, "mode": res["stats"]["mode"], "raw": res.get("raw", text),
            "corrected": res.get("corrected", text), "hits": hits, "stats": res.get("stats") or {},
            "map": {"version": mm.get("version"), "review_status": mm.get("review_status"),
                    "n_entries": mm.get("n_entries"), "n_verified": mm.get("n_verified")},
            "note": "ℹ️ 只改输入框文本，不改文件名；建议来自本地字表，请人工确认",
        }

    def tab3_parse(self, req: dict | None = None) -> dict:
        """文件名解析（`validator.parse_tiff_name` 单一真源）⇒ 回填 P/C/R 与三字段。

        认**两套**命名：旧模板 `P<页>-C<列>-R<行>-释文-朝代-作者.tiff` 与切图台新命名
        `<编号>_P<页>_C<列>_R<行>_<释文>_<朝代>_<作者>.tiff`（`naming` 字段区分）。
        两套都不匹配 ⇒ 三字段留空、前缀留空（与旧版 `webui.py` L808–816 同口径），并给出提示。
        """
        req = req or {}
        name = self._safe_seg(str(req.get("name", "")))
        parsed = validator.parse_tiff_name(name)
        fields = ({"shiwen": parsed["shiwen"], "dynasty": parsed["dynasty"],
                   "author": parsed["author"]} if parsed
                  else {"shiwen": "", "dynasty": "", "author": ""})
        prefix = ""
        if parsed:
            prefix = (f"{parsed['code']}_P{parsed['page_raw']}_C{parsed['col_raw']}_R{parsed['row_raw']}_"
                      if parsed["naming"] == "with_code"
                      else f"P{parsed['page_raw']}-C{parsed['col_raw']}-R{parsed['row_raw']}-")
        note = ""
        if not parsed:
            note = "文件名非标准模板 ⇒ 前缀留空，请手动填写（与旧版一致）"
        elif parsed["naming"] == "with_code":
            note = f"新命名（切图台带编号）：编号 {parsed['code']} · P/C/R 已回填"
        return {"ok": True, "name": name, "standard": bool(parsed), "fields": fields,
                "naming": (parsed or {}).get("naming") or "",
                "code": (parsed or {}).get("code") or "",
                "page": parsed["page"] if parsed else None,
                "col": parsed["col"] if parsed else None,
                "row": parsed["row"] if parsed else None,
                "prefix": prefix, "note": note,
                "limits": {"shiwen_max": validator.SHIWEN_MAX, "author_max": validator.AUTHOR_MAX}}

    def _compose_new_name(self, old_name: str, shiwen: str, dynasty: str,
                          author: str) -> dict:
        """新文件名 = **沿用旧文件名的命名方案**（旧模板 / 切图台新命名）＋ 三字段。

        * 旧模板 ⇒ `P<页>-C<列>-R<行>-释文-朝代-作者.tiff`（与旧版 `webui.py` L811/L829 同构造）；
        * 新命名（`<编号>_P<页>_C<列>_R<行>_…`）⇒ `<编号>_P<页>_C<列>_R<行>_释文_朝代_作者.tiff`
          （**保留编号**，不把新文件降级回旧名 —— 兼容解析不等于改语义）；
        * 两套都不匹配 ⇒ 前缀留空（提示手填）；校验一律走 `validator.validate_fields`。
        """
        parsed = validator.parse_tiff_name(old_name)
        if parsed:
            raw = (parsed["page_raw"], parsed["col_raw"], parsed["row_raw"])
            prefix = (f"{parsed['code']}_P{raw[0]}_C{raw[1]}_R{raw[2]}_"
                      if parsed["naming"] == "with_code"
                      else f"P{raw[0]}-C{raw[1]}-R{raw[2]}-")
            new_name = validator.build_crop_filename(
                raw[0], raw[1], raw[2], shiwen, dynasty, author,
                code=parsed["code"] if parsed["naming"] == "with_code" else "")
        else:
            prefix, new_name = "", f"{shiwen}-{dynasty}-{author}{validator.SUFFIX}"
        valid, msg = validator.validate_fields(shiwen, dynasty, author)
        return {
            "prefix": prefix, "standard": bool(parsed),
            "naming": (parsed or {}).get("naming") or "",
            "valid": bool(valid), "msg": msg, "new_name": new_name,
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


def startup() -> dict:
    """**进程启动一次性钩子**（`app.py::main` 调用）：目录兜底 ＋ 旧侧车迁移。**永不抛**。

    * 迁移＝`lib.migrate_legacy_meta()`：数据根**优先**、`books` **键并集**、旧件改名 `.migrated`
      留痕、**幂等**（第二次起来 `action="noop"`、0 变更）。
    * 只在**真启动**调（不在 `build_api()` 里）：`selftest.py` / `domtest*.py` 在 import 前把
      `FEICUI_DATA_DIR` 指到临时目录，若 import 即迁移，会把仓内 `local-dist/var/pdf_meta.json`
      搬进临时目录并改名 —— 那是自检污染，不是用户路径。
    """
    info: dict = {"data_dir": str(DATA_DIR), "meta_path": str(lib.DEFAULT_META_PATH), "migration": {}}
    try:
        info["migration"] = lib.migrate_legacy_meta()
    except Exception as exc:                                  # 迁移失败不拦启动
        info["migration"] = {"action": "error", "reason": f"{exc.__class__.__name__}: {exc}"}
    return info


def build_api() -> FeicuiApi:
    """唯一入口：两种形态都拿同一份实例。"""
    api = FeicuiApi()
    api._closer = None
    return api
