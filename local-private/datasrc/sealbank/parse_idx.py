#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""官方免费书版三索引（《篆刻年歷 1051-1911》）→ NDJSON 解析器。

输入：`out/sbidxtxt.zip`（官网免费下载的纯文字索引；文件名 cp437 乱码、内容 Big5）
  * 篆刻年歷印文索引.txt  字段 `年-序／刻印者／印面文字`
  * 篆刻年歷人名索引.txt  字段 `年-序／人名字號籍貫`（长传文本）
  * 篆刻年歷書目索引.txt  字段 `年-序／主題人物／年歷事態／書籍名稱`

编码：Big5-ETen（不是纯 Big5 —— 纯 `big5` / `cp950` 在扩展字上直接抛错，
实测 0xFCB7 / 0xFE74 等 ETen 扩展区字节）。解码走 `iconv -f BIG5-ETEN`；
其中落进 Unicode 私用区（U+E000–U+F8FF）的字形**不猜**，一律写成站点自家的
`◎{big5:0xXXXX}` 占位（XXXX = 该字在源文件里的两字节 Big5 码），
`name_plain` 去掉占位、`glyph_notes` 记下占位内容（沿用 client.py `_enrich` 手法）。

行/记录：有的行把两条记录挤在一行（以 `／年-序／` 连接），按 `年-序` 边界拆开
⇒ 记录数 ≥ 行数。拆不动（字段数不符）的行记入 `out/idx_parse_report.json` 的 anomalies，
不静默丢。

产出（逐行 flush）：
  out/idx_seals.ndjson    {seq, year, author, seal_text}
  out/idx_persons.ndjson  {seq, year, name_raw, name_plain, glyph_notes, bio_raw,
                           zi[], hao[], place, birth, death}
  out/idx_persons 的长传文本不做任何改写；解析不出的字段留 null / []（不编造）
  out/idx_biblio.ndjson   {seq, year, subject, event, title}
  out/idx_parse_report.json  行数 / 记录数 / 每字段非空率 / anomalies / 占位字表

用法：python3 parse_idx.py [--zip out/sbidxtxt.zip] [--out out]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_LABEL = "真微印網 sealbank.net"

IDX_SEALS = "篆刻年歷印文索引.txt"
IDX_PERSONS = "篆刻年歷人名索引.txt"
IDX_BIBLIO = "篆刻年歷書目索引.txt"

# 站点自造字 / ETen 私用区字形占位（与 client.py 同一记法）
GLYPH_RE = re.compile(r"◎\{([^}]*)\}")
_PUA_LO, _PUA_HI = 0xE000, 0xF8FF

# 记录边界：行内出现「/四位年-序号/」即视为新记录
REC_START = re.compile(r"(?=(?<!\d)\d{4}-\d{1,3}／)")
SEQ_RE = re.compile(r"^(\d{4})-(\d{1,3})$")


def _decode_eten(raw: bytes) -> str:
    """Big5-ETen 解码；failed 走 big5hkscs(replace) 兜底（并如实计数）。"""
    try:
        proc = subprocess.run(["iconv", "-f", "BIG5-ETEN", "-t", "UTF-8"],
                              input=raw, capture_output=True)
        if proc.returncode == 0:
            return proc.stdout.decode("utf-8")
    except OSError:
        pass
    return raw.decode("big5hkscs", errors="replace")


def _pua_placeholder(ch: str) -> str:
    """私用区字形 → ◎{big5:0xXXXX}（用 iconv 反查源字节；查不到则给码位）。"""
    try:
        proc = subprocess.run(["iconv", "-f", "UTF-8", "-t", "BIG5-ETEN"],
                              input=ch.encode("utf-8"), capture_output=True)
        if proc.returncode == 0 and len(proc.stdout) == 2:
            return "◎{big5:0x%s}" % proc.stdout.hex().upper()
    except OSError:
        pass
    return "◎{u+%04X}" % ord(ch)


def markup_pua(text: str) -> tuple[str, dict]:
    """把私用区字换成占位；返回 (新文本, {占位: 出现次数})。"""
    found: dict = {}
    if not any(_PUA_LO <= ord(c) <= _PUA_HI for c in text):
        return text, found
    out = []
    for ch in text:
        if _PUA_LO <= ord(ch) <= _PUA_HI:
            ph = _pua_placeholder(ch)
            found[ph] = found.get(ph, 0) + 1
            out.append(ph)
        else:
            out.append(ch)
    return "".join(out), found


def read_indexes(zip_path: str) -> dict:
    zf = zipfile.ZipFile(zip_path)
    out = {}
    for info in zf.infolist():
        name = info.filename.encode("cp437").decode("big5")
        raw = zf.read(info)
        text = _decode_eten(raw)
        out[name] = {"raw_bytes": len(raw), "text": text}
    return out


def split_records(text: str) -> tuple[list, dict]:
    """按 `年-序` 边界拆行；返回 (记录行列表, 统计)。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    stat = {"lines_total": len(lines), "header": None, "blank_lines": 0,
            "merged_lines": 0, "records": 0}
    body = lines
    if body and "／" in body[0] and not SEQ_RE.match(body[0].split("／")[0].strip()):
        stat["header"] = body[0]
        body = body[1:]
    recs = []
    for line in body:
        if not line.strip():
            stat["blank_lines"] += 1
            continue
        # 行内并记时，前一条记录尾部会留一个分隔符 `／`（源文件如此）⇒ 去掉再数字段
        parts = [p.strip().strip("／").strip() for p in REC_START.split(line)]
        parts = [p for p in parts if p]
        if len(parts) > 1:
            stat["merged_lines"] += 1
        recs.extend(parts)
    stat["records"] = len(recs)
    return recs, stat


def parse_seq(field: str) -> tuple[str, int, int] | None:
    m = SEQ_RE.match(field.strip())
    if not m:
        return None
    year, no = int(m.group(1)), int(m.group(2))
    return f"{year}-{no}", year, no


def seq_padded(seq: str) -> str:
    """`1287-5` → `1287-005`（网页/详情页的 3 位补零形态）。"""
    year, no = seq.split("-")
    return f"{year}-{int(no):03d}"


# —— 人名长传文本 → 结构化字段（只在能可靠切分时填，拿不准留空）——
_STOP_KW = ("別號", "晚號", "又號", "或號", "自號", "別署", "一字", "又字", "亦字",
            "字", "號", "齋堂", "一作", "初名", "原名", "又名", "譜名", "世稱", "通稱")
_STOP_RE = re.compile("|".join(_STOP_KW))
_ZI_RE = re.compile(r"(?:^|[。，；、])(?:一字|又字|亦字|字)")
_HAO_RE = re.compile(r"(?:^|[。，；、])(?:別號|晚號|又號|或號|自號|別署|號)")
_TOK_SPLIT = re.compile(r"[、，,]")
_BAD_TOK = re.compile(r"[0-9（）()改作字號稱為以後遂亦又\s]|的|生|卒|人$")


def _tokens(chunk: str, limit: int = 8) -> list:
    """把「字/號」后的串切成词：截到下一个关键词，按顿号逗号分。"""
    m = _STOP_RE.search(chunk)
    if m:
        chunk = chunk[:m.start()]
    chunk = chunk.strip("。；、， ")
    toks = []
    for tok in _TOK_SPLIT.split(chunk):
        tok = tok.strip("。； ")
        if not tok or len(tok) > 6 or _BAD_TOK.search(tok):
            continue
        if tok not in toks:
            toks.append(tok)
        if len(toks) >= limit:
            break
    return toks


def parse_zi(bio: str) -> list:
    out = []
    for m in _ZI_RE.finditer(bio):
        for tok in _tokens(bio[m.end():]):
            if tok not in out:
                out.append(tok)
    return out


def parse_hao(bio: str) -> list:
    out = []
    for m in _HAO_RE.finditer(bio):
        for tok in _tokens(bio[m.end():]):
            if tok not in out:
                out.append(tok)
    return out


def parse_place(bio: str):
    """首句 `…人` ⇒ 籍贯（保留「人」字，与既有 persons.ndjson 口径一致）。"""
    if not bio:
        return None
    first = re.split(r"[。；]", bio, maxsplit=1)[0]
    first = first.split("，")[0].strip()
    # 首句虽以「人」结尾但实为字号 / 斋堂 / 改名叙述 ⇒ 不是籍贯（不猜）
    if re.match(r"^(字|號|別|晚|又|或|自|一作|齋|名|譜名|初名|原名|通稱|世稱|後|遂)", first):
        return None
    if 2 <= len(first) <= 40 and first.endswith("人"):
        return first
    return None


_BIRTH = re.compile(r"(?:生於|生於清|生)[^\d]{0,4}(\d{4})")
_YEAR_RANGE = re.compile(r"[（(](\d{3,4})\s*[—–\-~～]\s*(\d{3,4})[）)]")
_DEATH = re.compile(r"(\d{4})年(?:卒|逝世)")


def parse_lifespan(bio: str) -> tuple:
    """生卒年：只认显式年份写法；本索引长传文本实测无此写法 ⇒ 恒 (None, None)。"""
    if not bio:
        return None, None
    m = _YEAR_RANGE.search(bio)
    if m:
        return int(m.group(1)), int(m.group(2))
    b = _BIRTH.search(bio)
    d = _DEATH.search(bio)
    return (int(b.group(1)) if b else None), (int(d.group(1)) if d else None)


def parse_person(seq: str, year: int, rest: str, glyph_hits: dict) -> dict:
    if "—" in rest:
        name_raw, bio = rest.split("—", 1)
    else:
        name_raw, bio = rest, ""
    name_raw = name_raw.strip()
    bio = bio.strip()
    notes = GLYPH_RE.findall(name_raw) or GLYPH_RE.findall(rest)
    name_plain = GLYPH_RE.sub("", name_raw).strip()
    birth, death = parse_lifespan(bio)
    return {
        "seq": seq,
        "year": year,
        "name_raw": name_raw or None,
        "name_plain": name_plain or None,
        "glyph_notes": notes,
        "bio_raw": bio or None,
        "zi": parse_zi(bio),
        "hao": parse_hao(bio),
        "place": parse_place(bio),
        "birth": birth,
        "death": death,
    }


def rate(rows: list, key: str, pred=None) -> dict:
    n = len(rows)
    if pred is None:
        ok = sum(1 for r in rows if r.get(key) not in (None, "", []))
    else:
        ok = sum(1 for r in rows if pred(r.get(key)))
    return {"non_empty": ok, "total": n, "pct": round(100.0 * ok / n, 2) if n else 0.0}


def write_ndjson(path: str, rows: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    zip_path = os.path.join(HERE, "out", "sbidxtxt.zip")
    out_dir = os.path.join(HERE, "out")
    for i, a in enumerate(argv):
        if a == "--zip" and i + 1 < len(argv):
            zip_path = argv[i + 1]
        if a == "--out" and i + 1 < len(argv):
            out_dir = argv[i + 1]

    files = read_indexes(zip_path)
    report: dict = {"source": SOURCE_LABEL, "zip": os.path.relpath(zip_path, HERE),
                    "encoding": "BIG5-ETEN (iconv); PUA → ◎{big5:0xXXXX}",
                    "indexes": {}, "glyphs": {}, "anomalies": []}

    # ① 印文索引
    text = files[IDX_SEALS]["text"]
    recs, stat = split_records(text)
    seals, bad = [], 0
    for rec in recs:
        cols = rec.split("／")
        sq = parse_seq(cols[0]) if cols else None
        if not sq or len(cols) != 3:
            bad += 1
            report["anomalies"].append({"index": "seals", "line": rec[:120],
                                        "why": f"fields={len(cols)}"})
            continue
        author, seal_text = cols[1].strip(), "／".join(cols[2:]).strip()
        seal_text, hits = markup_pua(seal_text)
        author, hits2 = markup_pua(author)
        for k, v in list(hits.items()) + list(hits2.items()):
            report["glyphs"][k] = report["glyphs"].get(k, 0) + v
        seals.append({"seq": sq[0], "year": sq[1], "author": author or None,
                      "seal_text": seal_text or None})
    write_ndjson(os.path.join(out_dir, "idx_seals.ndjson"), seals)
    report["indexes"]["seals"] = {
        "file": IDX_SEALS, **stat, "parsed": len(seals), "dropped": bad,
        "pct_of_official_5527": round(100.0 * len(seals) / 5527, 2),
        "rates": {k: rate(seals, k) for k in ("seq", "year", "author", "seal_text")},
        "distinct_seq": len({r["seq"] for r in seals}),
    }

    # ② 人名索引
    text = files[IDX_PERSONS]["text"]
    recs, stat = split_records(text)
    persons, bad = [], 0
    for rec in recs:
        cols = rec.split("／", 1)
        sq = parse_seq(cols[0]) if cols else None
        if not sq or len(cols) != 2:
            bad += 1
            report["anomalies"].append({"index": "persons", "line": rec[:120],
                                        "why": f"fields={len(cols)}"})
            continue
        body, hits = markup_pua(cols[1])
        for k, v in hits.items():
            report["glyphs"][k] = report["glyphs"].get(k, 0) + v
        persons.append(parse_person(sq[0], sq[1], body, hits))
    write_ndjson(os.path.join(out_dir, "idx_persons.ndjson"), persons)
    report["indexes"]["persons"] = {
        "file": IDX_PERSONS, **stat, "parsed": len(persons), "dropped": bad,
        "pct_of_official_3328": round(100.0 * len(persons) / 3328, 2),
        "rates": {k: rate(persons, k) for k in
                  ("seq", "year", "name_raw", "name_plain", "bio_raw", "zi", "hao",
                   "place", "birth", "death")},
        "zi_count": sum(len(r["zi"]) for r in persons),
        "hao_count": sum(len(r["hao"]) for r in persons),
        "glyph_rows": sum(1 for r in persons if r["glyph_notes"]),
    }

    # ③ 書目索引
    text = files[IDX_BIBLIO]["text"]
    recs, stat = split_records(text)
    biblio, bad = [], 0
    for rec in recs:
        cols = rec.split("／")
        sq = parse_seq(cols[0]) if cols else None
        if not sq or len(cols) != 4:
            bad += 1
            report["anomalies"].append({"index": "biblio", "line": rec[:120],
                                        "why": f"fields={len(cols)}"})
            continue
        vals = [markup_pua(c.strip()) for c in cols[1:]]
        for _, hits in vals:
            for k, v in hits.items():
                report["glyphs"][k] = report["glyphs"].get(k, 0) + v
        biblio.append({"seq": sq[0], "year": sq[1],
                       "subject": vals[0][0] or None, "event": vals[1][0] or None,
                       "title": "／".join(cols[3:]).strip() or None})
    write_ndjson(os.path.join(out_dir, "idx_biblio.ndjson"), biblio)
    report["indexes"]["biblio"] = {
        "file": IDX_BIBLIO, **stat, "parsed": len(biblio), "dropped": bad,
        "pct_of_official_2264": round(100.0 * len(biblio) / 2264, 2),
        "rates": {k: rate(biblio, k) for k in ("seq", "year", "subject", "event", "title")},
    }

    # 三索引 seq 交集（同一套 年-序 的自洽性）
    s_seals = {r["seq"] for r in seals}
    s_pers = {r["seq"] for r in persons}
    s_bib = {r["seq"] for r in biblio}
    report["seq_overlap"] = {
        "seals∩persons": len(s_seals & s_pers),
        "seals∩biblio": len(s_seals & s_bib),
        "persons∩biblio": len(s_pers & s_bib),
        "all_three": len(s_seals & s_pers & s_bib),
        "union": len(s_seals | s_pers | s_bib),
    }
    report["year_range"] = {
        "seals": [min(r["year"] for r in seals), max(r["year"] for r in seals)],
        "persons": [min(r["year"] for r in persons), max(r["year"] for r in persons)],
        "biblio": [min(r["year"] for r in biblio), max(r["year"] for r in biblio)],
    }
    path = os.path.join(out_dir, "idx_parse_report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("indexes", "seq_overlap", "year_range")},
                     ensure_ascii=False, indent=1))
    print("report:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
