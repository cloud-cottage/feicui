"""feicui API 应用工厂 —— Kong / 阶段 1a。

规范锚点：§1.1（薄接口层 `feicui-api` :5196）、§1.3（进程分离：**重启接口层不得丢 job / 丢进度**
—— 本层无进程内业务状态，重启后 E2 读数与库内复算逐字一致）、§3.2 S-4。

启动（详见 server/README.md §8）：
    cd /Users/kevin/bistro/feicui/server
    FEICUI_DB=<db> ./.venv/bin/python -m app.main          # 等价于 uvicorn 起 app.main:app
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db, inbox_gc, migrations, poolctl, repository
from .config import get_settings
from .routers import jobs as jobs_router
from .routers import tools as tools_router
from .routers import persons as persons_router
from .routers import items as items_router
from .routers import seals as seals_router
from .routers import relations as relations_router
from .routers import pdf_records as pdf_records_router

log = logging.getLogger("feicui.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

API_VERSION = "1c-activate"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动补跑（阶段 1c-激活）：库里有 `QUEUED`/`RUNNING` 的 job ⇒ 异步拉一次池。

    防「API 重启后 job 被遗忘」：池是不常驻的（跑完即退），重启前在跑的 job 会留在
    `QUEUED`/`RUNNING`，若没人再拉池就会永远停住。此处只**派发**拉起动作（daemon 线程 +
    detached 子进程），**不阻塞** uvicorn 起服务。

    另加 **inbox 启动扫描**（R41）：**只 dry-run 扫描 + 落报告/告警**，**绝不删任何文件**
    （策略铁律 ②：系统无任何自动删除路径；真删只能由人 `--apply` / `POST /api/jobs/inbox/gc`）。
    """
    try:
        inbox_gc.startup_scan(get_settings())
    except Exception as exc:  # 扫描侧任何异常都不得挡住 API 起服务
        log.warning("inbox 启动扫描失败（API 照常起服务；**未删任何文件**）：%r", exc)
    try:
        poolctl.catch_up_on_startup(get_settings())
    except Exception as exc:  # 拉起侧任何异常都不得挡住 API 起服务
        log.warning("启动补跑失败（API 照常起服务）：%r", exc)
    yield


def create_app() -> FastAPI:
    st = get_settings()
    app = FastAPI(
        title="feicui API（薄接口层）",
        version=API_VERSION,
        description="印谱 PDF 解析工具 feicui 的接口层（1a：E1/E2/E5；1b-ii：E3/E4/E6/E7）。",
        lifespan=lifespan,
    )

    # 前端 5195 → 接口层 5196 属**跨 origin 的本地 dev 调用**（规范 §1.1 两进程分离）；
    # 玺爱 5163（`POST /api/tools/square-crop` 的调用方）同属本地 dev 跨 origin。
    # 允许来源的**唯一真源**＝`Settings.cors_origins`（默认 DEFAULT_CORS_ORIGINS：5195 ＋ 5163；
    # `FEICUI_CORS_ORIGINS` 可整体覆盖）；端点侧不再散落硬编码，也**不放开 `*`**。
    origins = list(st.cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(jobs_router.router)
    app.include_router(tools_router.router)
    # 印人采集线（批 1）——additive 端点，不动 E1〜E7（拆解件 §4.2）
    app.include_router(persons_router.router)
    # 印谱采集线（批 1）——additive 端点，不动 E1〜E7 与 persons（拆解件 §4）
    app.include_router(items_router.router)
    # 印章采集线（批 1）——additive 端点，不动 E1〜E7 与 persons/items
    app.include_router(seals_router.router)
    # 关联面（三表联立）——additive 端点，不动 E1〜E7 与 persons/items/seals（规范 §3.18.6）
    app.include_router(relations_router.router)
    # PDF 资料登记（output 四总目录落地单）——additive 端点；独立库 var/pdf_registry.db（不碰 yinpu.db）
    app.include_router(pdf_records_router.router)

    # ---- 领域异常 → §3.4 错误体（**必须含 `detail`**；不得以 200 承载失败）----
    # `repository.JobNotFound` 由仓库层直抛（E3 / E4 / E6 都可能命中），在此统一落 404，
    # 避免任何路由漏 catch 而被框架当成 500。
    @app.exception_handler(repository.JobNotFound)
    def _job_not_found(_request, exc: repository.JobNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "JOB_NOT_FOUND", "detail": f"job 不存在：{exc}"})

    @app.exception_handler(repository.BadCursor)
    def _bad_cursor(_request, exc: repository.BadCursor) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "BAD_PARAM", "detail": str(exc)})

    @app.get("/api/health", tags=["meta"])
    def health() -> JSONResponse:
        """骨架存活探针（**非规范 §3 端点**，只用于自测就绪判定与运维）。"""
        payload: dict = {
            "ok": False,
            "api_version": API_VERSION,
            "db_path": str(st.db_path),
            "db_exists": st.db_path.is_file(),
            "prod_db": st.is_prod_db,
            "root": str(st.root),
            "time": db.now_iso(),
            "tables_present": {},
            "journal_mode": None,
        }
        if payload["db_exists"]:
            try:
                conn = db.connect(st.db_path)
                try:
                    payload["journal_mode"] = conn.execute("PRAGMA journal_mode").fetchone()[0]
                    for t in ("stamps", "jobs", "job_pages"):
                        payload["tables_present"][t] = db.table_exists(conn, t)
                    payload["ok"] = all(payload["tables_present"].values())
                finally:
                    conn.close()
            except Exception as exc:  # pragma: no cover - 探针不抛，回报即可
                payload["error"] = str(exc)
        return JSONResponse(payload)

    @app.get("/api/meta/migrations", tags=["meta"])
    def migrations_status() -> JSONResponse:
        """迁移记账（只读）：`schema_migrations` 现况 + `sqlite_master` 指纹。"""
        out: dict = {"db_path": str(st.db_path), "prod_db": st.is_prod_db, "applied": [], "schema_sha256": None}
        if st.db_path.is_file():
            conn = db.connect(st.db_path)
            try:
                if db.table_exists(conn, "schema_migrations"):
                    out["applied"] = [
                        dict(r)
                        for r in conn.execute(
                            "SELECT version, applied_at FROM schema_migrations ORDER BY version"
                        )
                    ]
                out["schema_sha256"] = db.schema_fingerprint(conn)
            finally:
                conn.close()
        return JSONResponse(out)

    @app.get("/api/meta/pool", tags=["meta"])
    def pool_status() -> JSONResponse:
        """执行层自检（**只读**，非规范 §3 端点）：池是否在跑 + 拉起日志 + 库内活跃 job。

        阶段 1c-激活新增：面板只托管**端口服务**，池是无端口进程（不入 `services` 表，`PORTS.md` P9），
        故它的现况只能这样读——**不臆造读数**（池在跑与否由 `flock` 探测，活跃 job 由库内复算）。
        """
        out: dict = {"db_path": str(st.db_path), "prod_db": st.is_prod_db}
        try:
            out.update(poolctl.status(st))
        except Exception as exc:  # pragma: no cover - 探针不抛，回报即可
            out["error"] = str(exc)
        return JSONResponse(out)

    log.info(
        "feicui-api(%s) 就绪：db=%s prod_db=%s root=%s chunk_size=%s export_root=%s",
        API_VERSION,
        st.db_path,
        st.is_prod_db,
        st.root,
        st.chunk_size,
        st.export_root,
    )
    return app


app = create_app()


def main() -> None:
    import uvicorn  # 延迟导入：仅 `python -m app.main` 路径需要

    st = get_settings()
    uvicorn.run("app.main:app", host=st.host, port=st.port, log_level="info")


if __name__ == "__main__":
    main()
