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
  source_seal_id   ← 印章编号「年-序」（编年条目内嵌 m2ImgShow SRCHTXT；书版索引同编号，补 3 位零）
  seal_name/seal_wen ← 条目正文〔…〕内印文（无则 null）；书版索引直接给「印面文字」
  author           ← 印人姓名（persons.ndjson / 书版印文索引「刻印者」）
  dynasty          ← 由年份推导，写 xiai 15 类枚举（书版索引按印章纪年；编年条目按生年近似）
  seal_type/shape  ← 正则描摹「朱文/白文…」「正方/長方…」（无则 null）
  seal_uri         ← m2ImgShow 详情页 URL（公开可引）
  seal_yt_url      ← 匿名 80px 缩图 URL（SBYBImg/red80/*.gif；仅有缩图的条目）
  seal_ytsw_url    ← 恒 null（原始图需扣點，餘點 0 不可得）
  transcription/material/size( seal_cc)/provenance(seal_ly) ← 恒 null（会员面，未得）
    例外：`transcription`（釋文）与既有 8 键同组，**落空串 ""**（不是 null）—— 注释与实现一致
  image_status     ← 有缩图 ⇒ present＋faces[kind=FACE,image_source_kind='yt',image_storage_key=''(未上传)]
                      无缩图 ⇒ source_no_image＋faces=[]（xiai v1.65 起明文放行，见 README）
                      **占位图模式**（`--placeholder`）⇒ present＋faces[kind=FACE,
                      image_storage_key='placeholder/seal-no-image']（xiai 侧已登记该公共占位图，
                      仅 sealbank 来源可引用；见 README「占位图模式」）
  raw_json         ← sealbank 原始行（只落导入行，正式集合不带）

用法：
  python3 to_xiai.py sample                  # 3 枚样本 → out/xiai_imports_sample.ndjson
  python3 to_xiai.py index                   # 5,529 枚，**无图模式** → out/xiai_imports_sealbank.ndjson
  python3 to_xiai.py index --placeholder     # 5,529 枚，**占位图模式** → out/xiai_imports_sealbank_placeholder.ndjson
  python3 to_xiai.py index --both            # 两种形态各落一份（文件名区分；同一次解析）
  python3 to_xiai.py candidates              # 全候选计数报告（不落全量文件；全量启动权在用户）
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
SOURCE_NO_IMAGE = "source_no_image"

# —— 占位图（xiai 侧登记面｜仅 sealbank 来源可引用）——
# 真值来源：xiai `src/data/seed.js::SEAL_PLACEHOLDER_IMAGE` / `public/placeholders/seal-no-image.jpg`。
# 换图必须同时改三处：xiai 资产文件、xiai 常量、这里（占位图模式产出的引用要能被采纳门解析到）。
PLACEHOLDER_KEY = "placeholder/seal-no-image"
PLACEHOLDER_SHA256 = "18d94039af1b1d4289b60fb6ef527323e05bc739b41229081c94702407de329c"
PLACEHOLDER_BYTES = 23357
PLACEHOLDER_MIME = "image/jpeg"

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

# —— 朝代推导（xiai `DYNASTY_OPTIONS` 15 类枚举；**写库门** src/data/db.js:2250 只收这 15 值）——
# 分段按朝代更替年归新朝（1368 明洪武元年、1644 清顺治元年）；明 / 清再按帝王世系细分：
#   宋元       : 1051–1367（宋亡 1279；元 1271 建号，1280 起实为元，两者同归「宋元」类）
#   明早中期   : 1368–1521（洪武–正德）
#   晚明       : 1522–1643（嘉靖–崇祯）
#   清初       : 1644–1735（顺治–雍正）
#   清中期     : 1736–1820（乾隆–嘉庆）
#   晚清       : 1821–1911（道光–宣统）
# 粗分（宋/元/明/清）另存 raw_json.derived.dynasty_coarse —— 书版索引口径要的是粗分，
# 但 `dynasty` 字段本身必须落在 xiai 的 15 类值域内，否则写入被 `INVALID_VALUE` 拒。
DYN_SEGMENTS = (
    (1051, 1279, "宋元", "宋", "宋（北宋 960–1127／南宋 1127–1279；1279 宋亡）"),
    (1280, 1367, "宋元", "元", "元（1271 建号，1279 灭宋；1368 元亡）"),
    (1368, 1521, "明早中期", "明", "明早中期（洪武 1368–正德 1521）"),
    (1522, 1643, "晚明", "明", "晚明（嘉靖 1522–崇祯 1643）"),
    (1644, 1735, "清初", "清", "清初（顺治 1644–雍正 1735）"),
    (1736, 1820, "清中期", "清", "清中期（乾隆 1736–嘉庆 1820）"),
    (1821, 1911, "晚清", "清", "晚清（道光 1821–宣统 1911；本书止于 1911）"),
)


def derive_dynasty(year):
    """年份 → (xiai 15 类 dynasty, 粗分 宋/元/明/清, 依据串)；越界 ⇒ (None, None, None)。"""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None, None, None
    for lo, hi, name, coarse, why in DYN_SEGMENTS:
        if lo <= y <= hi:
            return name, coarse, why
    return None, None, None


def derive_dynasty_from_birth(years):
    """兼容旧路径：由生年（编年条目只有生卒年）近似 → 15 类枚举。"""
    if not years:
        return None
    return derive_dynasty(years[0])[0]


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
    row["dynasty"] = derive_dynasty_from_birth(person.get("years")) or ""
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
    row["transcription"] = ""    # 釋文未得；既有 8 键允许空串（**落 "" 而非 null**，与实现一致）
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
                           "dynasty": row["dynasty"],
                           "dynasty_coarse": derive_dynasty(person.get("years")[0])[1] if person.get("years") else None,
                           "dynasty_rule": "生年近似：" + (derive_dynasty_from_birth(person.get("years")) or ""),
                           "note": "编年条目只给生卒年，朝代按生年近似；书版索引按印章纪年精确"}}
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
    # 占位图模式专项：faces 全部指向占位键，且 key/sha/bytes/mime 与 xiai 登记值一致。
    for f in row.get("faces", []):
        if f.get("image_storage_key") == PLACEHOLDER_KEY:
            if f.get("image_sha256") != PLACEHOLDER_SHA256:
                errs.append("placeholder image_sha256 与 xiai 登记值不符")
            if f.get("image_bytes") != PLACEHOLDER_BYTES:
                errs.append("placeholder image_bytes 与 xiai 登记值不符")
            if f.get("image_mime") != PLACEHOLDER_MIME:
                errs.append("placeholder image_mime 与 xiai 登记值不符")
    return errs


def load_data():
    persons = {p["id"]: p for p in
               (json.loads(l) for l in open(os.path.join(OUT, "persons.ndjson"), encoding="utf-8")
                if l.strip())}
    entries = [json.loads(l) for l in
               open(os.path.join(OUT, "entries.ndjson"), encoding="utf-8") if l.strip()]
    return persons, entries


IDX_BATCH_ID = "sealbank_idx_1051_1911"
IDX_DETAIL_URL = ("http://www.sealbank.net/m2ImgShow.asp?STOP=M2IMGS&LM=2&L1=2&L2=1&L3=0"
                  "&LS=C&SRCHTXT={sid}")


def seq_padded(seq: str) -> str:
    """`1287-5` → `1287-005`（网页详情页 / 编年页的 3 位补零编号形态）。"""
    year, no = str(seq).split("-")
    return f"{year}-{int(no):03d}"


def map_index_seal(rec: dict, placeholder: bool = False) -> dict:
    """书版《篆刻年歷》印文索引一行 → xiai 导入候选。

    `placeholder=False`（默认）：无影像 ⇒ `source_no_image` ＋ `faces=[]`（保住文本本体）。
    `placeholder=True`：无影像 ⇒ 行级 `present` ＋ `faces=[FACE]` 指向 xiai 已登记的公共占位图
    `placeholder/seal-no-image`（仅 sealbank 来源可引用的**影像例外**）；印面本体字段与行同值。
    """
    seq = rec["seq"]
    year = rec.get("year")
    text = rec.get("seal_text") or ""
    author = rec.get("author") or ""
    dyn, coarse, why = derive_dynasty(year)
    sid = seq_padded(seq)
    row: dict = {"batch_id": IDX_BATCH_ID, "source": SOURCE_LABEL}
    # 印章级 8 键（字符串可空串）
    row["seal_name"] = text
    row["dynasty"] = dyn or ""
    row["seal_type"] = ""
    row["seal_style"] = ""
    row["material"] = None
    row["shape"] = ""
    row["author"] = author
    row["transcription"] = ""     # 釋文未得（既有 8 键允许空串；**不是 null**）
    # 源侧扩面（字符串/整数/null；不得空串、不得 0）
    row["source_seal_id"] = sid
    row["seal_uri"] = IDX_DETAIL_URL.format(sid=sid)
    row["category"] = "印章"
    row["seal_wen"] = text or None
    row["seal_yt_url"] = None      # 书版索引不带图；red80 缩图按人内序号编，不属此书编号
    row["seal_ytsw_url"] = None    # 原始图需扣點，永久不可得
    row["seal_cc"] = None          # 尺寸未得
    row["seal_ly"] = None          # 出处未得
    row["seal_yn"] = year if isinstance(year, int) else None
    # 影像：本书版索引无图。
    #   默认 ⇒ 行级缺图标记 + 零 faces（xiai v1.65 AC-553/554）；
    #   占位图模式 ⇒ 行级 present + 一个 FACE 指向公共占位图（保住「一个印面」，详情页有印面块）。
    if placeholder:
        row["image_status"] = "present"
        row["faces"] = [{
            "kind": "FACE", "seal_name": text, "dynasty": dyn or "", "seal_type": "",
            "face_style": "", "seal_class": "", "author": author, "author_person_id": "",
            "transcription": "", "image_storage_key": PLACEHOLDER_KEY,
            "image_sha256": PLACEHOLDER_SHA256, "image_bytes": PLACEHOLDER_BYTES,
            "image_mime": PLACEHOLDER_MIME, "image_source_kind": "placeholder",
        }]
    else:
        row["image_status"] = SOURCE_NO_IMAGE
        row["faces"] = []
    row["raw_json"] = {
        "book": "篆刻年歷 1051-1911（官方免费书版索引）",
        "index_file": "篆刻年歷印文索引.txt",
        "seq_raw": seq, "seq_padded": sid, "year": year,
        "author_raw": author, "seal_text_raw": text,
        "derived": {"dynasty": dyn, "dynasty_coarse": coarse, "dynasty_rule": why},
        "source": SOURCE_LABEL,
    }
    return row


def index_seals(placeholder: bool = False) -> dict:
    """读 out/idx_seals.ndjson → 导入 NDJSON（逐行 flush）。

    `placeholder=False` ⇒ `out/xiai_imports_sealbank.ndjson`（无图模式，既有形态，逐字不变）；
    `placeholder=True`  ⇒ `out/xiai_imports_sealbank_placeholder.ndjson`（占位图模式，文件名区分，
                          两份文件**不互相覆盖**）。
    """
    src = os.path.join(OUT, "idx_seals.ndjson")
    rows, errs, seen, dups = [], [], {}, []
    for line in open(src, encoding="utf-8"):
        if not line.strip():
            continue
        row = map_index_seal(json.loads(line), placeholder=placeholder)
        key = (row["source"], row["source_seal_id"])
        if key in seen:
            dups.append(row["source_seal_id"])
            continue
        seen[key] = True
        bad = validate_row(row)
        if bad:
            errs.append({"seq": row["source_seal_id"], "errors": bad})
        rows.append(row)
    path = os.path.join(OUT, "xiai_imports_sealbank_placeholder.ndjson" if placeholder
                        else "xiai_imports_sealbank.ndjson")
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
    dist = {}
    for row in rows:
        dist[row["dynasty"]] = dist.get(row["dynasty"], 0) + 1
    # 人工可核样例：等距抽 10 条（seq / 印文 / 刻印者 / 推导朝代）
    step = max(1, len(rows) // 10)
    samples = [{"seq": r["source_seal_id"], "seq_raw": r["raw_json"]["seq_raw"],
                "seal_text": r["seal_wen"], "author": r["author"], "dynasty": r["dynasty"],
                "dynasty_coarse": r["raw_json"]["derived"]["dynasty_coarse"],
                "year": r["raw_json"]["year"], "image_status": r["image_status"]}
               for r in rows[::step][:10]]
    return {
        "path": path, "rows": len(rows), "source_rows": sum(1 for l in open(src, encoding="utf-8") if l.strip()),
        "validation_failures": len(errs), "validation_errors": errs[:5],
        "duplicate_idempotent_keys": len(dups), "dup_samples": dups[:5],
        "image_status": {"source_no_image": sum(1 for r in rows if r["image_status"] == SOURCE_NO_IMAGE),
                         "present": sum(1 for r in rows if r["image_status"] == "present")},
        "mode": "placeholder" if placeholder else "no_image",
        "placeholder_key": PLACEHOLDER_KEY if placeholder else None,
        "dynasty_distribution": dist,
        "samples": samples,
        "batch_id": IDX_BATCH_ID, "source": SOURCE_LABEL,
    }


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "sample"
    if cmd == "index":
        flags = set(argv[1:])
        unknown = flags - {"--placeholder", "--both"}
        if unknown:
            print(f"unknown flags: {sorted(unknown)}（只认 --placeholder / --both）", file=sys.stderr)
            return 2
        if "--both" in flags:
            # 同一次解析、两种形态各落一份（文件名区分：…_sealbank.ndjson / …_sealbank_placeholder.ndjson）
            print(json.dumps({"no_image": index_seals(False),
                              "placeholder": index_seals(True)}, ensure_ascii=False, indent=1))
            return 0
        print(json.dumps(index_seals("--placeholder" in flags), ensure_ascii=False, indent=1))
        return 0
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
