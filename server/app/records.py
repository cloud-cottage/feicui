"""E3 记录形状层（阶段 1b-ii）——Kong。

**规范锚点**：§3.1 E3（`items[]` 为实体数组）、§3.2 S-3（字段封闭只管信封）、
§3.3（每条记录必须能给出平台 §9.3 的 **必填 11 项**，缺失时须附带**可解释的缺失原因**，口径与
`exports/selfcheck_report.json` 的 `requiredCoverage` 一致）、§7 **AC-08**。

**形状真源＝F1 交付物**：`feicui/export.py::build_record` 产出的记录对象（平台字段名为顶层键 +
内嵌 `assets[]` + feicui 专有信息收在 `feicui` 子对象），它已逐条带 `feicui.missingRequired`。

**本层不做**（纪律）：
  * 不 import `export.py`、不 import PyMuPDF / Pillow / OpenCV —— §6.5「接口层不装 OCR / 图像栈」
    （`export.py` 的 `build_record` 会调 PIL / cv2 生成本层不需要的派生值）；
  * 不**重新实现** §9.3 的派生逻辑（避免第二份真源）：有 `seals.record_json` 的行**原样**取用；
  * 不读影像字节、不写任何文件（§3.5 只读纪律的同一精神）。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from . import db

log = logging.getLogger("feicui.api.records")

# §9.3 **必填 11 项**的 feicui 语义名（顺序照 export.py 的 REQUIRED_KEYS；
# 自测 `selftest/verify_1b_ii.py` 会与 `export.py` 的常量**逐项断言相等**，防手工抄错）。
REQUIRED_KEYS = (
    "seal_name",
    "dynasty",
    "seal_type",
    "asset_kind",
    "source_book",
    "source_page_no",
    "seal_code",
    "sha256",
    "image_metrics",
    "review_status",
    "batch_id",
)

# 供「尚未导出过」的行构造壳记录：平台字段名 → 本层可否凭空派生
SHELL_NOTE = (
    "该行尚未被 F1 导出过（`seals` 侧表无对应 `record_json`）⇒ §9.3 派生字段未生成；"
    "E3 只回可凭 `stamps` 直读的字段，其余逐项列在 `missing_required`，"
    "不臆造值（§3.7 纪律：不得用替代值冒充真数据）。"
)


def _json_field(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except Exception:  # pragma: no cover - 脏数据兜底
        return None


def _shell_record(row: dict[str, Any], *, file_exists: bool) -> dict[str, Any]:
    """未导出行的壳记录：**键集与 build_record 同形**，值只填能直读的，缺的进 `missing_required`。"""
    text = (row.get("text") or "").strip()
    img_rel = row.get("img_path")
    page = int(row["page"])
    idx = int(row["idx"])
    present = {
        "seal_name": bool(text),
        "dynasty": False,
        "seal_type": False,
        "asset_kind": True,  # 'FACE' 是行级常量（§9.3 #6）
        "source_book": False,  # 书本身份须按导出侧口径归一化，本层不重算
        "source_page_no": page >= 1,
        "seal_code": False,
        "sha256": False,  # 本层不读影像字节（只读 DB）
        "image_metrics": False,
        "review_status": True,
        "batch_id": False,
    }
    missing = [k for k in REQUIRED_KEYS if not present.get(k)]
    return {
        "sealCode": None,
        "sealName": text or None,
        "transcription": text or None,
        "dynasty": None,
        "sealType": None,
        "sourceBook": None,
        "sourcePageNo": page if page >= 1 else None,
        "bbox": {
            "x1": row.get("x1"),
            "y1": row.get("y1"),
            "x2": row.get("x2"),
            "y2": row.get("y2"),
            "unit": "px(unknown_dpi)",
        },
        "reviewStatus": "DRAFT",
        "dedupeKey": None,
        "assets": [
            {
                "kind": "FACE",
                "seq": idx,
                "batchId": None,
                "sha256": None,
                "bytes": None,
                "width": None,
                "height": None,
                "colorMode": None,
                "mimeType": None,
                "sourceImgPath": img_rel,
                "fileExists": file_exists,
            }
        ],
        "feicui": {
            "stampId": int(row["id"]),
            "stampIdx": idx,
            "pdfName": row.get("pdf_name"),
            "pageNoBase": 1,
            "recordSource": "shell(stamps-only)",
            "missingRequired": missing,
            "note": SHELL_NOTE,
        },
        "missing_required": missing,
    }


def build_items(
    db_path: Path | str,
    rows: list[dict[str, Any]],
    *,
    root: Path,
    print_size_1to1: bool | None = None,
    render_dpi: float | None = None,
) -> list[dict[str, Any]]:
    """把 E3 的 `stamps` 行批量扩成记录对象（**两条路径**）：

    1. **有 `seals.record_json`** ⇒ 原样取用（F1 权威形态，含 `feicui.missingRequired`）；
    2. **无**（该行尚未导出）⇒ `_shell_record`：只回可直读的字段 + 逐项 `missing_required`。

    `os.path.exists` 只用于壳记录的 `assets[0].fileExists`（**只读**文件系统，不建不写）。

    **`size_mm`（additive，2026-10，Kevin ②「印刷尺寸即实物尺寸」下游闭环）**：
    `print_size_1to1=True` 时逐条挂**顶层** `size_mm = {width_mm, height_mm, dpi, basis}`
    （bbox px ÷ 渲染 dpi × 25.4，`print_size.size_mm_for_bbox`；bbox 缺角 ⇒ 该条**不挂** `size_mm` 键）。
    `print_size_1to1=None`（调用方未判定）或 False ⇒ 不挂该键（响应形状与既有完全一致）。
    """
    if not rows:
        return []
    ids = [int(r["id"]) for r in rows]
    by_id: dict[int, dict[str, Any]] = {}
    with db.ro(db_path) as conn:
        if db.table_exists(conn, "seals"):
            chunk = 400  # 参数上限保护（SQLite 变量数）
            for i in range(0, len(ids), chunk):
                part = ids[i : i + chunk]
                rows_ = db.query_all(
                    conn,
                    f"""SELECT stamp_id, record_json, missing_required FROM seals
                         WHERE stamp_id IN ({','.join('?' * len(part))})""",
                    part,
                )
                for r in rows_:
                    by_id[int(r["stamp_id"])] = dict(r)

    def _size_mm_for(row: dict[str, Any]) -> dict[str, Any] | None:
        if not print_size_1to1:
            return None
        from . import print_size as _print_size  # 延迟导入：纯 stdlib，仅本开关用到才加载

        return _print_size.size_mm_for_bbox(
            row.get("x1"), row.get("y1"), row.get("x2"), row.get("y2"),
            dpi=render_dpi if render_dpi is not None else _print_size.RENDER_DPI,
        )

    items: list[dict[str, Any]] = []
    for row in rows:
        hit = by_id.get(int(row["id"]))
        raw = _json_field(hit["record_json"]) if hit else None
        if isinstance(raw, dict):
            item = raw
            # 逐条带 missing_required（AC-08 的可判负面）——顶层键便于机械校验，值取自 record_json
            fed = item.get("feicui") or {}
            if "missing_required" not in item:
                item["missing_required"] = _json_field(fed.get("missingRequired")) or []
        else:
            if hit is not None and raw is None and hit.get("record_json"):
                log.warning("seals.record_json 解析失败（stamp_id=%s）⇒ 回退壳记录", row["id"])
            img_rel = row.get("img_path")
            exists = bool(img_rel) and (Path(root) / str(img_rel)).is_file()
            item = _shell_record(row, file_exists=exists)
        smm = _size_mm_for(row)
        if smm is not None:
            item["size_mm"] = smm
        items.append(item)
    return items
