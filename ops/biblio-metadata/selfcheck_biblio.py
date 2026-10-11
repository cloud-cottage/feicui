#!/usr/bin/env python3
"""`server/app/biblio.py` 单测 ＋ 静态纪律自检（Kong / biblio-metadata 单 · 2026-10-11）。

**纯标准库**（无图像栈依赖）⇒ 任意解释器可跑：
    cd /Users/kevin/bistro/xiai/feicui
    python3 ops/biblio-metadata/selfcheck_biblio.py

覆盖：口径件 §8 的验收候选 BM-1 〜 BM-6（**阶段 1 可机械判负的那部分**）＋ 抓取面常量
（前 6 页 ∪ 末 4 页）＋ 静默/伪造判负（不伪造 L1 成功、冲突不静默）。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


b = _load("biblio", REPO / "server" / "app" / "biblio.py")

RESULTS: list[tuple[bool, str]] = []


def check(cond: bool, label: str, extra: str = "") -> None:
    RESULTS.append((bool(cond), label + (f"  [{extra}]" if extra else "")))


# ── 静态纪律：纯函数（无 DB / 图像栈 import）────────────────────────────────
src = (REPO / "server" / "app" / "biblio.py").read_text(encoding="utf-8")
import re as _re
_imported = {m.split(".")[0] for m in
             _re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)", src, flags=_re.M)}
for forbidden in ["sqlite3", "cv2", "pymupdf", "PIL", "paddleocr", "numpy"]:
    check(forbidden not in _imported, f"纯函数纪律：不 import `{forbidden}`（实际 import={sorted(_imported)}）")

# ── BM-1：ISBN 规范化 ＋ 校验位 ───────────────────────────────────────────
check(b.normalize_isbn("ISBN 978-7-5508-4722-4") == "9787550847224", "BM-1 normalize 去连字符/空格")
check(b.normalize_isbn("7-80635-095-0") == "7806350950", "BM-1 normalize ISBN-10")
check(b.normalize_isbn("043942089x") == "043942089X", "BM-1 normalize x→X")
check(b.normalize_isbn(None) is None, "BM-1 normalize None ⇒ None")

v = b.validate_isbn("9787550847224")
check(v["kind"] == "isbn13" and v["valid"] and v["total"] == 136 and v["check_digit"] == 4,
      "BM-1 ISBN-13 样本 9787550847224（total=136, check=4）", json.dumps(v, ensure_ascii=False))
v = b.validate_isbn("7806350950")
check(v["kind"] == "isbn10" and v["valid"] and v["total"] == 264, "BM-1 ISBN-10 样本 7806350950（264）")
v = b.validate_isbn("7501007985")
check(v["kind"] == "isbn10" and v["valid"] and v["total"] == 198, "BM-1 ISBN-10 样本 7501007985（198）")
check(b.validate_isbn("043942089X")["valid"], "BM-1 ISBN-10 含 X 校验通过（043942089X）")

check(not b.validate_isbn("9787550847223")["valid"], "BM-1 非法校验位 ISBN-13 ⇒ invalid")
check(not b.validate_isbn("7806350951")["valid"], "BM-1 非法校验位 ISBN-10 ⇒ invalid")
check(b.validate_isbn("978755084722")["kind"] is None, "BM-1 位数不合 ⇒ kind=None")
check(b.validate_isbn("9775550847224")["kind"] is None, "BM-1 非 978/979 前缀 ⇒ kind=None")

check(b.isbn10_to_isbn13("7806350950") == "9787806350959", "BM-1 ISBN-10→13（7806350950）")
check(b.isbn13_to_isbn10("9787550847224") == "7550847223", "BM-1 ISBN-13→10（9787550847224）")
check(b.isbn13_to_isbn10("9791234567894") is None, "BM-1 979 前缀无 ISBN-10 ⇒ None")

# ── BM-2：CIP 核字号正则 ──────────────────────────────────────────────────
check(b.cip_code("中國國家版本館CIP數據核字第2025WX8837號") == "2025WX8837",
      "BM-2 样本锚 核字第2025WX8837號 ⇒ 2025WX8837")
check(b.cip_code("图书在版编目(CIP)数据 核字第2025WX8837号") == "2025WX8837",
      "BM-2 简体「核字第…号」命中")
check(b.cip_code("核字 第 2025 WX 8837 號") == "2025WX8837", "BM-2 松散空白命中")
check(b.cip_code("本页正文没有任何相关词") is None, "BM-2 不含核字 ⇒ 不误命中")
check(b.cip_code("核对字数与版式") is None, "BM-2 含「核」不含「核字…號」⇒ 不误命中")
check(len(b.find_cip_codes("核字第2025WX8837號 又 核字第2024AB12号")) == 2, "BM-2 多命中计数")

# ── BM-3 / BM-4：交叉自证（出版社前缀 ⟷ OCR 出版社）────────────────────────
check(b.PUBLISHER_PREFIX_MAP.get("5508") == "西泠印社出版社", "交叉自证 表项 5508 ⇒ 西泠印社出版社（照登）")
check("5508" in b.publisher_prefix_candidates("9787550847224"), "前缀候选含 5508")
check(b.publisher_for_isbn("9787550847224")["publisher"] == "西泠印社出版社", "前缀匹配 ⇒ 出版社")
xv = b.cross_verify("9787550847224", "西泠印社出版社")
check(xv["verify_state"] == "ok", "BM-3 校验位过 ∧ 前缀与 OCR 出版社一致 ⇒ ok", xv["note"])
xv = b.cross_verify("9787550847224", "中华书局")
check(xv["verify_state"] == "conflict" and xv["match"] is False, "BM-4 前缀与 OCR 出版社不一致 ⇒ conflict")
check(xv["evidence"].get("prefix_table_entry") == "5508 ＝ 西泠印社出版社"
      and xv["ocr_publisher"] == "中华书局", "BM-4 冲突：双方证据均保留（不静默取一）")
xv = b.cross_verify("9787550847223", "西泠印社出版社")
check(xv["verify_state"] == "checksum_fail", "BM-4 校验位不过 ⇒ checksum_fail（优先于冲突）")
xv = b.cross_verify("0306406152", "新星出版社")   # ISBN-10 组号 0（英语）⇒ 前缀不在本地表
check(xv["verify_state"] == "unverified", "校验位过 ∧ 前缀未收录本地表 ⇒ unverified（不臆断）")
xv = b.cross_verify("7806350950", "上海书画出版社")   # 80635 由配置文件载入
check(xv["verify_state"] == "ok" and xv["prefix"] == "80635",
      "BM-3 前缀 80635 ⇒ 上海书画出版社（来自 config/isbn_publisher_prefixes.json）")
check(b.find_publishers("西泠印社出版社出版 西泠印社出版社") == ["西泠印社出版社"],
      "出版社抽取去重")
check(b.find_publishers("顺义向阳胶印厂印刷") == [], "出版社抽取不误命中「…厂印刷」")

# ── BM-5：L1 适配层（无密钥即跳过；不伪造成功；不阻塞）────────────────────
out = b.l1_lookup("9787550847224", "jisu", environ={})
check(out["skipped"] and out["reason"] == "missing_key" and out["verify_state"] == "unverified",
      "BM-5 密钥缺失 ⇒ 跳过 ＋ unverified", json.dumps({k: out[k] for k in ('skipped','reason','verify_state')}, ensure_ascii=False))
check(out["called_network"] is False, "BM-5 密钥缺失 ⇒ 未发起网络")
out2 = b.l1_lookup("9787550847224", "jisu", environ={"FEICUI_L1_JISU_KEY": "x"})
check(out2["skipped"] and out2["reason"] == "no_http_client", "BM-5 有密钥无 http 客户端 ⇒ 跳过")
check(out2["verify_state"] == "unverified", "BM-5 有密钥不伪造成功 ⇒ unverified")
try:
    b.l1_lookup("9787550847224", "nope", environ={})
    check(False, "BM-5 未知供应商 ⇒ KeyError")
except KeyError:
    check(True, "BM-5 未知供应商 ⇒ KeyError")

# ── BM-6：豆瓣只读 / 不进校验链；国图惯例 ──────────────────────────────────
check(b.DOUBAN_READONLY_REG["in_verify_chain"] is False, "BM-6 豆瓣 in_verify_chain=False（不进校验链）")
d = b.douban_registration()
d["in_verify_chain"] = True
check(b.DOUBAN_READONLY_REG["in_verify_chain"] is False, "BM-6 douban_registration 返回深拷贝（常量不被误改）")
check(b.DOUBAN_READONLY_REG["cache_slot"].startswith("var/"), "BM-6 豆瓣缓存位登记在 var/（运行时）")

# ── 抓取面常量（口径件 §5-2）──────────────────────────────────────────────
check(b.SCAN_FACE_HEAD_PAGES == 6 and b.SCAN_FACE_TAIL_PAGES == 4, "抓取面 ＝ 前 6 页 ∪ 末 4 页")
check(b.SCAN_DPI == 200.0, "OCR 渲染 ＝ 200 dpi")
check(b.page_face_indices(851) == [0, 1, 2, 3, 4, 5, 847, 848, 849, 850], "851 页 ⇒ 面页下标正确（含 850/851）")
check(b.page_face_indices(3) == [0, 1, 2], "页数 <10 ⇒ 退化全页")
check(b.page_face_indices(0) == [], "0 页 ⇒ 空面")
check(b.contains_anchor("图书在版编目（CIP）数据") and b.contains_anchor("isbn 978"), "锚词命中（含小写 isbn）")
check(not b.contains_anchor("无关正文"), "锚词不误命中")

# ── 目录键推荐（不执行切键）───────────────────────────────────────────────
rec = b.recommend_dir_key("秦印类编 检索版.pdf", isbn13="9787550847224")
check(rec["dir_key"] == "9787550847224" and rec["dir_key_source"] == "ISBN",
      "目录键推荐：优先 ISBN-13（缺陷②修正）", rec["dir_key"])
rec = b.recommend_dir_key("古玺汇编 文物出版社 罗福颐  ok.pdf", isbn10="7501007985")
check(rec["dir_key"] == "7501007985" and rec["dir_key_source"] == "ISBN", "目录键推荐：ISBN-10 直接落")
rec = b.recommend_dir_key("吴颐人篆刻作品展示.pdf")
check(rec["dir_key"] == "吴颐人篆刻作品展示" and rec["dir_key_source"] == "chinese_title",
      "目录键推荐：无 ISBN ⇒ 中文书名")
rec = b.recommend_dir_key("tmp.pdf", unconfirmed=True)
check(rec["dir_key"] == "tmp.pdf" and rec["dir_key_source"] == "pdf_name_unconfirmed",
      "目录键推荐：身份未确认 ⇒ 回落 PDF 名")

# ── 文本抽取（ISBN）────────────────────────────────────────────────────────
cs = b.find_isbn_candidates("定价：128.00 元  ISBN 978-7-5508-4722-4")
check(len(cs) == 1 and cs[0]["normalized"] == "9787550847224" and cs[0]["labeled"],
      "find_isbn_candidates：合形 ＋ labeled")
cs = b.find_isbn_candidates("7-80635-095-0")
check(len(cs) == 1 and cs[0]["kind"] == "isbn10", "find_isbn_candidates：ISBN-10")
check(b.find_isbn_candidates("2025WX8837") == [], "find_isbn_candidates：核字串（含字母）不冒充 ISBN")
check(b.find_isbn_candidates("1111111111111") == [],
      "退化串守卫：`1111111111111` 不冒充 ISBN（全 1 的 1111111111 校验位恰好合法）")
check(b.find_isbn_candidates("0000000000000") == [], "退化串守卫：全 0 串不冒充")
check(len(b.find_isbn_candidates("9787550847224")) == 1, "退化守卫不误伤真 ISBN-13")
check(len(b.find_isbn_candidates("7501007985")) == 1, "退化守卫不误伤真 ISBN-10")
check(b.MIN_DISTINCT_DIGITS == 3, "退化守卫常量 MIN_DISTINCT_DIGITS=3（单点可改）")

# ══════════════════════════════════════════════════════════════════════════
# 收口（Kong 2026-10-11）：三重闸④ 形态/长度闸 ＋ 目录键（ISBN-13 优先 / 中文书名去来源缀）
# ══════════════════════════════════════════════════════════════════════════

# ── 缺陷①：拼接噪声假号被拒（真号＋噪声被连字符/无空格串接 ⇒ 整体拒、不滑窗）────
GARBAGE_QIN = "978-7-5508-4722-4787550847224"       # 秦印类编 检索表 OCR（25 位）
GARBAGE_FUAN = "978-988-19923-2-19789881992321"     # 福庵印缀 版权页 OCR（26 位）
check(b.find_isbn_candidates(GARBAGE_QIN) == [], "形态闸：秦印检索表 25 位拼接串 ⇒ 无候选")
check(b.find_isbn_candidates(GARBAGE_FUAN) == [], "形态闸：福庵 26 位拼接串 ⇒ 无候选（假号 9789881992321 被拒）")
_rj = b.find_isbn_candidates(GARBAGE_FUAN, keep_rejected=True)
check(len(_rj) == 1 and _rj[0]["shape_reason"] == "too_long(26)"
      and _rj[0]["normalized"] == "97898819923219789881992321" and _rj[0]["kind"] is None,
      "形态闸：拼接串留痕为 too_long(26)（不切片、kind=None）",
      _rj[0]["shape_reason"] if _rj else "—")
check(b.shape_reason("97898819923219789881992321") == "too_long(26)", "shape_reason：26 位 ⇒ too_long(26)")
check(b.shape_reason("9787550847224") is None and b.shape_reason("7501007985") is None,
      "shape_reason：合形 13/10 位 ⇒ None")
check(b.shape_reason("978755084722") == "bad_len(12)", "shape_reason：12 位 ⇒ bad_len(12)")
check(b.MAX_ISBN_DIGITS == 13, "形态闸常量 MAX_ISBN_DIGITS=13（单点可改）")

# ── 缺陷②：目录键优先 ISBN-13；仅当只有 ISBN-10 时才用 10 位 ──────────────────
check(b.recommend_dir_key("秦印类编 检索版.pdf", isbn13="9787550847224")["dir_key"] == "9787550847224",
      "缺陷②：直读 ISBN-13 ⇒ 目录键落 13 位")
check(b.recommend_dir_key("秦汉印典 x.pdf", isbn10="7806350950")["dir_key"] == "7806350950",
      "缺陷②：只有 ISBN-10 ⇒ 目录键落 10 位（既有口径不破）")
check(b.recommend_dir_key("x.pdf", isbn13="9787550847224", isbn10="7550847223")["dir_key"]
      == "9787550847224", "缺陷②：13/10 同时给出 ⇒ 优先 13 位")

# ── 缺陷③：无号回退规范化中文书名（去下载站来源缀）──────────────────────────
check(b.normalize_chinese_title("黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk).pdf")
      == "黄牧甫印谱", "缺陷③：去下载站来源缀 ⇒ 黄牧甫印谱")
check(b.recommend_dir_key("黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk).pdf")["dir_key"]
      == "黄牧甫印谱", "缺陷③：黄牧甫目录键不再输出垃圾整串")
check(b.normalize_chinese_title("秦印类编 检索版.pdf") == "秦印类编 检索版"
      and b.normalize_chinese_title("福庵印缀 原版 高清.pdf") == "福庵印缀 原版 高清"
      and b.normalize_chinese_title("吴颐人篆刻作品展示.pdf") == "吴颐人篆刻作品展示",
      "缺陷③：无来源缀者逐字不动（秦印/福庵/吴颐人）")
check("z-library" in b.EBOOK_SOURCE_MARKERS and "1lib" in b.EBOOK_SOURCE_MARKERS,
      "缺陷③：来源标记常量含 z-library / 1lib")

# ── 前缀表落成配置文件 ─────────────────────────────────────────────────────
_tbl = b.load_publisher_prefixes()
check(_tbl.get("5508") == "西泠印社出版社" and _tbl.get("80635") == "上海书画出版社"
      and _tbl.get("5010") == "文物出版社", "前缀表配置文件：最小集三条齐", str(_tbl))
check(b.PUBLISHER_PREFIX_MAP == _tbl, "PUBLISHER_PREFIX_MAP 由配置文件载入（与 load 一致）")
check(b.load_publisher_prefixes("/no/such/file.json") == b.PUBLISHER_PREFIXES_DEFAULT,
      "前缀表：文件缺失 ⇒ 回落内联最小集（不抛错）")

# ── 退化闸仍独立生效（合形但全同 ⇒ 拒）─────────────────────────────────────
check(b.degenerate_reason("1111111111") == "all_same_char", "退化闸：1111111111（合形 10 位）⇒ all_same_char")
check(b.find_isbn_candidates("1111111111") == [], "退化闸：1111111111 不冒充 ISBN（合形但退化）")

# ── 打印结果 ─────────────────────────────────────────────────────────────
total = len(RESULTS)
passed = sum(1 for ok, _ in RESULTS if ok)
lines = []
for ok, label in RESULTS:
    lines.append(("  [PASS] " if ok else "  [FAIL] ") + label)
lines.append("")
lines.append(f"{passed}/{total} PASS" + ("" if passed == total else f"  ({total - passed} FAIL)"))
report = "\n".join(lines)
print(report)
(REPO / "ops" / "biblio-metadata" / "selfcheck_output.txt").write_text(report + "\n", encoding="utf-8")
raise SystemExit(0 if passed == total else 1)
