"""本地上传印面导入（**seal-uploads 线**，Kevin 2026-10-13 单）——Kong。

把**本地已有的印面图片**（非复旦 API 采集）导入印章采集线：

  * `seals` **加法四列**：`dynasty` / `dynasty_source` / `author_name` / `source_kind`
    （DDL 唯一持有者＝`..seals` 的 `SCHEMA_SQL` ＋ `SEALS_EXTRA_COLUMNS`，本模块只消费）；
  * 新表 **`seal_uploads`**（upload_id / source_path / sha256 / width / height / o_path /
    canvas_path / meta_json / batch_id / created_at ＋ seq / filename / source_seal_id 溯源列）；
  * `record_upload`：原始字节落 `var/seal_uploads/<batch_id>/` ＋ 写 `seal_uploads` ＋ 写 `seals`
    （`source_kind='local_upload'`、`audit_status='UNREVIEWED_PENDING_HUMAN_REVIEW'`）；
  * **只加法**：既有 seals 行一字不改；同一 `(batch_id, sha256)` 重复导入 ⇒ 幂等 skip。

纪律（与接口层红线一致）：
  * 本模块**不 import fastapi / numpy / cv2**——只有 stdlib ＋ **PIL**（读尺寸用），
    在 `server/.venv` 与 `feicui/venv` 两个环境都可加载；
  * `yinpu.db` / `person_ingest.db` / `item_ingest.db` 一律不碰；
  * 朝代枚举真源＝**xiai**（15 种，`戰國` 等）；本侧**不复制枚举**，只如实记录
    `dynasty` ＋ `dynasty_source`（谁指定的）。
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from . import seals

__all__ = [
    "SOURCE_KIND", "UPLOAD_AUDIT_STATUS", "DEFAULT_CATEGORY",
    "MAX_FILE_BYTES", "MAX_TOTAL_BYTES", "MAX_FILES",
    "IMAGE_MAGICS", "seal_row_for_upload", "ensure_schema",
    "image_dimensions", "sniff_image_kind", "safe_filename",
    "next_batch_id", "record_upload", "list_uploads",
]

SOURCE_KIND = "local_upload"
UPLOAD_AUDIT_STATUS = "UNREVIEWED_PENDING_HUMAN_REVIEW"
DEFAULT_CATEGORY = "印章"

# 上传面限额（单点可改）：印面图量级 ≈ 0.1 MB/张；给足余量但不放开到 PDF 量级
MAX_FILE_BYTES = 16 * 1024 * 1024      # 单文件 16 MiB
MAX_TOTAL_BYTES = 64 * 1024 * 1024     # 单请求合计 64 MiB
MAX_FILES = 200                        # 单请求件数

IMAGE_MAGICS: tuple[tuple[str, bytes], ...] = (
    ("png", b"\x89PNG\r\n\x1a\n"),
    ("jpeg", b"\xff\xd8\xff"),
    ("tiff_le", b"II*\x00"),
    ("tiff_be", b"MM\x00*"),
)


class UploadError(ValueError):
    """上传校验失败（⇒ 400，可读 reason）。"""


# ── schema（DDL 唯一持有者＝..seals；本函数只做委托，供调用方显式表达意图）──────────────
def ensure_schema(db_path: Path | str) -> None:
    """建/补 `seal_uploads` 表与 seals 加法四列（幂等；真 DDL 在 `..seals.SCHEMA_SQL`）。"""
    seals.ensure_schema(db_path)


# ── 工具 ────────────────────────────────────────────────────────────────────────
def sniff_image_kind(data: bytes) -> str | None:
    """按魔数判图像容器（png/jpeg/tiff）；不认识 ⇒ None（⇒ 400）。"""
    for kind, magic in IMAGE_MAGICS:
        if data[: len(magic)] == magic:
            return kind
    return None


def image_dimensions(data: bytes) -> tuple[int, int]:
    """PIL 读尺寸（接口层只有 PIL——§6.5 解释器矩阵；解不开 ⇒ UploadError）。"""
    try:
        from PIL import Image  # type: ignore
        import io
        with Image.open(io.BytesIO(data)) as im:
            return int(im.width), int(im.height)
    except Exception as exc:  # noqa: BLE001
        raise UploadError(f"图像尺寸读取失败（非可解码图像？）：{exc!r}") from exc


def safe_filename(name: str) -> str:
    """文件名清毒：basename、剔路径分隔符/控制字符/`..`，保留中文；空 ⇒ `upload.png`。"""
    name = str(name or "").strip()
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = name.replace("..", "_")
    name = name.strip().lstrip(".")
    if not name:
        name = "upload.png"
    return name[:120]


def next_batch_id(db_path: Path | str) -> str:
    """`seal_upload_<yyyymmdd>_<NN>`（当日自增；同形不撞既有 batch_id）。"""
    conn = seals._connect(db_path)
    try:
        have = {r[0] for r in conn.execute("SELECT DISTINCT batch_id FROM seal_uploads")}
        have |= {r[0] for r in conn.execute("SELECT batch_id FROM seal_import_batches")}
    finally:
        conn.close()
    day = datetime.now().strftime("%Y%m%d")
    n = 1
    while f"seal_upload_{day}_{n:02d}" in have:
        n += 1
    return f"seal_upload_{day}_{n:02d}"


def source_seal_id_of(batch_id: str, seq: int) -> str:
    """`local_upload_20261013_01` 形（Kevin 2026-10-13 指定；日期段取 batch_id 里的 8 位日期）。

    ⚠ 同日多批：两批的 `source_seal_id` 会撞号（`local_upload_<date>_<seq>` 不含批次序号）⇒
    撞号时 `record_upload` 显式报 `UploadError`（**绝不覆盖既有行**）；届时请给 batch_id 用
    不同日期段（如跨日），id 规则如需含批次序号再立待裁。
    """
    m = re.search(r"(\d{8})", str(batch_id or ""))
    day = m.group(1) if m else "00000000"
    return f"local_upload_{day}_{int(seq):02d}"


# ── 落库 ────────────────────────────────────────────────────────────────────────
def _meta_json(**kw: Any) -> str:
    return json.dumps(kw, ensure_ascii=False, sort_keys=True)


def seal_row_for_upload(*, source_seal_id: str, dynasty: str, dynasty_source: str | None,
                        author_name: str | None, transcription: str, batch_id: str,
                        upload_id: str, filename: str, sha256: str, source_note: str | None) -> dict:
    """seals 新行（**只走 INSERT**，绝不 UPDATE 既有行）。

    `seal_wen`＝释文（**允许空串**＝Kevin「释文暂时留空」口径）；其余源侧字段一律 NULL。
    """
    return {
        "source_seal_id": source_seal_id,
        "category": DEFAULT_CATEGORY,
        "seal_wen": transcription if transcription is not None else "",
        "audit_status": UPLOAD_AUDIT_STATUS,
        "misc": _meta_json(kind=SOURCE_KIND, upload_id=upload_id, source_filename=filename,
                           sha256=sha256, batch_id=batch_id,
                           dynasty_source=dynasty_source, source_note=source_note),
        "raw_json": _meta_json(upload={"upload_id": upload_id, "source_filename": filename,
                                       "sha256": sha256, "batch_id": batch_id,
                                       "dynasty": dynasty, "dynasty_source": dynasty_source,
                                       "author_name": author_name, "transcription": transcription,
                                       "note": "本行＝本地上传导入；非复旦 API 采集，无源侧 list/detail/graph 行"}),
        "dynasty": dynasty,
        "dynasty_source": dynasty_source,
        "author_name": author_name,
        "source_kind": SOURCE_KIND,
        "batch_id": batch_id,
    }


def record_upload(db_path: Path | str, *, data: bytes, filename: str, batch_id: str, seq: int,
                  dynasty: str, dynasty_source: str | None = None,
                  author_name: str | None = None, transcription: str = "",
                  uploads_root: Path | str, source_note: str | None = None) -> dict:
    """单张上传导入（幂等）：落原始件 → `seal_uploads` 行 → `seals` 行（只 INSERT）。

    幂等口径：同 `batch_id` 内同 `sha256` 已在案 ⇒ `{"status":"skipped", ...}`，**不重写文件**；
    同 `source_seal_id` 已在 seals（异内容）⇒ `UploadError`（绝不覆盖既有行）。
    """
    if not isinstance(data, bytes) or not data:
        raise UploadError("文件内容为空")
    if len(data) > MAX_FILE_BYTES:
        raise UploadError(f"单文件超上限 {MAX_FILE_BYTES} bytes：{len(data)}")
    kind = sniff_image_kind(data)
    if kind is None:
        raise UploadError(f"不是可识别的图像容器（png/jpeg/tiff）：{filename!r}")
    width, height = image_dimensions(data)
    sha = hashlib.sha256(data).hexdigest()
    upload_id = f"up_{sha[:16]}"
    source_seal_id = source_seal_id_of(batch_id, seq)

    uploads_root = Path(uploads_root)
    batch_dir = uploads_root / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    conn = seals._connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        prev = conn.execute(
            "SELECT upload_id, source_path, source_seal_id, seq FROM seal_uploads "
            "WHERE batch_id=? AND sha256=?", (batch_id, sha)).fetchone()
        if prev is not None:  # 幂等重放
            conn.rollback()
            return {"status": "skipped", "reason": "duplicate_sha_in_batch", "upload_id": prev[0],
                    "source_path": prev[1], "source_seal_id": prev[2], "seq": prev[3],
                    "sha256": sha, "filename": filename}
        if conn.execute("SELECT 1 FROM seals WHERE source_seal_id=?", (source_seal_id,)).fetchone():
            raise UploadError(f"source_seal_id 已存在（不得覆盖既有行）：{source_seal_id}")

        # 原始件落盘（同批同名 ⇒ 前缀 sha8 去重，绝不覆盖）
        fname = safe_filename(filename)
        dest = batch_dir / fname
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() != sha:
            dest = batch_dir / f"{sha[:8]}-{fname}"
        if not dest.exists():
            dest.write_bytes(data)

        created_at = seals._now()
        conn.execute(
            "INSERT INTO seal_uploads (upload_id, source_path, filename, sha256, width, height, "
            "o_path, canvas_path, meta_json, batch_id, created_at, seq, source_seal_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (upload_id, str(dest), fname, sha, width, height, None, None,
             _meta_json(image_kind=kind, bytes=len(data), dynasty=dynasty,
                        dynasty_source=dynasty_source, author_name=author_name,
                        transcription=transcription, source_note=source_note,
                        naming="P?-C?-R?-印面釋文-朝代-作者-O"),
             batch_id, created_at, int(seq), source_seal_id),
        )
        row = seal_row_for_upload(source_seal_id=source_seal_id, dynasty=dynasty,
                                  dynasty_source=dynasty_source, author_name=author_name,
                                  transcription=transcription, batch_id=batch_id,
                                  upload_id=upload_id, filename=fname, sha256=sha,
                                  source_note=source_note)
        cols = list(row.keys())
        conn.execute(
            f"INSERT INTO seals ({', '.join(cols)}, updated_at) VALUES ({', '.join('?' for _ in cols)}, ?)",
            [row[c] for c in cols] + [created_at],
        )
        conn.commit()
        return {"status": "ok", "upload_id": upload_id, "source_seal_id": source_seal_id,
                "source_path": str(dest), "sha256": sha, "width": width, "height": height,
                "seq": int(seq), "filename": fname}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_uploads(db_path: Path | str, batch_id: str | None = None) -> list[dict]:
    """台账读数（验证/README 用；只读）。"""
    conn = seals._connect(db_path)
    try:
        if batch_id:
            rows = conn.execute("SELECT * FROM seal_uploads WHERE batch_id=? ORDER BY seq", (batch_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM seal_uploads ORDER BY batch_id, seq").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
