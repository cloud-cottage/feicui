#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sealbank 条目 → xiai 印章导入候选 映射器。

读 xiai 仓 imports 机制（只读取证，2026-10-19；本脚本不写 xiai 仓任何文件、不调云函数）：
  * 暂存集合 `xiai_seal_imports`（PENDING）→ 管理员采纳 ⇒ 整条落 `xiai_seals`＋`xiai_faces`
    （docs/spec-increments/seal-import-v1.55.md；§3.55/§4.1.17/§10.54）。
  * 提交载荷封闭键面 `SEAL_IMPORT_ALLOWED_KEYS`：
    batch_id / source / raw_json / 8 既有印章级键（seal_name, dynasty, seal_type, seal_style,
    material, shape, author, transcription）/ 51 源侧扩面键（… seal_yt_url …）/ faces / image_status
    （xiai cloudfunctions/xiai-user-token/lib/ops.js:329；src/data/seed.js:919-1105）。
  * 幂等键＝`source`＋`source_seal_id`；形态门：源侧扩面字段只允许 字符串/整数/null，
    **不得空串、不得数字 0**（audit_status 原样收；seal_ys_xz 整数或 null；misc 对象或 null）。
  * 行级缺图标记 image_status ∈ {present, source_no_image}；缺图行 faces[] 允许为空（保住文本本体）。
  * faces 键面（14 键）：kind∈{FACE,EDGE} / seal_name / dynasty / seal_type / face_style /
    seal_class / author / author_person_id / transcription / image_storage_key / image_sha256 /
    image_bytes / image_mime / image_source_kind（值域不封闭，原样收）。

映射（sealbank → xiai，源标「真微印網 sealbank.net」）：
  source_seal_id   ← 印章编号「年-序」（编年条目内嵌 m2ImgShow SRCHTXT）
  seal_name/seal_wen ← 条目正文〔…〕内印文（无则 null）
  author           ← 印人姓名（persons.ndjson）
  dynasty          ← 由生卒年推导（1644–1911 ⇒ 清；推导值，raw_json 留底）
  seal_type/shape  ← 正则描摹「朱文/白文…」「正方/長方…」（无则 null）
  seal_uri         ← m2ImgShow 详情页 URL（公开可引）
  seal_yt_url      ← 匿名 80px 缩图 URL（SBYBImg/red80/*.gif；仅有缩图的条目）
  seal_ytsw_url    ← 恒 null（原始图需扣點，餘點 0 不可得）
  transcription/material/size( seal_cc)/provenance(seal_ly) ← 恒 null（会员面，未得）
  image_status     ← 有缩图 ⇒ present＋faces[kind=FACE,image_source_kind='yt',image_storage_key=''(未上传)]
                      无缩图 ⇒ source_no_image＋faces=[]
  raw_json         ← sealbank 编年条目整行（只落导入行，正式集合不带）

用法：
  python3 to_xiai.py sample     # 3 枚样本 → out/xiai_imports_sample.ndjson
  python3 to_xiai.py candidates # 全候选计数报告（不落全量文件；全量启动权在用户）
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SOURCE_LABEL = "真微印網 sealbank.net"
BATCH_ID = "sealbank_sample_01"

# —— xiai 封闭键面（自 xiai/src/data/seed.js 逐字抄录；改动须回源头对齐）——
SEAL_IMPORT_SEAL_FIELDS = [
    "seal_name", "dynasty", "seal_type", "seal_style", "material", "shape", "author", "transcription",
]
SEAL_IMPORT_SOURCE_FIELDS = [
    "source_seal_id", "seal_uri", "category", "seal_wen", "seal_wen_chs", "seal_wen_pinyin",
    "seal_wen_wzly", "seal_wen_wzly_chs", "seal_wen_yssw", "seal_wen_yssw_chs", "seal_wen_wyz",
    "seal_wen_zjsw", "seal_wen_zjsw_chs", "seal_ys_xz", "seal_ys_label", "seal_ys_kf", "seal_ys_st",
    "seal_zyz", "seal_yz", "seal_yz_person_name", "seal_yz_person_name_chs", "seal_yz_name",
    "seal_yz_ref_id", "seal_yzzkz", "seal_yzzkz_chs", "seal_yzzkz_id", "seal_bk", "seal_bk_chs",
    "seal_bkzkz", "seal_bkzkz_chs", "seal_bkzkz_id", "as_book_id", "related_book", "seal_yt_url",
    "seal_ytsw_url", "seal_yzbk_url", "seal_yzqt_url", "seal_threed_url", "seal_title",
    "seal_title_chs", "seal_org", "seal_org_name", "seal_cz", "seal_cc", "seal_ly", "seal_yn",
    "seal_yksj_lsjn", "seal_yksj_lsjn_chs", "seal_yksj_gyjn", "audit_status", "misc",
]
FACE_FIELDS = [
    "kind", "seal_name", "dynasty", "seal_type", "face_style", "seal_class", "author",
    "author_person_id", "transcription", "image_storage_key", "image_sha256", "image_bytes",
    "image_mime", "image_source_kind",
]
ALLOWED_PAYLOAD_KEYS = set(
    ["batch_id", "source", "raw_json"] + SEAL_IMPORT_SEAL_FIELDS + SEAL_IMPORT_SOURCE_FIELDS
    + ["faces", "image_status"]
)

_SEAL_WEN = re.compile(r"〔([^〕]{1,40})〕")
_SHAPE = re.compile(r"(正方|長方|方形|圓形|橢圓|橢圓形|不規則|自然形|隨形)")
_STYPE = re.compile(r"(朱白文|朱文|白文|押脚朱文|回文朱文)")
_DYN = [(1911, "清"), (1644, "清"), (1368, "明")]


def derive_dynasty(years):
    """由生卒年推导朝代（推导值；两岸年代交叠以生年判）。"""
    if not years:
        return None
    y = years[0]
    for lo, name in _DYN:
        if y >= lo:
            return name
    return None


def map_entry(entry: dict, person: dict) -> dict:
    """编年条目（含印章引用）→ xiai 导入候选行（封闭键面；缺省与 xiai 默认一致）。"""
    sid = (entry.get("seal_ids") or [""])[0]
    text = entry.get("text", "")
    wen = _SEAL_WEN.search(text)
    shape = _SHAPE.search(text)
    stype = _STYPE.search(text)
    thumb = entry.get("thumb", "")
    # 只有 red80 是印章缩图；sb50/*.jpg 是印人照片占位，不得当作印章图
    is_seal_thumb = thumb.startswith("SBYBImg/red80/")
    thumb_url = ("http://www.sealbank.net/" + thumb) if is_seal_thumb else None
    row: dict = {"batch_id": BATCH_ID, "source": SOURCE_LABEL}
    # 印章级（既有 8 键：字符串可空串）
    row["seal_name"] = wen.group(1) if wen else ""
    row["dynasty"] = derive_dynasty(person.get("years")) or ""
    row["seal_type"] = stype.group(1) if stype else ""
    row["shape"] = shape.group(1) if shape else ""
    row["author"] = person.get("name", "")
    # 源侧扩面（字符串/整数/null；不得空串 0）
    row["source_seal_id"] = sid
    row["seal_uri"] = ("http://www.sealbank.net/m2ImgShow.asp?STOP=M2IMGS&LM=2&L1=2&L2=1&L3=0"
                       f"&LS=C&SRCHTXT={sid}") if sid else None
    row["category"] = "印章"
    row["seal_wen"] = wen.group(1) if wen else None
    row["seal_yt_url"] = thumb_url
    row["seal_ytsw_url"] = None  # 原始图需扣點；餘點 0 不可得（2026-10-19 实测）
    row["material"] = None       # 会员面字段未得
    row["seal_cc"] = None        # 尺寸未得
    row["seal_ly"] = None        # 出处未得
    row["seal_yn"] = entry.get("year")  # 整数或 null（条目纪年）
    row["transcription"] = ""    # 釋文未得（既有 8 键允许空串默认）
    # faces（影像先行：二进制未上传 ⇒ storage_key 空串；采纳时由 xiai 校验）
    if is_seal_thumb:
        row["image_status"] = "present"
        row["faces"] = [{
            "kind": "FACE", "seal_name": wen.group(1) if wen else "", "dynasty": row["dynasty"],
            "seal_type": row["seal_type"], "face_style": "", "seal_class": "",
            "author": person.get("name", ""), "author_person_id": person.get("id", ""),
            "transcription": "", "image_storage_key": "", "image_sha256": "", "image_bytes": 0,
            "image_mime": "image/gif", "image_source_kind": "yt",
        }]
    else:
        row["image_status"] = "source_no_image"
        row["faces"] = []
    row["raw_json"] = {"person_id": person.get("id"), "entry_seq": entry.get("seq"),
                       "year": entry.get("year"), "category": entry.get("category"),
                       "text": text, "note": entry.get("note", ""),
                       "seal_ids": entry.get("seal_ids", []), "thumb": thumb,
                       "scraped_at": entry.get("scraped_at"), "derived": {
                           "dynasty_rule": "birth_year∈[1644,1911]⇒清"}}
    return row


def validate_row(row: dict) -> list:
    """本地形态门预检（与 xiai validateSealImport 同规则的保守子集）。返回违规串列表。"""
    errs = []
    unknown = set(row) - ALLOWED_PAYLOAD_KEYS
    if unknown:
        errs.append(f"unknown keys: {sorted(unknown)}")
    if not row.get("source"):
        errs.append("source empty")
    if not row.get("source_seal_id"):
        errs.append("source_seal_id empty (幂等键)")
    for k in SEAL_IMPORT_SOURCE_FIELDS:
        if k in row:
            v = row[k]
            if k == "misc":
                if not (v is None or isinstance(v, dict)):
                    errs.append(f"{k} must be object|null")
            elif v is not None and not isinstance(v, (str, int)):
                errs.append(f"{k} must be str|int|null, got {type(v).__name__}")
            elif isinstance(v, str) and v == "" and k != "source_seal_id":
                errs.append(f"{k} empty string (源侧扩面不得空串)")
            elif v == 0:
                errs.append(f"{k} numeric 0 (源侧扩面不得 0)")
    for f in row.get("faces", []):
        unknown_f = set(f) - set(FACE_FIELDS)
        if unknown_f:
            errs.append(f"face unknown keys: {sorted(unknown_f)}")
        if f.get("kind") not in ("FACE", "EDGE"):
            errs.append(f"face kind invalid: {f.get('kind')}")
        if not isinstance(f.get("image_bytes", 0), int):
            errs.append("face image_bytes must be int")
    if row.get("image_status") not in (None, "present", "source_no_image"):
        errs.append(f"image_status invalid: {row['image_status']}")
    if row.get("image_status") == "source_no_image" and row.get("faces"):
        errs.append("source_no_image 行 faces 应为空")
    return errs


def load_data():
    persons = {p["id"]: p for p in
               (json.loads(l) for l in open(os.path.join(OUT, "persons.ndjson"), encoding="utf-8")
                if l.strip())}
    entries = [json.loads(l) for l in
               open(os.path.join(OUT, "entries.ndjson"), encoding="utf-8") if l.strip()]
    return persons, entries


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "sample"
    persons, entries = load_data()
    seal_entries = [(p, e) for e in entries
                    for p in [persons.get(e["person_id"])] if p and e.get("seal_ids")]
    if cmd == "sample":
        # 3 枚样本：取 Q9901 前三枚有缩图的印章条目（1818-027 / 1822-018 / 1832-039）
        picked, seen = [], set()
        for p, e in seal_entries:
            sid = e["seal_ids"][0]
            if sid in seen or not e.get("thumb"):
                continue
            seen.add(sid)
            picked.append((p, e))
            if len(picked) == 3:
                break
        rows, bad = [], 0
        for p, e in picked:
            row = map_entry(e, p)
            errs = validate_row(row)
            if errs:
                bad += 1
                row["validation_errors"] = errs
            rows.append(row)
        path = os.path.join(OUT, "xiai_imports_sample.ndjson")
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps({"path": path, "rows": len(rows), "validation_failures": bad,
                          "source_seal_ids": [r["source_seal_id"] for r in rows],
                          "batch_id": BATCH_ID, "source": SOURCE_LABEL}, ensure_ascii=False, indent=1))
    elif cmd == "candidates":
        n_with_thumb = sum(1 for _, e in seal_entries
                           if e.get("thumb", "").startswith("SBYBImg/red80/"))
        print(json.dumps({
            "persons": len(persons), "entries": len(entries),
            "seal_referencing_entries": len(seal_entries),
            "distinct_source_seal_ids": len({e["seal_ids"][0] for _, e in seal_entries}),
            "with_thumb": n_with_thumb,
            "without_thumb(source_no_image)": len(seal_entries) - n_with_thumb,
            "note": "全量启动权在用户；本命令只计数，不落全量文件",
        }, ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
