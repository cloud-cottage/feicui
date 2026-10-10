"""`/api/relations/*` 路由（**关联面 · 三表联立**）—— Kong。

端点一律 **additive**（不动 E1〜E7 与 persons / items / seals）：

  * `POST /api/relations/package` —— 从三库联立、**重建 xiai 就绪包**（**零联网**；不联网采集）
  * `GET  /api/relations/summary` —— 关联面摘要（**只读**：各 predicate 计数 / 三表行数 / 去重前后 / 未命中·幽灵）

纪律：
  * 本文件**不含任何 SQL**，一切读数走 `..relations`；
  * **不新建任何 DB**（红线「只读三库」）；只写 feicui 自有树内就绪包；
  * 规范锚点 ＝ `docs/feicui.spec.md` §3.18.6（T1 / T2）。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import relations
from ..config import Settings, get_settings

log = logging.getLogger("feicui.api.relations.router")

router = APIRouter(prefix="/api/relations", tags=["relations"])


def _settings() -> Settings:
    return get_settings()


def _reject_unsupported_query(request: Request, allowed: frozenset[str]) -> None:
    """未白名单查询参数 ⇒ **400 结构化 JSON**（绝不静默忽略）。"""
    unsupported = sorted(k for k in request.query_params.keys() if k not in allowed)
    if unsupported:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "UNSUPPORTED_PARAM",
                "detail": f"不支持的查询参数：{unsupported}。支持的参数：{sorted(allowed)}",
                "unsupported": unsupported,
                "supported": sorted(allowed),
            },
        )


@router.post("/package")
def create_package(
    request: Request,
    batch_id: str | None = Query(default=None, description="批次号（缺省＝既有最新批次；无则当日默认名）"),
    st: Settings = Depends(_settings),
) -> dict:
    """`POST /api/relations/package` —— 生成 **xiai 就绪包**（**从三库联立重建，零联网**）。

    产物目录 `exports/relation_import_<batch_id>/`：`relations.jsonl` ＋ `manifest.json`
    （`key_face_status: "pending_xiai"`）＋ `report.json`。

    * **零联网**：只读 `var/person_ingest.db` / `var/item_ingest.db` / `var/seal_ingest.db`，不打源站；
    * **不写 xiai 任何文件、不调任何云函数**；
    * 未白名单查询参数 ⇒ **400**（`UNSUPPORTED_PARAM`）；给出 `batch_id` 但批次不存在 ⇒ **404**
      （`BATCH_NOT_FOUND`）。
    """
    _reject_unsupported_query(request, frozenset({"batch_id"}))
    try:
        pkg = relations.write_package_from_db(
            st.person_db_path, st.items_db_path, st.seals_db_path,
            st.relations_export_root, batch_id=(batch_id or None), create=False,
        )
    except relations.ImportPackageError as exc:
        status = 404 if exc.code in {"BATCH_NOT_FOUND", "NO_BATCH"} else 409
        raise HTTPException(status_code=status, detail={"error": exc.code, "detail": str(exc)})
    summary = pkg["summary"]
    log.info("xiai 就绪包已生成（relation）：batch_id=%s rows=%s dir=%s",
             summary["batch_id"], summary["rows"], summary["package_dir"])
    return summary


@router.get("/summary")
def summary(request: Request, st: Settings = Depends(_settings)) -> dict:
    """`GET /api/relations/summary` —— 关联面摘要（**只读、不重建包、不落盘**）。

    给：各 `predicate` 计数 / 三表行数 / 去重前后计数 / 未命中·幽灵计数。非白名单参数一律 **400**。
    """
    _reject_unsupported_query(request, frozenset())
    out = relations.summary_only(st.person_db_path, st.items_db_path, st.seals_db_path)
    out["_db_paths"] = {
        "person": str(st.person_db_path),
        "item": str(st.items_db_path),
        "seal": str(st.seals_db_path),
    }
    return out
