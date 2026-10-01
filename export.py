#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""feicui 汇入线 F1：承载规范 §9.3 全 17 项字段（必填 11 项）并产出批次导出包。

设计原则（硬约束：不破坏现有解析管线）
------------------------------------------------------------------
1. 纯加法。既有 `stamps` 表、`processor.py` 解析流程、`output/**` 产物一律**只读**：
   本模块只做 `SELECT`，不执行任何 UPDATE/DELETE/ALTER，也不在 `output/` 下写文件。
2. 新增 4 张侧表（`seals` / `images` / `export_batches` / `export_records`），
   用 `CREATE TABLE IF NOT EXISTS` 建立，与 `stamps` 通过 `stamp_id` 弱引用关联；
   既有 65 条记录不被改写（`stamps` 全程只读，自检脚本另附快照 diff 佐证）。
3. 导出层独立：`exports/<batch_id>/{manifest,report}.json + seals.jsonl + draft.jsonl + images/`。
   一本书 = 一个 batch_id（`fb_YYYYMMDD_<书简码>_NN`）。

字段与映射（照 §9.3「对应平台字段」列，不自造平台字段名）
------------------------------------------------------------------
导出 JSONL 一行 = 一条 Seal（平台字段名为顶层键）+ 内嵌 `assets` 数组（ImageAsset）。
feicui 侧专有信息（抽取来源、批次状态、原始像素 bbox 等）收在 `feicui` 子对象里，
不污染平台字段。§9.3 逐项见 `FIELD_SPECS`。

必填缺失处理（§9.3 尾注 + §9.5）
------------------------------------------------------------------
必填缺失或 `sealType=UNKNOWN` 或 `sealCode` 未签发 ⇒ `reviewStatus=DRAFT`，
只进 `draft.jsonl`（暂存），**不进** `seals.jsonl`（正式包）。

坐标系（实测，非推测）
------------------------------------------------------------------
`stamps.x1y1x2y2` 是**页内像素坐标**，且**渲染 DPI 逐书不同**（旧版 144dpi / 现版 400dpi）。
`export.py calibrate` 通过「按候选 DPI 重新渲染 + 重跑红色检测 + 与库内 bbox 逐值比对」
实测出每本书的 `coord_dpi`（见 `config/book_geometry.json` 的 evidence），
据此换算点位（pt）、相对比例 bbox 与 `dedupe_key` 的 1pt 量化 bbox。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _env_path(name: str, default: Path) -> Path:
    """允许用环境变量把数据/配置/导出根重定向（自检脚本用临时沙箱跑逻辑自测，不动真实库）。"""
    val = os.environ.get(name)
    return Path(os.path.expanduser(val)) if val else default


DB_PATH = _env_path("FEICUI_DB", ROOT / "yinpu.db")
CONFIG_DIR = _env_path("FEICUI_CONFIG_DIR", ROOT / "config")
TEMPLATES_PATH = CONFIG_DIR / "templates.json"
BOOK_CODES_PATH = CONFIG_DIR / "book_codes.json"
GEOMETRY_PATH = CONFIG_DIR / "book_geometry.json"
EXPORT_ROOT = _env_path("FEICUI_EXPORT_ROOT", ROOT / "exports")

SCHEMA_VERSION = "yinsuo.feicui.seal.v1"
REPORT_SCHEMA_VERSION = "yinsuo.feicui.export.report.v1"
TOOL_VERSION = "feicui-export-f1.0"

# §9.3 十七项（field_key 为 feicui 侧语义名；platform 为「对应平台字段」列原文）
FIELD_SPECS = [
    {"no": 1, "key": "seal_name", "platform": "Seal.sealName", "type": "string", "required": True},
    {"no": 2, "key": "dynasty", "platform": "Seal.dynasty", "type": "string", "required": True},
    {"no": 3, "key": "material", "platform": "Seal.material", "type": "string", "required": False},
    {"no": 4, "key": "seal_type", "platform": "Seal.sealType", "type": "enum(5)", "required": True},
    {"no": 5, "key": "seal_style", "platform": "Seal.sealStyle", "type": "enum", "required": False},
    {"no": 6, "key": "asset_kind", "platform": "ImageAsset.kind", "type": "enum", "required": True},
    {"no": 7, "key": "source_book", "platform": "Seal.sourceBook", "type": "string", "required": True},
    {"no": 8, "key": "source_page_no", "platform": "Seal.sourcePageNo", "type": "int", "required": True},
    {"no": 9, "key": "seal_code", "platform": "Seal.sealCode", "type": "string", "required": True},
    {"no": 10, "key": "sha256", "platform": "ImageAsset.sha256", "type": "string", "required": True},
    {"no": 11, "key": "image_metrics", "platform": "ImageAsset.(bytes|width|height|colorMode)", "type": "int/enum", "required": True},
    {"no": 12, "key": "ocr_audit", "platform": "Seal.ext.{ocrConfidence,ocrEngine}", "type": "float/string", "required": False},
    {"no": 13, "key": "review_status", "platform": "Seal.reviewStatus", "type": "enum", "required": True},
    {"no": 14, "key": "batch_id", "platform": "Seal.batchId / ImageAsset.batchId", "type": "string", "required": True},
    {"no": 15, "key": "source_bbox", "platform": "Seal.bbox", "type": "object", "required": False},
    {"no": 16, "key": "rights_status", "platform": "Seal.rightsStatus", "type": "enum", "required": False},
    {"no": 17, "key": "size_mm", "platform": "Seal.sizeMm", "type": "object", "required": False},
]
REQUIRED_KEYS = [f["key"] for f in FIELD_SPECS if f["required"]]

# 规范许可的「哨兵值」：有值但需人工判定（§9.3 #3 / #4）
SENTINELS = {"seal_type": {"UNKNOWN"}, "material": {"UNKNOWN"}, "rights_status": {"UNKNOWN"}}

# 同名/别名说明：tmp.pdf 是上传通道落盘的临时名（processor/app 均以 tmp.pdf 保存上传件），
# 其身份线索见 config/book_codes.json 的 identity_alias_* 字段（**不自动采信**）。
UPLOAD_PLACEHOLDER_NAMES = re.compile(r"^(tmp|temp|upload|untitled|new|\d+)$", re.I)

PUBLISHER_HINTS = ("出版社", "书局", "印社", "书画", "文物", "古籍", "书店", "美术", "美術", "书社")
JUNK_TOKENS = {"ok", "copy", "pdf", "上传", "副本", "终版", "定稿"}

# ---------------------------------------------------------------------------
# 配置读取
# ---------------------------------------------------------------------------


def load_json(path: Path, default):
    if not Path(path).exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_templates() -> dict:
    """既有模板（按 PDF 文件名 → 条目）。新键一律 .get() 取，缺省不报错。"""
    return load_json(TEMPLATES_PATH, {})


def load_book_codes() -> dict:
    return load_json(BOOK_CODES_PATH, {"schema": "yinsuo.feicui.book_codes.v1", "books": {}})


def load_geometry() -> dict:
    return load_json(GEOMETRY_PATH, {"schema": "yinsuo.feicui.book_geometry.v1", "books": {}})


def book_code_entry(pdf_name: str, codes: dict | None = None) -> dict:
    codes = codes or load_book_codes()
    return (codes.get("books") or {}).get(pdf_name) or {}


def template_for(pdf_name: str, templates: dict | None = None) -> tuple[dict, str | None]:
    """取本书模板条目。命中别名时返回 (条目, 别名来源书)。找不到返回 ({}, None)。

    注意：模板顶层是「PDF 文件名 → 条目」，条目内键名为 hsv_low/hsv_high/min_area/
    text_offset/density_min/density_max/page_range/edge_enabled/pad_ratio（磁盘事实）。
    """
    templates = templates if templates is not None else load_templates()
    ent = templates.get(pdf_name)
    if isinstance(ent, dict):
        return ent, None
    alias = book_code_entry(pdf_name).get("template_alias")
    if alias and isinstance(templates.get(alias), dict):
        return templates[alias], alias
    return {}, None


def geometry_for(book_key: str, geometry: dict | None = None) -> dict:
    geometry = geometry if geometry is not None else load_geometry()
    return (geometry.get("books") or {}).get(book_key) or {}


# ---------------------------------------------------------------------------
# 侧表（加法）
# ---------------------------------------------------------------------------

DDL = [
    """CREATE TABLE IF NOT EXISTS seals (
        id INTEGER PRIMARY KEY,
        stamp_id INTEGER NOT NULL,
        pdf_name TEXT NOT NULL,
        book_key TEXT,
        page INTEGER NOT NULL,
        idx INTEGER NOT NULL,
        batch_id TEXT NOT NULL,
        stage TEXT NOT NULL,
        seal_name TEXT, name_source TEXT,
        dynasty TEXT, dynasty_source TEXT,
        material TEXT,
        seal_type TEXT, seal_type_source TEXT,
        seal_style TEXT, seal_style_red_ratio REAL, seal_style_method TEXT,
        asset_kind TEXT,
        source_book TEXT, source_book_title TEXT, source_book_publisher TEXT,
        source_book_editor TEXT, source_book_year TEXT, source_book_source TEXT,
        source_page_no INTEGER,
        seal_code TEXT, seal_code_state TEXT, seal_code_candidate TEXT, short_code_source TEXT,
        review_status TEXT,
        bbox_x1 REAL, bbox_y1 REAL, bbox_x2 REAL, bbox_y2 REAL,
        bbox_unit TEXT, bbox_pt_x1 REAL, bbox_pt_y1 REAL, bbox_pt_x2 REAL, bbox_pt_y2 REAL,
        rel_x1 REAL, rel_y1 REAL, rel_x2 REAL, rel_y2 REAL,
        page_width_pt REAL, page_height_pt REAL, coord_dpi REAL,
        rights_status TEXT, size_mm_w REAL, size_mm_h REAL,
        ocr_engine TEXT, ocr_confidence REAL, transcription TEXT,
        dedupe_key TEXT,
        missing_required TEXT, draft_reasons TEXT, record_json TEXT,
        created_at TEXT, updated_at TEXT,
        UNIQUE(stamp_id)
    )""",
    """CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY,
        stamp_id INTEGER, seal_id INTEGER, batch_id TEXT,
        kind TEXT, seq INTEGER,
        src_path TEXT, package_path TEXT, file_exists INTEGER,
        sha256 TEXT, bytes INTEGER, width INTEGER, height INTEGER,
        color_mode TEXT, mime TEXT,
        bbox_x1 REAL, bbox_y1 REAL, bbox_x2 REAL, bbox_y2 REAL,
        rel_x1 REAL, rel_y1 REAL, rel_x2 REAL, rel_y2 REAL,
        created_at TEXT,
        UNIQUE(stamp_id, kind, seq)
    )""",
    """CREATE TABLE IF NOT EXISTS export_batches (
        batch_id TEXT PRIMARY KEY,
        seq INTEGER, batch_date TEXT,
        pdf_name TEXT, book_key TEXT,
        short_code TEXT, short_code_state TEXT,
        created_at TEXT, package_dir TEXT,
        total_records INTEGER, formal_records INTEGER, draft_records INTEGER,
        rejected_required_missing INTEGER,
        inserted_candidate INTEGER, updated_candidate INTEGER, skipped_duplicate_candidate INTEGER,
        counts_json TEXT, coverage_json TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS export_records (
        dedupe_key TEXT PRIMARY KEY,
        identity TEXT,
        seal_code_candidate TEXT,
        stage TEXT,
        first_batch_id TEXT, last_batch_id TEXT,
        first_seen_at TEXT, last_seen_at TEXT,
        seen_count INTEGER, sha256 TEXT
    )""",
]


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _rel(p: Path) -> str:
    """ROOT 相对路径；沙箱（导出根在 ROOT 之外）时退回绝对路径。"""
    try:
        return str(Path(p).relative_to(ROOT))
    except ValueError:
        return str(p)


def ensure_schema(conn: sqlite3.Connection) -> None:
    for ddl in DDL:
        conn.execute(ddl)
    conn.commit()


def stamps_snapshot(conn: sqlite3.Connection) -> list[dict]:
    """既有表的只读快照（自检脚本用它对帐：导出前后必须完全一致）。"""
    rows = conn.execute(
        "SELECT id, pdf_name, page, idx, text, img_path, x1, y1, x2, y2 FROM stamps ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 派生逻辑
# ---------------------------------------------------------------------------


def normalize_source_book(pdf_name: str) -> dict:
    """PDF 文件名 → 结构化来源书目（书名/出版社/编者 三段，§9.3 #7）。

    返回 {"source_book": str|None, "title":..., "publisher":..., "editor":..., "year":..., "source":...}
    """
    stem = re.sub(r"\.pdf$", "", pdf_name, flags=re.I)
    stem = re.sub(r"[（(][^）)]*(z-library|1lib|z-lib)[^）)]*[）)]", "", stem, flags=re.I)
    tokens = [t for t in re.split(r"[\s_]+", stem) if t.strip()]
    tokens = [t.strip("-_") for t in tokens]
    tokens = [t for t in tokens if t and t.lower() not in JUNK_TOKENS]
    year = None
    title = publisher = editor = None
    others: list[str] = []
    for tok in tokens:
        if re.fullmatch(r"(1[89]|20)\d{2}", tok):
            year = year or tok
            continue
        if publisher is None and any(h in tok for h in PUBLISHER_HINTS):
            publisher = tok
            continue
        if title is None:
            title = tok
            continue
        if editor is None and re.fullmatch(r"[\u4e00-\u9fff·]{2,6}", tok):
            editor = tok
            continue
        others.append(tok)
    if title is None or UPLOAD_PLACEHOLDER_NAMES.match(title):
        return {
            "source_book": None,
            "title": None,
            "publisher": publisher,
            "editor": editor,
            "year": year,
            "others": others,
            "source": "pdf_name_unusable(上传临时名/占位名，书本身份未知)",
        }
    parts = [p for p in (title, publisher, editor) if p]
    return {
        "source_book": " ".join(parts),
        "title": title,
        "publisher": publisher,
        "editor": editor,
        "year": year,
        "others": others,
        "source": "pdf_name_normalized",
    }


def quantize_bbox_pt(bbox_px, coord_dpi: float) -> tuple:
    """页内像素 bbox → 点位 bbox（1pt 量化；§9.4 的 quantize(bbox, 1pt)）。"""
    scale = 72.0 / float(coord_dpi)
    return tuple(int(round(float(v) * scale)) for v in bbox_px)


def compute_dedupe_key(source_book, source_page_no, bbox_pt, asset_kind) -> str | None:
    """§9.4: dedupe_key = sha256(sourceBook + '|' + sourcePageNo + '|' + quantize(bbox,1pt) + '|' + assetKind)"""
    if source_book is None or source_page_no is None or bbox_pt is None or not asset_kind:
        return None
    q = ",".join(str(int(v)) for v in bbox_pt)
    raw = f"{source_book}|{int(source_page_no)}|{q}|{asset_kind}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_metrics(path: Path) -> dict:
    """§9.3 #10/#11：sha256 + bytes/width/height/colorMode（Pillow 读取）。"""
    from PIL import Image

    with Image.open(path) as im:
        width, height = im.size
        mode = im.mode
        if mode in ("1", "L", "LA", "I;16"):
            color_mode = "BINARY"
        elif mode == "P":
            colors = im.getcolors(maxcolors=256)
            color_mode = "BINARY" if (colors is not None and len(colors) <= 2) else "PALETTE"
        else:
            colors = im.convert("RGB").getcolors(maxcolors=3)
            color_mode = "BINARY" if (colors is not None and len(colors) <= 2) else "COLOR"
    return {
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "width": int(width),
        "height": int(height),
        "color_mode": color_mode,
        "mime": "image/webp" if path.suffix.lower() == ".webp" else f"image/{path.suffix.lstrip('.').lower()}",
    }


def infer_seal_style(img_path: Path, template: dict) -> dict:
    """§9.3 #5：由二值/前景占比推断朱白。阈值取模板 style_red_ratio_threshold。

    口径（v1）：以模板 HSV 红色阈值统计裁剪图内红色前景占比 r。
    印面为朱色钤盖时：r 高 ⇒ 红底白字＝白文(阴文)；r 低 ⇒ 白底红字＝朱文(阳文)。
    """
    result = {"seal_style": None, "red_ratio": None, "method": None, "threshold": None}
    if not template or "hsv_low" not in template or "hsv_high" not in template:
        result["method"] = "skipped:no_template_hsv"
        return result
    try:
        import cv2
        import numpy as np

        buf = np.fromfile(str(img_path), dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            result["method"] = "skipped:decode_failed"
            return result
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(template["hsv_low"]), np.array(template["hsv_high"]))
        ratio = float(np.count_nonzero(mask)) / float(mask.size)
    except Exception as exc:  # pragma: no cover - 依赖本地 cv2
        result["method"] = f"skipped:error({exc.__class__.__name__})"
        return result
    threshold = float(template.get("style_red_ratio_threshold", 0.5))
    result.update(
        {
            "seal_style": "BAI_WEN" if ratio >= threshold else "ZHU_WEN",
            "red_ratio": round(ratio, 6),
            "method": template.get("style_inference_method", "red_ratio_v1"),
            "threshold": threshold,
        }
    )
    return result


def _ocr_engine_label() -> str:
    try:
        import importlib.metadata as md

        return f"paddleocr {md.version('paddleocr')}"
    except Exception:
        return "paddleocr (version unknown)"


# ---------------------------------------------------------------------------
# 单条记录构造
# ---------------------------------------------------------------------------


def build_record(stamp_row, template: dict, template_alias, code_entry: dict, geom: dict,
                 batch_id: str, sequence_class: str = "FACE") -> dict:
    """把一条 stamps 记录扩成 §9.3 全字段的 Seal(+ImageAsset) 记录（纯函数，不写盘）。"""
    stamp_id = int(stamp_row["id"])
    pdf_name = stamp_row["pdf_name"]
    page = int(stamp_row["page"])
    idx = int(stamp_row["idx"])
    text = (stamp_row["text"] or "").strip()
    img_rel = stamp_row["img_path"]
    img_path = Path(img_rel) if os.path.isabs(img_rel) else (ROOT / img_rel)
    bbox_px = (float(stamp_row["x1"]), float(stamp_row["y1"]), float(stamp_row["x2"]), float(stamp_row["y2"]))

    coord_dpi = geom.get("coord_dpi")
    pages_pt = (geom.get("pages_pt") or {}).get(str(page))
    source_page_no = page if page >= 1 else None

    # ---- 来源书目（§9.3 #7）
    sb = normalize_source_book(pdf_name)
    source_book = sb["source_book"]

    # ---- 印名（§9.3 #1）
    seal_name = text or None
    name_source = "OCR(stamps.text)" if text else None

    # ---- 朝代（§9.3 #2）：模板「本书默认朝代」（人工标注，加法键）
    #      经 template_alias 取到的条目视为**身份不可信**：只借用影像阈值类键
    #      （hsv_*/min_area/pad_ratio/style_*），不采信其身份类键（default_dynasty /
    #      default_seal_type）——除非 book_codes.json 显式 trust_alias_identity=true。
    trust_alias = bool(code_entry.get("trust_alias_identity"))
    alias_untrusted = bool(template_alias) and not trust_alias
    if alias_untrusted:
        dynasty = None
        dynasty_source = f"ignored:template_alias_identity_untrusted(alias={template_alias})"
    else:
        dynasty = template.get("default_dynasty")
        dynasty_source = template.get("default_dynasty_source") if dynasty else None

    # ---- 材质 / 玺印类型（§9.3 #3/#4）
    material = "UNKNOWN"
    if alias_untrusted:
        seal_type = "UNKNOWN"
        seal_type_source = "alias_identity_untrusted(不采信别名书的类型映射)"
    else:
        seal_type = template.get("default_seal_type", "UNKNOWN")
        seal_type_source = template.get("default_seal_type_source", "no_chapter_map(待人工章节映射)")

    # ---- 影像类型（§9.3 #6）
    asset_kind = "FACE"

    # ---- seal_code（§9.3 #9）
    short_code = code_entry.get("short_code")
    issued = bool(code_entry.get("issued"))
    seal_code_state = "ISSUED" if (issued and short_code) else "PENDING_ISSUE"
    seal_code_candidate = f"{short_code}-p{page:04d}-{idx:02d}" if short_code else None
    seal_code = seal_code_candidate if seal_code_state == "ISSUED" else None

    # ---- 影像派生字段（§9.3 #10/#11/#5）
    exists = img_path.exists()
    metrics = image_metrics(img_path) if exists else None
    style = infer_seal_style(img_path, template) if exists else {
        "seal_style": None, "red_ratio": None, "method": "skipped:image_missing", "threshold": None
    }

    # ---- bbox（§9.3 #15）：像素（源坐标空间）+ 点位 + 相对比例
    bbox_pt = quantize_bbox_pt(bbox_px, coord_dpi) if coord_dpi else None
    rel = None
    page_px = None
    if coord_dpi and pages_pt:
        page_px = (float(pages_pt[0]) * coord_dpi / 72.0, float(pages_pt[1]) * coord_dpi / 72.0)
        rel = (
            round(bbox_px[0] / page_px[0], 6), round(bbox_px[1] / page_px[1], 6),
            round(bbox_px[2] / page_px[0], 6), round(bbox_px[3] / page_px[1], 6),
        )

    # ---- dedupe_key（§9.4）
    dedupe_key = compute_dedupe_key(source_book, source_page_no, bbox_pt, asset_kind)

    # ---- 必填缺失 / DRAFT 判定（§9.3 尾注 + §9.5）
    present = {
        "seal_name": bool(seal_name),
        "dynasty": bool(dynasty),
        "seal_type": bool(seal_type),          # UNKNOWN 也算“有值”（哨兵）
        "asset_kind": bool(asset_kind),
        "source_book": bool(source_book),
        "source_page_no": bool(source_page_no),
        "seal_code": bool(seal_code),
        "sha256": bool(metrics),
        "image_metrics": bool(metrics),
        "review_status": True,
        "batch_id": bool(batch_id),
    }
    missing_required = [k for k in REQUIRED_KEYS if not present.get(k)]
    draft_reasons = [f"MISSING_REQUIRED:{k}" for k in missing_required]
    if seal_type == "UNKNOWN":
        draft_reasons.append("SEAL_TYPE_UNKNOWN(§9.3 #4：无法判定填 UNKNOWN 并置 DRAFT)")
    if seal_code_state == "PENDING_ISSUE":
        draft_reasons.append("SEAL_CODE_PENDING_ISSUE(书简码待平台签发回填，占位值不作为正式 sealCode)")
    if exists is False:
        draft_reasons.append(f"IMAGE_FILE_MISSING:{img_rel}")
    review_status = "DRAFT" if draft_reasons else "MACHINE_EXTRACTED"
    stage = "DRAFT" if review_status == "DRAFT" else "FORMAL"

    image_asset = {
        "kind": asset_kind,
        "seq": idx,
        "batchId": batch_id,
        "sha256": metrics["sha256"] if metrics else None,
        "bytes": metrics["bytes"] if metrics else None,
        "width": metrics["width"] if metrics else None,
        "height": metrics["height"] if metrics else None,
        "colorMode": metrics["color_mode"] if metrics else None,
        "mimeType": metrics["mime"] if metrics else None,
        "sourceImgPath": img_rel,
        "fileExists": exists,
        "bbox": {
            "x1": bbox_px[0], "y1": bbox_px[1], "x2": bbox_px[2], "y2": bbox_px[3],
            "unit": f"px@{coord_dpi}dpi" if coord_dpi else "px(unknown_dpi)",
            "pt": ({"x1": bbox_pt[0], "y1": bbox_pt[1], "x2": bbox_pt[2], "y2": bbox_pt[3]} if bbox_pt else None),
            "rel": ({"x1": rel[0], "y1": rel[1], "x2": rel[2], "y2": rel[3]} if rel else None),
        },
    }

    seal_obj = {
        "schemaVersion": SCHEMA_VERSION,
        "batchId": batch_id,
        "sealCode": seal_code,
        "sealName": seal_name,
        "transcription": text or None,
        "dynasty": dynasty,
        "material": material,
        "sealType": seal_type,
        "sealStyle": style["seal_style"],
        "sizeMm": None,
        "sourceBook": source_book,
        "sourcePageNo": source_page_no,
        "bbox": {
            "x1": bbox_pt[0] if bbox_pt else bbox_px[0],
            "y1": bbox_pt[1] if bbox_pt else bbox_px[1],
            "x2": bbox_pt[2] if bbox_pt else bbox_px[2],
            "y2": bbox_pt[3] if bbox_pt else bbox_px[3],
            "unit": "pt" if bbox_pt else "px(unknown_dpi)",
            "relX1": rel[0] if rel else None,
            "relY1": rel[1] if rel else None,
            "relX2": rel[2] if rel else None,
            "relY2": rel[3] if rel else None,
            "pageWidthPt": float(pages_pt[0]) if pages_pt else None,
            "pageHeightPt": float(pages_pt[1]) if pages_pt else None,
            "pageWidthPx": page_px[0] if page_px else None,
            "pageHeightPx": page_px[1] if page_px else None,
            "sourceCoordDpi": coord_dpi,
            "sourceAbsPx": {"x1": bbox_px[0], "y1": bbox_px[1], "x2": bbox_px[2], "y2": bbox_px[3]},
        },
        "rightsStatus": "UNKNOWN",
        "reviewStatus": review_status,
        "ext": {
            "ocrEngine": _ocr_engine_label() if text else None,
            "ocrConfidence": None,
            "ocrConfidenceNote": "PaddleOCR 置信度当前未落库（stamps 表无该列），保留 null 不臆造",
            "nameSource": name_source,
            "sealStyleEvidence": {
                "method": style["method"],
                "redRatio": style["red_ratio"],
                "threshold": style["threshold"],
            },
            "sizeMmNote": "书本无比例尺标注且未人工录入，留空（§9.3 #17 选填）",
        },
        "dedupeKey": dedupe_key,
        "assets": [image_asset],
        "feicui": {
            "toolVersion": TOOL_VERSION,
            "stampId": stamp_id,
            "stampIdx": idx,
            "pdfName": pdf_name,
            "bookKey": code_entry.get("key"),
            "templateAlias": template_alias,
            "pageNoBase": 1,
            "sealCodeState": seal_code_state,
            "sealCodeCandidate": seal_code_candidate,
            "sealCodeNote": ("书简码由平台首次汇入时签发并回填（§9.3 #9）；"
                             "未签发期间 sealCode 留 null，候选值仅作占位线索，不得当正式码使用"),
            "shortCodeSource": code_entry.get("short_code_source"),
            "templateAnnotationStatus": template.get("annotation_status"),
            "dynastySource": dynasty_source,
            "sealTypeSource": seal_type_source,
            "sourceBookParts": sb,
            "identityHints": {
                "templateAlias": template_alias,
                "aliasEvidence": code_entry.get("identity_alias_evidence"),
                "identityResolved": bool(source_book),
            },
            "missingRequired": missing_required,
            "draftReasons": draft_reasons,
            "stage": stage,
        },
    }
    return seal_obj


# ---------------------------------------------------------------------------
# 批次导出
# ---------------------------------------------------------------------------


def _batch_seq(conn: sqlite3.Connection, pdf_name: str, batch_date: str) -> int:
    row = conn.execute(
        "SELECT MAX(seq) AS s FROM export_batches WHERE pdf_name=? AND batch_date=?",
        (pdf_name, batch_date),
    ).fetchone()
    return int(row["s"] or 0) + 1


def make_batch_id(batch_date: str, code_entry: dict, seq: int) -> tuple[str, bool]:
    """fb_YYYYMMDD_<书简码>_NN；书简码未签发时用 X<本地KEY> 显式占位。"""
    short = code_entry.get("short_code")
    if short and code_entry.get("issued"):
        return f"fb_{batch_date}_{short}_{seq:02d}", False
    token = "X" + str(code_entry.get("key") or "BOOK")
    return f"fb_{batch_date}_{token}_{seq:02d}", True


# §9.3 每项在导出 JSONL 中的**键路径**（"*" 表示对 assets[] 展开），用于机械校验「17 项都真的在每条记录里」
FIELD_KEY_PATHS = {
    "seal_name": ["sealName"],
    "dynasty": ["dynasty"],
    "material": ["material"],
    "seal_type": ["sealType"],
    "seal_style": ["sealStyle"],
    "asset_kind": ["assets.*.kind"],
    "source_book": ["sourceBook"],
    "source_page_no": ["sourcePageNo"],
    "seal_code": ["sealCode"],
    "sha256": ["assets.*.sha256"],
    "image_metrics": ["assets.*.bytes", "assets.*.width", "assets.*.height", "assets.*.colorMode"],
    "ocr_audit": ["ext.ocrEngine", "ext.ocrConfidence"],
    "review_status": ["reviewStatus"],
    "batch_id": ["batchId", "assets.*.batchId"],
    "source_bbox": ["bbox"],
    "rights_status": ["rightsStatus"],
    "size_mm": ["sizeMm"],
}


def _path_present(rec: dict, path: str) -> tuple[bool, str]:
    """键路径是否存在（值可为 null；路径本身缺失才算问题）。支持 assets.* 展开。"""
    if "*" in path:
        head, _, tail = path.partition(".*.")
        arr = rec.get(head)
        if not isinstance(arr, list) or not arr:
            return False, f"{path}: 数组 {head}[] 缺失或为空"
        for i, item in enumerate(arr):
            if not isinstance(item, dict) or tail.split(".")[0] not in item:
                return False, f"{path}: 第 {i} 个元素缺 {tail}"
        return True, ""
    cur = rec
    for seg in path.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return False, f"{path}: 缺 {seg}"
        cur = cur[seg]
    return True, ""


def check_field_key_paths(records: list[dict]) -> dict:
    """校验每条导出记录都带齐 §9.3 十七项对应的键（值可为 null，但键必须在）。"""
    problems = {}
    for spec in FIELD_SPECS:
        paths = FIELD_KEY_PATHS[spec["key"]]
        bad = []
        for i, rec in enumerate(records):
            for path in paths:
                ok, msg = _path_present(rec, path)
                if not ok:
                    bad.append(f"line{i + 1}: {msg}")
                    break
        problems[spec["key"]] = {"paths": paths, "ok": not bad, "problems": bad[:3]}
    return {
        "specs": problems,
        "allOk": all(v["ok"] for v in problems.values()),
        "linesChecked": len(records),
        "fieldsChecked": len(FIELD_SPECS),
    }


def coverage_of(records: list[dict]) -> dict:
    cov = {}
    for spec in FIELD_SPECS:
        key = spec["key"]
        present = 0
        missing_examples = {}
        values = {}
        non_sentinel = 0
        for rec in records:
            is_present, value, reason = _field_presence(rec, key)
            if is_present:
                present += 1
                vs = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
                values[vs] = values.get(vs, 0) + 1
                if not (spec["key"] in SENTINELS and value in SENTINELS[spec["key"]]):
                    non_sentinel += 1
            else:
                missing_examples[reason] = missing_examples.get(reason, 0) + 1
        total = len(records)
        cov[key] = {
            "no": spec["no"],
            "platform": spec["platform"],
            "type": spec["type"],
            "required": spec["required"],
            "present": present,
            "missing": total - present,
            "total": total,
            "presentPct": round(100.0 * present / total, 2) if total else None,
            "presentNonSentinel": non_sentinel,
            "valueCounts": dict(sorted(values.items(), key=lambda kv: -kv[1])[:8]),
            "missingReasons": dict(sorted(missing_examples.items(), key=lambda kv: -kv[1])[:8]),
        }
    return cov


def _field_presence(rec: dict, key: str):
    assets = rec.get("assets") or [{}]
    a0 = assets[0]
    if key == "seal_name":
        return (bool(rec.get("sealName")), rec.get("sealName"), "OCR 释文为空（stamps.text 全空）")
    if key == "dynasty":
        return (bool(rec.get("dynasty")), rec.get("dynasty"), "模板无 default_dynasty（书本身份未知）")
    if key == "material":
        return (bool(rec.get("material")), rec.get("material"), "未判定")
    if key == "seal_type":
        return (bool(rec.get("sealType")), rec.get("sealType"), "未判定")
    if key == "seal_style":
        return (bool(rec.get("sealStyle")), rec.get("sealStyle"), "影像缺失或无法推断")
    if key == "asset_kind":
        return (bool(a0.get("kind")), a0.get("kind"), "无影像候选")
    if key == "source_book":
        return (bool(rec.get("sourceBook")), rec.get("sourceBook"), "pdf_name 为上传临时名，书本身份未知")
    if key == "source_page_no":
        return (bool(rec.get("sourcePageNo")), rec.get("sourcePageNo"), "页码缺失/非 1-based")
    if key == "seal_code":
        return (bool(rec.get("sealCode")), rec.get("sealCode"), "书简码未签发（sealCode 留 null）")
    if key == "sha256":
        return (bool(a0.get("sha256")), a0.get("sha256"), "影像文件缺失")
    if key == "image_metrics":
        ok = all(a0.get(k) is not None for k in ("bytes", "width", "height", "colorMode"))
        return (ok, {"bytes": a0.get("bytes"), "width": a0.get("width"),
                     "height": a0.get("height"), "colorMode": a0.get("colorMode")} if ok else None,
                "影像文件缺失")
    if key == "ocr_audit":
        return (bool(rec.get("ext", {}).get("ocrEngine")), rec.get("ext", {}).get("ocrEngine"), "无释文⇒未跑 OCR")
    if key == "review_status":
        return (bool(rec.get("reviewStatus")), rec.get("reviewStatus"), "派生失败")
    if key == "batch_id":
        return (bool(rec.get("batchId")), rec.get("batchId"), "批次缺失")
    if key == "source_bbox":
        return (bool(rec.get("bbox")), rec.get("bbox"), "缺页几何/坐标标定")
    if key == "rights_status":
        return (bool(rec.get("rightsStatus")), rec.get("rightsStatus"), "未标注")
    if key == "size_mm":
        return (bool(rec.get("sizeMm")), rec.get("sizeMm"), "书本无比例尺标注且未人工录入")
    return (False, None, "unknown field")


def export_book(pdf_name: str, seq: int | None = None, batch_date: str | None = None,
                out_root: Path | None = None, conn: sqlite3.Connection | None = None,
                verbose: bool = True) -> dict:
    """整书导出 = 一个 batch_id。返回该批次的报告 dict（并落 package + 侧表）。"""
    own_conn = conn is None
    conn = conn or connect()
    ensure_schema(conn)
    templates = load_templates()
    codes = load_book_codes()
    geometry = load_geometry()
    code_entry = book_code_entry(pdf_name, codes)
    template, template_alias = template_for(pdf_name, templates)
    key = code_entry.get("key") or "BOOK"
    geom = geometry_for(key, geometry)

    rows = conn.execute(
        "SELECT id, pdf_name, page, idx, text, img_path, x1, y1, x2, y2 FROM stamps "
        "WHERE pdf_name=? ORDER BY page, idx, id",
        (pdf_name,),
    ).fetchall()
    if not rows:
        raise SystemExit(f"没有该书的 stamps 记录：{pdf_name!r}")

    batch_date = batch_date or dt.datetime.now().strftime("%Y%m%d")
    seq = seq if seq is not None else _batch_seq(conn, pdf_name, batch_date)
    batch_id, placeholder_short_code = make_batch_id(batch_date, code_entry, seq)

    records = [build_record(r, template, template_alias, code_entry, geom, batch_id) for r in rows]

    # ---- 计数（§9.4 五项里 feicui 侧可判定的部分）
    ledger = {r["dedupe_key"]: dict(r) for r in conn.execute("SELECT * FROM export_records")}
    formal = [r for r in records if r["feicui"]["stage"] == "FORMAL"]
    draft = [r for r in records if r["feicui"]["stage"] == "DRAFT"]
    counts = {"insertedCandidate": 0, "updatedCandidate": 0, "skippedDuplicateCandidate": 0}
    for rec in formal:
        dk = rec["dedupeKey"]
        prev = ledger.get(dk)
        sha = (rec["assets"][0] or {}).get("sha256")
        if prev is None:
            counts["insertedCandidate"] += 1
        elif prev.get("sha256") != sha:
            counts["updatedCandidate"] += 1
        else:
            counts["skippedDuplicateCandidate"] += 1
    draft_new = sum(1 for rec in draft if rec["dedupeKey"] not in ledger)
    draft_repeat = len(draft) - draft_new
    rejected_required_missing = sum(1 for rec in records if rec["feicui"]["missingRequired"])

    # ---- 落包
    out_root = Path(out_root or EXPORT_ROOT)
    pkg = out_root / batch_id
    images_dir = pkg / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    for rec in records:
        asset = rec["assets"][0]
        src = ROOT / asset["sourceImgPath"] if not os.path.isabs(asset["sourceImgPath"]) else Path(asset["sourceImgPath"])
        if asset["fileExists"]:
            dst_name = f"p{int(rec['sourcePageNo'] or 0):04d}_{int(rec['feicui']['stampIdx']):02d}_{asset['kind']}{src.suffix}"
            dst = images_dir / dst_name
            shutil.copyfile(src, dst)
            try:
                asset["imgPath"] = str(dst.relative_to(ROOT))
            except ValueError:  # 沙箱导出根在 ROOT 之外（自检用）
                asset["imgPath"] = str(dst)
        else:
            asset["imgPath"] = None

    with open(pkg / "seals.jsonl", "w", encoding="utf-8") as f:
        for rec in formal:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=False) + "\n")
    with open(pkg / "draft.jsonl", "w", encoding="utf-8") as f:
        for rec in draft:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=False) + "\n")

    counts_feicui = {
        "total": len(records),
        "formal": len(formal),
        "draftStaged": len(draft),
        "rejectedRequiredMissing": rejected_required_missing,
        **counts,
        "draftNew": draft_new,
        "draftRepeatWithinLedger": draft_repeat,
        "dedupeKeysComputed": sum(1 for rec in records if rec["dedupeKey"]),
        "dedupeKeysNull": sum(1 for rec in records if not rec["dedupeKey"]),
        "dedupeKeysNullReason": ("sourceBook/sourcePageNo/bbox/kind 缺一即无法按 §9.4 公式计算："
                                 "书本身份未定（sourceBook 空）的条目 dedupe_key 为 null，"
                                 "待书本身份与书简码补齐后重跑即得。"),
    }
    counts_awaiting = {
        "inserted": "待平台回执",
        "updated": "待平台回执",
        "skipped": "待平台回执",
        "conflicted": "待平台回执",
        "note": ("§9.4 五项计数中，rejected 与 inserted/updated/skipped 的**候选**分类可由 feicui 侧判定"
                 "（*Candidate 字段，依据本地 export_records 账本）；权威的 inserted/updated/skipped/conflicted "
                 "须由平台按 §9.5 字段级优先级（人工复核值 > 平台维护值 > 机器抽取）判定后回执。"),
    }

    coverage = coverage_of(records)
    reasons: dict[str, int] = {}
    for rec in records:
        for r in rec["feicui"]["draftReasons"]:
            tag = r.split("(")[0].split(":")[0]
            reasons[tag] = reasons.get(tag, 0) + 1

    warnings = []
    if placeholder_short_code:
        warnings.append(
            f"书简码未签发：batch_id 用占位 token 'X{key}'，sealCode 全为 null ⇒ 本批次无正式条目（formal=0）。"
            "待平台签发简码并回填 config/book_codes.json（issued=true）后重跑即可出正式包。")
    missing_img = sum(1 for rec in records if not rec["assets"][0]["fileExists"])
    if missing_img:
        warnings.append(f"{missing_img}/{len(records)} 条影像文件在磁盘上不存在（img_path 指向已不存在的产物）⇒ 无法计算 sha256/尺寸。")
    if not geom.get("coord_dpi"):
        warnings.append("该书缺坐标标定（config/book_geometry.json）⇒ bbox 无点位/相对比例，dedupe_key 不可计算。")

    report = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "toolVersion": TOOL_VERSION,
        "batchId": batch_id,
        "batchSeq": seq,
        "generatedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "book": {
            "pdfName": pdf_name,
            "bookKey": key,
            "sourceBook": records[0]["sourceBook"],
            "shortCode": code_entry.get("short_code"),
            "shortCodeState": records[0]["feicui"]["sealCodeState"],
            "batchIdUsesPlaceholderShortCode": placeholder_short_code,
            "templateFound": bool(template),
            "templateAlias": template_alias,
            "coordDpi": geom.get("coord_dpi"),
            "coordDpiSource": geom.get("coord_dpi_source"),
        },
        "package": {
            "dir": _rel(pkg),
            "sealsJsonl": "seals.jsonl",
            "draftJsonl": "draft.jsonl",
            "imagesDir": "images",
            "manifest": "manifest.json",
            "report": "report.json",
        },
        "jsonl": {"sealsLines": len(formal), "draftLines": len(draft), "totalLines": len(records),
                  "imagesCopied": sum(1 for rec in records if rec["assets"][0]["fileExists"])},
        "counts": {"feicuiDecidable": counts_feicui, "awaitingPlatformReceipt": counts_awaiting},
        "draftReasonCounts": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "coverage": coverage,
        "warnings": warnings,
    }

    with open(pkg / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "schemaVersion": SCHEMA_VERSION,
                "reportSchemaVersion": REPORT_SCHEMA_VERSION,
                "toolVersion": TOOL_VERSION,
                "batchId": batch_id,
                "batchDate": batch_date,
                "batchSeq": seq,
                "deliveryUnit": "一本书 = 一个批次（规范 §9.6）",
                "generatedAt": report["generatedAt"],
                "book": report["book"],
                "jsonl": report["jsonl"],
                "counts": report["counts"],
                "warnings": warnings,
                "lineFormat": ("一行一条 Seal：平台字段名（§9.3「对应平台字段」列）为顶层键，内嵌 assets[] 为 ImageAsset；"
                               "feicui 侧抽取/批次元信息收在 feicui 子对象内。"),
            },
            f, ensure_ascii=False, indent=2,
        )
    with open(pkg / "report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # ---- 侧表落库（只动新表）
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    for rec in records:
        a0 = rec["assets"][0]
        bb = rec["bbox"]
        fk = rec["feicui"]
        conn.execute(
            """INSERT INTO seals (stamp_id, pdf_name, book_key, page, idx, batch_id, stage,
                seal_name, name_source, dynasty, dynasty_source, material, seal_type, seal_type_source,
                seal_style, seal_style_red_ratio, seal_style_method, asset_kind,
                source_book, source_book_title, source_book_publisher, source_book_editor,
                source_book_year, source_book_source, source_page_no,
                seal_code, seal_code_state, seal_code_candidate, short_code_source, review_status,
                bbox_x1, bbox_y1, bbox_x2, bbox_y2, bbox_unit,
                bbox_pt_x1, bbox_pt_y1, bbox_pt_x2, bbox_pt_y2,
                rel_x1, rel_y1, rel_x2, rel_y2, page_width_pt, page_height_pt, coord_dpi,
                rights_status, size_mm_w, size_mm_h, ocr_engine, ocr_confidence, transcription,
                dedupe_key, missing_required, draft_reasons, record_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(stamp_id) DO UPDATE SET
                batch_id=excluded.batch_id, stage=excluded.stage, seal_name=excluded.seal_name,
                name_source=excluded.name_source, dynasty=excluded.dynasty, dynasty_source=excluded.dynasty_source,
                material=excluded.material, seal_type=excluded.seal_type, seal_type_source=excluded.seal_type_source,
                seal_style=excluded.seal_style, seal_style_red_ratio=excluded.seal_style_red_ratio,
                seal_style_method=excluded.seal_style_method, asset_kind=excluded.asset_kind,
                source_book=excluded.source_book, source_book_title=excluded.source_book_title,
                source_book_publisher=excluded.source_book_publisher, source_book_editor=excluded.source_book_editor,
                source_book_year=excluded.source_book_year, source_book_source=excluded.source_book_source,
                source_page_no=excluded.source_page_no, seal_code=excluded.seal_code,
                seal_code_state=excluded.seal_code_state, seal_code_candidate=excluded.seal_code_candidate,
                short_code_source=excluded.short_code_source, review_status=excluded.review_status,
                bbox_x1=excluded.bbox_x1, bbox_y1=excluded.bbox_y1, bbox_x2=excluded.bbox_x2, bbox_y2=excluded.bbox_y2,
                bbox_unit=excluded.bbox_unit, bbox_pt_x1=excluded.bbox_pt_x1, bbox_pt_y1=excluded.bbox_pt_y1,
                bbox_pt_x2=excluded.bbox_pt_x2, bbox_pt_y2=excluded.bbox_pt_y2,
                rel_x1=excluded.rel_x1, rel_y1=excluded.rel_y1, rel_x2=excluded.rel_x2, rel_y2=excluded.rel_y2,
                page_width_pt=excluded.page_width_pt, page_height_pt=excluded.page_height_pt,
                coord_dpi=excluded.coord_dpi, rights_status=excluded.rights_status,
                size_mm_w=excluded.size_mm_w, size_mm_h=excluded.size_mm_h,
                ocr_engine=excluded.ocr_engine, ocr_confidence=excluded.ocr_confidence,
                transcription=excluded.transcription, dedupe_key=excluded.dedupe_key,
                missing_required=excluded.missing_required, draft_reasons=excluded.draft_reasons,
                record_json=excluded.record_json, updated_at=excluded.updated_at""",
            (
                fk["stampId"], pdf_name, key, int(rec["sourcePageNo"] or 0), fk["stampIdx"], batch_id, fk["stage"],
                rec["sealName"], rec["ext"]["nameSource"], rec["dynasty"], fk["dynastySource"], rec["material"],
                rec["sealType"], fk["sealTypeSource"], rec["sealStyle"],
                rec["ext"]["sealStyleEvidence"]["redRatio"], rec["ext"]["sealStyleEvidence"]["method"], a0["kind"],
                rec["sourceBook"], fk["sourceBookParts"]["title"], fk["sourceBookParts"]["publisher"],
                fk["sourceBookParts"]["editor"], fk["sourceBookParts"]["year"], fk["sourceBookParts"]["source"],
                rec["sourcePageNo"], rec["sealCode"], fk["sealCodeState"], fk["sealCodeCandidate"],
                fk["shortCodeSource"], rec["reviewStatus"],
                bb["sourceAbsPx"]["x1"], bb["sourceAbsPx"]["y1"], bb["sourceAbsPx"]["x2"], bb["sourceAbsPx"]["y2"],
                bb["unit"], rec["bbox"]["x1"], rec["bbox"]["y1"], rec["bbox"]["x2"], rec["bbox"]["y2"],
                rec["bbox"]["relX1"], rec["bbox"]["relY1"], rec["bbox"]["relX2"], rec["bbox"]["relY2"],
                rec["bbox"]["pageWidthPt"], rec["bbox"]["pageHeightPt"], bb["sourceCoordDpi"],
                rec["rightsStatus"], None, None,
                rec["ext"]["ocrEngine"], rec["ext"]["ocrConfidence"], rec["transcription"],
                rec["dedupeKey"], json.dumps(fk["missingRequired"], ensure_ascii=False),
                json.dumps(fk["draftReasons"], ensure_ascii=False),
                json.dumps(rec, ensure_ascii=False), now, now,
            ),
        )
        seal_id = conn.execute("SELECT id FROM seals WHERE stamp_id=?", (fk["stampId"],)).fetchone()["id"]
        conn.execute(
            """INSERT INTO images (stamp_id, seal_id, batch_id, kind, seq, src_path, package_path,
                 file_exists, sha256, bytes, width, height, color_mode, mime,
                 bbox_x1, bbox_y1, bbox_x2, bbox_y2, rel_x1, rel_y1, rel_x2, rel_y2, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(stamp_id, kind, seq) DO UPDATE SET
                 seal_id=excluded.seal_id, batch_id=excluded.batch_id, src_path=excluded.src_path,
                 package_path=excluded.package_path, file_exists=excluded.file_exists, sha256=excluded.sha256,
                 bytes=excluded.bytes, width=excluded.width, height=excluded.height,
                 color_mode=excluded.color_mode, mime=excluded.mime""",
            (
                fk["stampId"], seal_id, batch_id, a0["kind"], a0["seq"], a0["sourceImgPath"], a0.get("imgPath"),
                1 if a0["fileExists"] else 0, a0["sha256"], a0["bytes"], a0["width"], a0["height"],
                a0["colorMode"], a0["mimeType"],
                bb["sourceAbsPx"]["x1"], bb["sourceAbsPx"]["y1"], bb["sourceAbsPx"]["x2"], bb["sourceAbsPx"]["y2"],
                rec["bbox"]["relX1"], rec["bbox"]["relY1"], rec["bbox"]["relX2"], rec["bbox"]["relY2"], now,
            ),
        )
        dk = rec["dedupeKey"]
        if dk:
            conn.execute(
                """INSERT INTO export_records (dedupe_key, identity, seal_code_candidate, stage,
                     first_batch_id, last_batch_id, first_seen_at, last_seen_at, seen_count, sha256)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(dedupe_key) DO UPDATE SET
                     identity=excluded.identity, seal_code_candidate=excluded.seal_code_candidate,
                     stage=excluded.stage, last_batch_id=excluded.last_batch_id,
                     last_seen_at=excluded.last_seen_at, seen_count=export_records.seen_count+1,
                     sha256=excluded.sha256""",
                (dk, f"stamp:{fk['stampId']}", rec["feicui"]["sealCodeCandidate"], fk["stage"],
                 batch_id, batch_id, now, now, 1, a0["sha256"]),
            )
    conn.execute(
        """INSERT OR REPLACE INTO export_batches (batch_id, seq, batch_date, pdf_name, book_key,
             short_code, short_code_state, created_at, package_dir, total_records, formal_records,
             draft_records, rejected_required_missing, inserted_candidate, updated_candidate,
             skipped_duplicate_candidate, counts_json, coverage_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (batch_id, seq, batch_date, pdf_name, key, code_entry.get("short_code"),
         records[0]["feicui"]["sealCodeState"], now, _rel(pkg), len(records), len(formal),
         len(draft), rejected_required_missing, counts["insertedCandidate"], counts["updatedCandidate"],
         counts["skippedDuplicateCandidate"],
         json.dumps(counts_feicui, ensure_ascii=False), json.dumps(coverage, ensure_ascii=False)),
    )
    conn.commit()
    if own_conn:
        conn.close()
    if verbose:
        print(f"[export] {batch_id} → {_rel(pkg)}  formal={len(formal)} draft={len(draft)} total={len(records)}")
    return report


def export_all(batch_date: str | None = None, out_root: Path | None = None) -> list[dict]:
    conn = connect()
    ensure_schema(conn)
    books = [r["pdf_name"] for r in conn.execute("SELECT DISTINCT pdf_name FROM stamps ORDER BY pdf_name")]
    reports = [export_book(b, batch_date=batch_date, out_root=out_root, conn=conn) for b in books]
    conn.close()
    return reports


# ---------------------------------------------------------------------------
# 坐标标定（实测）
# ---------------------------------------------------------------------------

CALIBRATION_CANDIDATE_DPIS = [72, 100, 120, 144, 150, 180, 200, 240, 288, 300, 350, 400, 500, 600]


def calibrate_book(pdf_name: str, pdf_path: str, pages: list[int] | None = None,
                   candidates: list[int] | None = None) -> dict:
    """实测 coord_dpi：按候选 DPI 渲染 + 重跑红色检测 + 与库内 bbox 逐值比对（tolerance 3px）。

    复用既有解析逻辑的等价实现（HSV inRange → CLOSE 3x3 → findContours → area/aspect → pad），
    只是把渲染 DPI 与 min_area 的换算系数当变量扫。命中即「库内 bbox 由该 DPI 渲染产生」。
    """
    import cv2
    import numpy as np
    import pymupdf

    conn = connect()
    rows = conn.execute(
        "SELECT page, idx, x1, y1, x2, y2 FROM stamps WHERE pdf_name=? ORDER BY page, idx", (pdf_name,)
    ).fetchall()
    templates = load_templates()
    template, alias = template_for(pdf_name, templates)
    if not template or "hsv_low" not in template:
        raise SystemExit(f"{pdf_name!r} 无模板条目（hsv_low 缺失），无法标定")
    if pages is None:
        pages = sorted({r["page"] for r in rows})[:2]
    candidates = candidates or CALIBRATION_CANDIDATE_DPIS

    def detect_dpi(img, min_area, pad_ratio):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(template["hsv_low"]), np.array(template["hsv_high"]))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        H, W = img.shape[:2]
        out = []
        for c in cnts:
            if cv2.contourArea(c) < min_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            if not (0.6 < w / h < 1.6):
                continue
            px, py = int(w * pad_ratio), int(h * pad_ratio)
            out.append((max(0, x - px), max(0, y - py), min(W, x + w + px), min(H, y + h + py)))
        return sorted(out)

    doc = pymupdf.open(pdf_path)
    evidence = {"method": "render_at_candidate_dpi + red_redetect + exact_bbox_match(tol=3px)",
                "templateUsed": pdf_name if alias is None else f"{pdf_name} → alias {alias}",
                "pages": {}}
    per_page_best = {}
    match_pages: dict[int, set] = {}
    for pg in pages:
        want = {(round(r["x1"]), round(r["y1"]), round(r["x2"]), round(r["y2"]))
                for r in rows if r["page"] == pg}
        if len(want) < 3:
            continue
        page = doc[pg - 1]
        page_pt = [round(page.rect.width, 4), round(page.rect.height, 4)]
        page_ev = {"pageSizePt": page_pt, "want": len(want), "candidates": {}}
        for dpi in candidates:
            mat = pymupdf.Matrix(dpi / 72.0, dpi / 72.0)
            pix = page.get_pixmap(matrix=mat)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
            min_area = float(template.get("min_area", 800)) * ((dpi / 144.0) ** 2)
            got = detect_dpi(img, min_area, float(template.get("pad_ratio", 0.15)))
            exact = sum(1 for w_ in want if any(max(abs(a - b) for a, b in zip(w_, g)) <= 3 for g in got))
            page_ev["candidates"][str(dpi)] = {"detected": len(got), "exactMatch": exact}
            if exact == len(want):
                match_pages.setdefault(dpi, set()).add(pg)
        evidence["pages"][str(pg)] = page_ev

    # 全书页几何
    pages_pt = {}
    for pg in sorted({r["page"] for r in rows}):
        r = doc[pg - 1].rect
        pages_pt[str(pg)] = [round(r.width, 4), round(r.height, 4)]
    doc.close()

    best_dpi = None
    if match_pages:
        best_dpi = max(match_pages.items(), key=lambda kv: (len(kv[1]), kv[0]))[0]
    return {
        "coord_dpi": best_dpi,
        "coord_dpi_source": "measured" if best_dpi else "undetermined",
        "pdf_path": pdf_path,
        "pages_pt": pages_pt,
        "evidence": {**evidence, "fullMatchPages": {str(k): sorted(v) for k, v in match_pages.items()},
                     "testedPages": list(pages)},
    }


def cmd_calibrate(args) -> None:
    codes = load_book_codes()
    geometry = load_json(GEOMETRY_PATH, {"schema": "yinsuo.feicui.book_geometry.v1", "books": {}})
    geometry.setdefault("books", {})
    geometry["schema"] = "yinsuo.feicui.book_geometry.v1"
    targets = args.book or list(codes.get("books", {}).keys())
    for pdf_name in targets:
        entry = book_code_entry(pdf_name, codes)
        pdf_path = args.pdf or entry.get("pdf_path")
        if not pdf_path or not Path(os.path.expanduser(pdf_path)).exists():
            print(f"[calibrate] SKIP {pdf_name}: PDF 路径不可用（{pdf_path!r}）")
            continue
        res = calibrate_book(pdf_name, os.path.expanduser(pdf_path), pages=args.pages)
        key = entry.get("key") or pdf_name
        geometry["books"][key] = {
            "pdf_name": pdf_name,
            "pdf_path": os.path.expanduser(pdf_path),
            **{k: v for k, v in res.items() if k != "pdf_path"},
        }
        print(f"[calibrate] {pdf_name}: coord_dpi={res['coord_dpi']} ({res['coord_dpi_source']}) "
              f"pages_pt={len(res['pages_pt'])} fullMatch={res['evidence']['fullMatchPages']}")
    geometry["generatedAt"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    geometry["note"] = ("stamps.x1y1x2y2 是页内**像素**坐标，渲染 DPI 逐书不同（旧版 144dpi / 现版 400dpi）。"
                        "coord_dpi 由 export.py calibrate 实测（重渲染重检测 + 与库内 bbox 精确比对），"
                        "用于换算点位 bbox、相对比例 bbox 与 §9.4 dedupe_key 的 1pt 量化。")
    with open(GEOMETRY_PATH, "w", encoding="utf-8") as f:
        json.dump(geometry, f, ensure_ascii=False, indent=2)
    print(f"[calibrate] 写入 {_rel(GEOMETRY_PATH)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_export(args) -> None:
    if args.book:
        books = args.book
    else:
        conn = connect(); ensure_schema(conn)
        books = [r["pdf_name"] for r in conn.execute("SELECT DISTINCT pdf_name FROM stamps ORDER BY pdf_name")]
        conn.close()
    for b in books:
        export_book(b, seq=args.seq, batch_date=args.date)


def cmd_books(args) -> None:
    conn = connect(); ensure_schema(conn)
    codes = load_book_codes(); geometry = load_geometry()
    for r in conn.execute("SELECT pdf_name, COUNT(*) n, MIN(page) p0, MAX(page) p1 FROM stamps GROUP BY pdf_name ORDER BY pdf_name"):
        ent = book_code_entry(r["pdf_name"], codes)
        geom = geometry_for(ent.get("key") or "BOOK", geometry)
        print(f"- {r['pdf_name']!r}: rows={r['n']} pages={r['p0']}..{r['p1']} key={ent.get('key')} "
              f"short_code={ent.get('short_code')} issued={ent.get('issued')} coord_dpi={geom.get('coord_dpi')}")
    print(f"合计 {conn.execute('SELECT COUNT(*) c FROM stamps').fetchone()['c']} 条")
    conn.close()


def cmd_batches(args) -> None:
    conn = connect(); ensure_schema(conn)
    for r in conn.execute("SELECT * FROM export_batches ORDER BY created_at DESC"):
        print(f"- {r['batch_id']} book={r['book_key']} total={r['total_records']} formal={r['formal_records']} "
              f"draft={r['draft_records']} rejected={r['rejected_required_missing']} dir={r['package_dir']}")
    conn.close()


def cmd_issue_code(args) -> None:
    codes = load_book_codes()
    books = codes.setdefault("books", {})
    ent = books.setdefault(args.book, {})
    ent.setdefault("key", args.key or (args.book or "BOOK")[:12])
    ent["short_code"] = args.short_code
    ent["issued"] = True
    ent["issued_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    ent["issued_by"] = args.by or "platform"
    ent["short_code_source"] = args.source or "platform_issued_and_backfilled(§9.3 #9)"
    with open(BOOK_CODES_PATH, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False, indent=2)
    print(f"[issue-code] {args.book} → short_code={args.short_code} issued=True（已写回 {_rel(BOOK_CODES_PATH)}）")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="feicui 汇入线 F1：字段对齐 + 批次导出包")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("books", help="列出 stamps 中的书、书简码状态与坐标标定")
    p.set_defaults(func=cmd_books)

    p = sub.add_parser("calibrate", help="实测每本书的 coord_dpi（写 config/book_geometry.json）")
    p.add_argument("--book", action="append", help="限定书（可多次）；缺省扫全部")
    p.add_argument("--pdf", help="显式 PDF 路径（覆盖配置）")
    p.add_argument("--pages", type=int, nargs="*", help="指定测试页（缺省取该书前 2 页）")
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("export", help="整书导出（一本书 = 一个 batch_id，产 JSONL + 计数报告）")
    p.add_argument("--book", action="append", help="限定书（可多次）；缺省全部书各出一个批次")
    p.add_argument("--seq", type=int, help="批次序号（缺省按当日已有批次自增）")
    p.add_argument("--date", help="批次日期 YYYYMMDD（缺省今天）")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("batches", help="列出已导出批次")
    p.set_defaults(func=cmd_batches)

    p = sub.add_parser("issue-code", help="登记平台签发的书简码（issued=true 后 sealCode 方可正式签发）")
    p.add_argument("--book", required=True)
    p.add_argument("--short-code", required=True, dest="short_code")
    p.add_argument("--key")
    p.add_argument("--by")
    p.add_argument("--source")
    p.set_defaults(func=cmd_issue_code)

    args = ap.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
