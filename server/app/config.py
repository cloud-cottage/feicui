"""feicui API 层配置（Kong / 阶段 1a）。

优先级（后者覆盖前者）：
  1. 内置默认值
  2. JSON 配置文件：$FEICUI_SERVER_CONFIG，或 server/config.json（存在才读）
  3. 环境变量：FEICUI_DB / FEICUI_ROOT / FEICUI_API_HOST / FEICUI_API_PORT / PORT / FEICUI_CHUNK_SIZE

规范锚点：`../docs/feicui.spec.md` v1.1 §4.2（影像路径一律相对 feicui/）、§6.1（API 端口 5196）、
§3.2 S-4（接口层不落业务真值）、PORTS.md 制度 (d)（本机非生产链路一律 127.0.0.1）。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# server/app/config.py -> app -> server -> feicui
SERVER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_DIR.parent  # /Users/kevin/bistro/shu/feicui
PROD_DB_PATH = (REPO_ROOT.parent / "data" / "yinpu.db").resolve()  # 唯一真源（不得被本层写路径触碰）

DEFAULT_CONFIG_FILE = SERVER_DIR / "config.json"

# CORS 允许来源（**唯一真源**，端点侧不得再散落硬编码）：本机非生产链路一律 `127.0.0.1`（PORTS.md 制度 (d)），
# 并同时给出 `localhost` 同形项（浏览器地址栏常见形态，与 5195 既有口径同形）。
#   * `5195` = feicui 前端（既有）；
#   * `5163` = 玺爱（xiai）dev 前端 —— `POST /api/tools/square-crop` 的调用方（本单新增）。
# 可用 `FEICUI_CORS_ORIGINS`（逗号分隔）整体覆盖；**任何情况下都不放开 `*`**。
DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:5195",
    "http://localhost:5195",
    "http://127.0.0.1:5163",
    "http://localhost:5163",
)


# ── 拖曳上传落盘（additive 端点 `POST /api/jobs/upload`）：默认常量 ────────────────
# 单文件上限默认 **5 GiB（5368709120 B）**（Kevin 2026-10-11 裁定，原值 512 MiB）：实测真实书
# `~/Downloads/秦印类编 检索版.pdf` ＝ 1.88 GiB / 851 页、`福庵印缀 原版 高清.pdf` ＝ 1.14 GiB / 236 页
# ⇒ 512 MiB 会把真书拒在门外；本机 `df` 余量 191 GiB 容得下。上限「**有上限 / 有默认值 / 可改**」
# 三件口径不变（§3.19.2：改数值不需升规范）。`FEICUI_UPLOAD_MAX_BYTES` 或 server/config.json 的
# `upload_max_bytes` 可改（自测调小阈值即可验 413，**不必真传 5 GiB**）。
# 分块写盘 1 MiB/块 ⇒ 内存占用恒定（对比 `app/multipart.py`：整包读进内存，372 MB 会打爆）。
UPLOAD_MAX_BYTES_DEFAULT = 5 * 1024 * 1024 * 1024
UPLOAD_CHUNK_BYTES_DEFAULT = 1024 * 1024
INBOX_DIRNAME = "inbox"


def _load_config_file() -> dict:
    path = Path(os.environ.get("FEICUI_SERVER_CONFIG", str(DEFAULT_CONFIG_FILE)))
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"配置文件必须是 JSON 对象：{path}")
    return data


def _resolve_db_path(value: str) -> Path:
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.resolve()


@dataclass(frozen=True)
class Settings:
    """进程级只读配置（每次读 API 都是现算，无进程内业务真值缓存）。"""

    db_path: Path
    root: Path
    host: str
    port: int
    chunk_size: int
    allow_prod_migrate: bool
    config_file: str | None
    debug: bool = False
    # ---- CORS 允许来源（默认＝DEFAULT_CORS_ORIGINS；`FEICUI_CORS_ORIGINS` 可整体覆盖）----
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    # ---- 执行层（阶段 1b-i）：池 / worker / 影像 口径 ----
    faces_dir: Path = REPO_ROOT / "output" / "faces"
    worker_python: Path = REPO_ROOT / "venv" / "bin" / "python"
    workers: int = 4
    doc_preprocess: bool = True
    cpu_threads: int = 2
    on_conflict: str = "skip"
    poll_interval: float = 0.5
    pool_state_path: Path = SERVER_DIR / ".run" / "pool.state.json"
    worker_log_dir: Path = SERVER_DIR / ".run" / "worker-logs"
    # ---- E4（阶段 1b-ii）：触发导出的落点与解释器（§3.1 E4 / §6.5） ----
    # 导出物落点＝feicui/exports（规范 §3.3 §9.6「首版仍走本地目录」）；env FEICUI_EXPORT_ROOT 可重定向
    # （自测用临时目录，**避免污染既有批次包**——导出根即 export.py 自己的 `FEICUI_EXPORT_ROOT`）。
    export_root: Path = REPO_ROOT / "exports"
    # E4 走 **worker 侧解释器**子进程调 `export.py` CLI（§6.5：接口层不装 OCR / 图像栈）
    export_script: Path = REPO_ROOT / "export.py"
    export_config_dir: Path = REPO_ROOT / "config"
    export_timeout_s: float = 180.0
    # ---- 印人采集（person-ingest，批 1）：**独立库**，与 yinpu.db 一字不碰（拆解件 §4.3）----
    # 落点 `feicui/var/person_ingest.db`（`var/` 已在 .gitignore 内，属运行时产物）；
    # 批次包落点沿用 `feicui/exports/`（与既有 fb_* 同根、不同前缀 `person_*`）。
    # `FEICUI_PERSON_DB` / `FEICUI_PERSON_EXPORT_ROOT` 可覆盖（自测用临时目录）。
    person_db_path: Path = REPO_ROOT / "var" / "person_ingest.db"
    person_export_root: Path = REPO_ROOT / "exports"
    person_source_base: str = "https://yin.fudan.edu.cn/service_yinpu"
    person_fetch_delay_s: float = 0.5
    person_fetch_timeout_s: float = 30.0
    # ---- 印谱采集（item-ingest，批 1）：**独立库**，与 yinpu.db / person_ingest.db 一字不碰 ----
    # 落点 `feicui/var/item_ingest.db`（`var/` 已在 .gitignore 内）；就绪包落点 `feicui/exports/`
    # （前缀 `item_import_*`）。`FEICUI_ITEMS_DB` / `FEICUI_ITEMS_EXPORT_ROOT` 等可覆盖（自测用）。
    items_db_path: Path = REPO_ROOT / "var" / "item_ingest.db"
    items_export_root: Path = REPO_ROOT / "exports"
    items_source_base: str = "https://yin.fudan.edu.cn/service_yinpu"
    items_fetch_delay_s: float = 0.5
    items_fetch_timeout_s: float = 30.0
    # ---- 印章采集（seal-ingest，批 1）：**独立库**，与 yinpu.db / person_ingest.db / item_ingest.db 一字不碰 ----
    # 落点 `feicui/var/seal_ingest.db`（`var/` 已在 .gitignore 内）；就绪包落点 `feicui/exports/`
    # （前缀 `seal_import_*`）；影像缓存 `var/seal_images/<kind>/<seqid>.jpg`（JPEG 源）＋
    # `var/seal_images_tiff/<sha256[:2]>/<sha256>.tiff`（内容寻址 TIFF，供 xiai 影像库）。
    # `FEICUI_SEALS_DB` / `FEICUI_SEALS_EXPORT_ROOT` / `FEICUI_SEAL_IMAGES_DIR` 等可覆盖（自测用）。
    seals_db_path: Path = REPO_ROOT / "var" / "seal_ingest.db"
    seals_export_root: Path = REPO_ROOT / "exports"
    seals_source_base: str = "https://yin.fudan.edu.cn/service_yinpu"
    seals_fetch_delay_s: float = 0.5
    seals_fetch_timeout_s: float = 30.0
    seal_images_dir: Path = REPO_ROOT / "var" / "seal_images"
    seal_images_tiff_dir: Path = REPO_ROOT / "var" / "seal_images_tiff"
    seals_image_delay_s: float = 0.15
    seals_image_concurrency: int = 1
    # ---- 关联面（relation-ingest，三表联立）：**纯本库联立、零联网**；**不新建 DB** ----
    # 就绪包落点 `feicui/exports/relation_import_<batch_id>/`（前缀 `relation_import_*`）；
    # 只读三库（person/item/seal ingest）＋三线既有就绪包。`FEICUI_RELATIONS_EXPORT_ROOT` 可覆盖（自测用）。
    relations_export_root: Path = REPO_ROOT / "exports"
    # ---- 拖曳上传（additive `POST /api/jobs/upload`）：落点与限流 ----
    # 落点 `feicui/inbox/<yyyymmdd>/<safe-name>.pdf`（`.gitignore` 已排除 `inbox/`：属运行时产物）；
    # 上限默认 5 GiB（5368709120 B；`FEICUI_UPLOAD_MAX_BYTES` / config.json `upload_max_bytes` 可改）；
    # 分块写盘 1 MiB（内存恒定）。`FEICUI_INBOX_DIR` 可重定向（自测用）。
    inbox_dir: Path = REPO_ROOT / INBOX_DIRNAME
    upload_max_bytes: int = UPLOAD_MAX_BYTES_DEFAULT
    upload_chunk_bytes: int = UPLOAD_CHUNK_BYTES_DEFAULT

    @property
    def is_prod_db(self) -> bool:
        return self.db_path == PROD_DB_PATH

    @property
    def sqlite_uri(self) -> str:
        return f"file:{self.db_path}"


def get_settings() -> Settings:
    file_cfg = _load_config_file()
    env = os.environ

    db_raw = env.get("FEICUI_DB") or file_cfg.get("db_path") or str(PROD_DB_PATH)
    db_path = _resolve_db_path(str(db_raw))

    root_raw = env.get("FEICUI_ROOT") or file_cfg.get("root") or str(REPO_ROOT)
    root = Path(root_raw).expanduser().resolve()

    host = env.get("FEICUI_API_HOST") or file_cfg.get("host") or "127.0.0.1"

    port_raw = env.get("FEICUI_API_PORT") or env.get("PORT") or file_cfg.get("port") or 5196
    port = int(port_raw)

    chunk_raw = env.get("FEICUI_CHUNK_SIZE") or file_cfg.get("chunk_size") or 8
    chunk_size = max(1, int(chunk_raw))

    # CORS 来源：`FEICUI_CORS_ORIGINS`（逗号分隔）显式给出时**整体覆盖**默认表；否则用 DEFAULT_CORS_ORIGINS。
    cors_raw = env.get("FEICUI_CORS_ORIGINS")
    cors_origins = (
        tuple(o.strip() for o in str(cors_raw).split(",") if o.strip())
        if cors_raw
        else DEFAULT_CORS_ORIGINS
    )

    return Settings(
        db_path=db_path,
        root=root,
        host=host,
        port=port,
        chunk_size=chunk_size,
        allow_prod_migrate=str(env.get("FEICUI_ALLOW_PROD_MIGRATE", "")).lower() in {"1", "true", "yes"},
        config_file=str(env.get("FEICUI_SERVER_CONFIG", DEFAULT_CONFIG_FILE))
        if Path(str(env.get("FEICUI_SERVER_CONFIG", DEFAULT_CONFIG_FILE))).is_file()
        else None,
        debug=str(env.get("FEICUI_DEBUG", "")).lower() in {"1", "true", "yes"},
        cors_origins=cors_origins,
        # ---- 执行层（阶段 1b-i）----
        faces_dir=Path(env.get("FEICUI_FACES_DIR") or file_cfg.get("faces_dir") or str(REPO_ROOT / "output" / "faces")).expanduser().resolve(),
        worker_python=Path(
            env.get("FEICUI_WORKER_PYTHON") or file_cfg.get("worker_python") or str(REPO_ROOT / "venv" / "bin" / "python")
        ).expanduser(),
        workers=max(1, int(env.get("FEICUI_WORKERS") or file_cfg.get("workers") or 4)),
        doc_preprocess=str(env.get("FEICUI_DOC_PREPROCESS", file_cfg.get("doc_preprocess", "1"))).lower()
        not in {"0", "false", "no", "off"},
        cpu_threads=max(1, int(env.get("FEICUI_CPU_THREADS") or file_cfg.get("cpu_threads") or 2)),
        on_conflict=str(env.get("FEICUI_ON_CONFLICT") or file_cfg.get("on_conflict") or "skip").lower(),
        poll_interval=float(env.get("FEICUI_POOL_POLL") or file_cfg.get("poll_interval") or 0.5),
        pool_state_path=Path(
            env.get("FEICUI_POOL_STATE") or file_cfg.get("pool_state_path") or str(SERVER_DIR / ".run" / "pool.state.json")
        ).expanduser(),
        worker_log_dir=Path(
            env.get("FEICUI_WORKER_LOG_DIR") or file_cfg.get("worker_log_dir") or str(SERVER_DIR / ".run" / "worker-logs")
        ).expanduser(),
        # ---- E4（阶段 1b-ii）----
        export_root=Path(
            env.get("FEICUI_EXPORT_ROOT") or file_cfg.get("export_root") or str(REPO_ROOT / "exports")
        ).expanduser().resolve(),
        export_script=Path(
            env.get("FEICUI_EXPORT_SCRIPT") or file_cfg.get("export_script") or str(REPO_ROOT / "export.py")
        ).expanduser(),
        export_config_dir=Path(
            env.get("FEICUI_CONFIG_DIR") or file_cfg.get("export_config_dir") or str(REPO_ROOT / "config")
        ).expanduser().resolve(),
        export_timeout_s=float(env.get("FEICUI_EXPORT_TIMEOUT") or file_cfg.get("export_timeout_s") or 180.0),
        # ---- 印人采集（批 1）：独立库 + 批次包落点（env 覆盖优先）----
        person_db_path=Path(
            env.get("FEICUI_PERSON_DB") or file_cfg.get("person_db_path") or str(REPO_ROOT / "var" / "person_ingest.db")
        ).expanduser().resolve(),
        person_export_root=Path(
            env.get("FEICUI_PERSON_EXPORT_ROOT") or file_cfg.get("person_export_root") or str(REPO_ROOT / "exports")
        ).expanduser().resolve(),
        person_source_base=str(
            env.get("FEICUI_PERSON_SOURCE_BASE") or file_cfg.get("person_source_base") or "https://yin.fudan.edu.cn/service_yinpu"
        ),
        person_fetch_delay_s=float(
            env.get("FEICUI_PERSON_FETCH_DELAY") or file_cfg.get("person_fetch_delay_s") or 0.5
        ),
        person_fetch_timeout_s=float(
            env.get("FEICUI_PERSON_FETCH_TIMEOUT") or file_cfg.get("person_fetch_timeout_s") or 30.0
        ),
        # ---- 印谱采集（批 1）：独立库 + 就绪包落点（env 覆盖优先）----
        items_db_path=Path(
            env.get("FEICUI_ITEMS_DB") or file_cfg.get("items_db_path") or str(REPO_ROOT / "var" / "item_ingest.db")
        ).expanduser().resolve(),
        items_export_root=Path(
            env.get("FEICUI_ITEMS_EXPORT_ROOT") or file_cfg.get("items_export_root") or str(REPO_ROOT / "exports")
        ).expanduser().resolve(),
        items_source_base=str(
            env.get("FEICUI_ITEMS_SOURCE_BASE") or file_cfg.get("items_source_base") or "https://yin.fudan.edu.cn/service_yinpu"
        ),
        items_fetch_delay_s=float(
            env.get("FEICUI_ITEMS_FETCH_DELAY") or file_cfg.get("items_fetch_delay_s") or 0.5
        ),
        items_fetch_timeout_s=float(
            env.get("FEICUI_ITEMS_FETCH_TIMEOUT") or file_cfg.get("items_fetch_timeout_s") or 30.0
        ),
        # ---- 印章采集（批 1）：独立库 + 就绪包 + 影像缓存落点（env 覆盖优先）----
        seals_db_path=Path(
            env.get("FEICUI_SEALS_DB") or file_cfg.get("seals_db_path") or str(REPO_ROOT / "var" / "seal_ingest.db")
        ).expanduser().resolve(),
        seals_export_root=Path(
            env.get("FEICUI_SEALS_EXPORT_ROOT") or file_cfg.get("seals_export_root") or str(REPO_ROOT / "exports")
        ).expanduser().resolve(),
        seals_source_base=str(
            env.get("FEICUI_SEALS_SOURCE_BASE") or file_cfg.get("seals_source_base") or "https://yin.fudan.edu.cn/service_yinpu"
        ),
        seals_fetch_delay_s=float(
            env.get("FEICUI_SEALS_FETCH_DELAY") or file_cfg.get("seals_fetch_delay_s") or 0.5
        ),
        seals_fetch_timeout_s=float(
            env.get("FEICUI_SEALS_FETCH_TIMEOUT") or file_cfg.get("seals_fetch_timeout_s") or 30.0
        ),
        seal_images_dir=Path(
            env.get("FEICUI_SEAL_IMAGES_DIR") or file_cfg.get("seal_images_dir") or str(REPO_ROOT / "var" / "seal_images")
        ).expanduser().resolve(),
        seal_images_tiff_dir=Path(
            env.get("FEICUI_SEAL_IMAGES_TIFF_DIR") or file_cfg.get("seal_images_tiff_dir")
            or str(REPO_ROOT / "var" / "seal_images_tiff")
        ).expanduser().resolve(),
        seals_image_delay_s=float(
            env.get("FEICUI_SEALS_IMAGE_DELAY") or file_cfg.get("seals_image_delay_s") or 0.15
        ),
        seals_image_concurrency=max(1, int(
            env.get("FEICUI_SEALS_IMAGE_CONCURRENCY") or file_cfg.get("seals_image_concurrency") or 1
        )),
        # ---- 关联面（三表联立）：就绪包落点（env 覆盖优先；**不新建 DB**）----
        relations_export_root=Path(
            env.get("FEICUI_RELATIONS_EXPORT_ROOT") or file_cfg.get("relations_export_root")
            or str(REPO_ROOT / "exports")
        ).expanduser().resolve(),
        # ---- 拖曳上传（additive `POST /api/jobs/upload`）：落点 ＋ 上限 ＋ 分块（env 覆盖优先）----
        inbox_dir=Path(
            env.get("FEICUI_INBOX_DIR") or file_cfg.get("inbox_dir") or str(REPO_ROOT / INBOX_DIRNAME)
        ).expanduser().resolve(),
        upload_max_bytes=max(
            1,
            int(
                env.get("FEICUI_UPLOAD_MAX_BYTES")
                or file_cfg.get("upload_max_bytes")
                or UPLOAD_MAX_BYTES_DEFAULT
            ),
        ),
        upload_chunk_bytes=max(
            4096,
            int(
                env.get("FEICUI_UPLOAD_CHUNK_BYTES")
                or file_cfg.get("upload_chunk_bytes")
                or UPLOAD_CHUNK_BYTES_DEFAULT
            ),
        ),
    )
