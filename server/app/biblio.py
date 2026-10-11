"""书目元数据校验地基（ISBN / CIP）—— Kong / biblio-metadata 单 · 2026-10-11。

**纯函数模块**：只依赖标准库（`re` / `json` / `os`）。**不 import** 任何 DB 与图像栈
（`sqlite3` / `cv2` / `pymupdf` / `PIL` / `paddleocr` 一律不出现），因此可被接口层
（`server/.venv`，无图像栈）与 worker 侧（`venv`，有图像栈）**两侧共用**，与
`server/app/naming.py` / `server/app/colorcal.py` **同款约束**。

## 口径（真源：`docs/biblio-metadata-draft-v0.1.md`）

* **§5-1** ISBN 规范化（去连字符 / 空格、大小写 `X`）＋ **ISBN-10 / ISBN-13 校验位** ＋
  **CIP 核字号正则**（样本锚 `中國國家版本館CIP數據核字第2025WX8837號`；兼容
  `核字第2025WX8837號` 与简体「核字第…号」）。
* **§5-2** 版权页定位与抓取常量：扫描面 ＝ **前 6 页 ∪ 末 4 页**；**200 dpi**；
  锚词 `ISBN` / `圖書在版編目` / `在版编目` / `CIP` / `核字`。
* **§5-3** 交叉自证：ISBN 校验位通过 **∧** 出版社前缀与 OCR 出的出版社一致
  （`5508` ＝ 西泠印社出版社）⇒ `verify_state=ok`；不一致 ⇒ `conflict`（**保留双方证据**）。
* **§5-4** 目录键推荐：**ISBN 优先** —— **优先规范化后的 ISBN-13（去连字符，13 位）；仅当无 ISBN-13
  时才用 ISBN-10 的 10 位数字**；无 ISBN 落**规范化中文书名**（去下载站来源缀）；身份未确认回落 PDF 名。
* **§5-5** L1 商用 API 适配层**骨架**：配置驱动（供应商 / 端点 / 超时 / 限速），
  **密钥缺失即跳过并标 `unverified`**（**不得伪造成功**）；**本单不接真网、不申请密钥**。
* **§5-6** 豆瓣**只读**封面 / 简介：**仅登记接口形态与缓存位，不进校验链**。

## 红线（本模块自身）

只读、无副作用：**不写盘、不写库、不建 job、不联网**。写盘 / 落库由调用方
（`ops/biblio-metadata/scan_biblio.py`）负责；**密钥不入仓**（走环境变量）。

## 三重闸（＋收口新增「形态/长度闸」；Kong 2026-10-11）

候选 ISBN 须**同时**过闸方可采信（`is_accepted_candidate`）：

1. **锚词邻近闸** `anchor_near`（±`ANCHOR_WINDOW`）：排检索表 / 正文里的数字噪声；
2. **出版社前缀白名单闸**：命中本地前缀表 ∧ OCR 出版社一致 ⇒ `ok`；命中而不一致 ⇒ `conflict`；
   **未命中 ⇒ `unverified`（不得判 `ok`）**（表真源 ＝ `config/isbn_publisher_prefixes.json`）；
3. **退化串闸** `degenerate_reason`：全同 / 连续 `1` / 不同数字过少 / 单调连号 ⇒ 拒；
4. **形态/长度闸** `shape_reason`（**本次收口新增**）：规范化后数字**连续段**必须恰为 10 或 13 位；
   `>13`（真号＋噪声被连字符/无空格串接）**整体拒绝、不再滑窗**（旧版会把 25/26 位串切成伪 10/13 位窗口）。

## 已知正确样本（自证用，见 `docs/biblio-metadata-draft-v0.1.md` §2 / §8）

| 样本 | 面 | 期望 |
| --- | --- | --- |
| `9787550847224` | ISBN-13 | 校验通过（前 12 位加权和 **136**、校验位 **4**） |
| `7806350950` | ISBN-10 | 校验通过（加权和 **264**） |
| `7501007985` | ISBN-10 | 校验通过（加权和 **198**） |
| `核字第2025WX8837號` | CIP | 命中，code ＝ `2025WX8837` |
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    # 常量：版权页抓取
    "SCAN_FACE_HEAD_PAGES",
    "SCAN_FACE_TAIL_PAGES",
    "SCAN_DPI",
    "ANCHOR_WORDS",
    "page_face_indices",
    "contains_anchor",
    # 常量：ISBN / CIP
    "ISBN_TOKEN_RE",
    "CIP_RE",
    "PUBLISHER_PREFIX_MAP",
    "PUBLISHER_PREFIX_TABLE_PATH",
    "PUBLISHER_PREFIXES_DEFAULT",
    "PUBLISHER_RE",
    "MIN_DISTINCT_DIGITS",
    "ANCHOR_WINDOW",
    "ONES_RUN_MIN",
    "MONOTONIC_RUN_MIN",
    "MAX_ISBN_DIGITS",
    "EBOOK_SOURCE_MARKERS",
    "PUBLISHER_MISMATCH_AS_UNVERIFIED",
    # 三重闸
    "degenerate_reason",
    "shape_reason",
    "anchor_near",
    "is_accepted_candidate",
    # ISBN 规范化 / 校验
    "normalize_isbn",
    "isbn10_checksum",
    "isbn13_checksum",
    "validate_isbn",
    "isbn10_to_isbn13",
    "isbn13_to_isbn10",
    # 抽取
    "find_isbn_candidates",
    "find_cip_codes",
    "cip_code",
    "find_publishers",
    "find_pub_years",
    # 交叉自证 / 出版社前缀
    "load_publisher_prefixes",
    "publisher_prefix_candidates",
    "publisher_for_isbn",
    "cross_verify",
    # 目录键推荐
    "normalize_chinese_title",
    "recommend_dir_key",
    # L1 适配层骨架 / 豆瓣登记
    "L1_PROVIDERS",
    "L1_STAGE1_DISABLED_REASON",
    "l1_lookup",
    "DOUBAN_READONLY_REG",
    "douban_registration",
]

# ===========================================================================
# 常量（**全部单点可改**）
# ===========================================================================

#: 版权页扫描面：前 N 页（口径件 §5-2 ＝ 6）。
SCAN_FACE_HEAD_PAGES = 6
#: 版权页扫描面：末 N 页（口径件 §5-2 ＝ 4）。
SCAN_FACE_TAIL_PAGES = 4
#: 版权页 OCR 渲染分辨率（口径件 §2 实测：200 dpi 单页 ≈19.8 s 且 ISBN 照样命中；400 dpi 42–60 s）。
SCAN_DPI = 200.0

#: 版权页锚词（口径件 §5-2；大写按「不区分大小写」匹配）。
ANCHOR_WORDS: tuple[str, ...] = ("ISBN", "圖書在版編目", "在版编目", "CIP", "核字")

#: ISBN 候选 token 正则：以数字 / `X` 起止，内部允许数字 / `X` / 连字符 / 空白（**不含其他字母**，
#: 以免把 `2025WX8837` 之类核字串并入）。连字符含常见 Unicode 破折号。
ISBN_TOKEN_RE = re.compile(r"[0-9Xx][0-9Xx\-\u2010\u2011\u2012\u2013\u2014\u2015\s]{7,}[0-9Xx]")

#: CIP 核字号正则（口径件 §5-1 / §2 样本锚 `中國國家版本館CIP數據核字第2025WX8837號`）。
#: 兼容 `核字第2025WX8837號` 与简体「核字第…号」；`第` 可选、`（）` 可选。
CIP_RE = re.compile(
    r"核\s*字\s*第?\s*[（(]?\s*(?P<code>[0-9]{4}\s*[A-Za-z]{1,4}\s*[0-9]{1,10})\s*[）)]?\s*[號号]"
)

#: 出版者前缀 → 出版社名（**白名单**）。
#: 键 ＝ **出版者前缀数字串**（ISBN 去掉 EAN(`978`/`979`) 与组号(`7`) 、再去掉校验位后的前导数字）。
#: 来源：`5508` ＝口径件 §5-3 照登；`80635` / `5010` ＝ **Kevin 2026-10-11 复核给定**（见本单交回件）。
#: **未登记前缀一律 `unverified`、不得判 `ok`**（三重闸②）。
#: 真源＝配置文件 `config/isbn_publisher_prefixes.json`（Kong 2026-10-11 收口：由内联表落成配置文件，
#: 供审计与扩展）。此常量由 `load_publisher_prefixes()` 载入；**文件缺失 / 不可解析 ⇒ 回落内联最小集**。
PUBLISHER_PREFIX_TABLE_PATH: Path = (
    Path(__file__).resolve().parents[2] / "config" / "isbn_publisher_prefixes.json"
)

#: 内联最小集（**回落**用；与配置文件 `prefixes` 同口径）。**单点可改**。
PUBLISHER_PREFIXES_DEFAULT: dict[str, str] = {
    "5508": "西泠印社出版社",
    "80635": "上海书画出版社",
    "5010": "文物出版社",
}


def load_publisher_prefixes(path: str | os.PathLike[str] | None = None) -> dict[str, str]:
    """读入出版社前缀表配置文件 ⇒ `{prefix: 出版社名}`。

    配置形态（`config/isbn_publisher_prefixes.json`）：
        `{"schema": "...", "prefixes": {"5508": {"publisher": "西泠印社出版社", ...}, ...}}`
    —— `prefixes` 的每个值可为**字符串**（直接是出版社名）或**对象**（取 `publisher` 字段）。
    文件缺失 / 不可解析 / 无可用条目 ⇒ **回落** `PUBLISHER_PREFIXES_DEFAULT`（不抛错、不静默空表）。
    """
    p = Path(path) if path is not None else PUBLISHER_PREFIX_TABLE_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return dict(PUBLISHER_PREFIXES_DEFAULT)
    prefixes = raw.get("prefixes") if isinstance(raw, Mapping) else None
    if not isinstance(prefixes, Mapping) or not prefixes:
        return dict(PUBLISHER_PREFIXES_DEFAULT)
    out: dict[str, str] = {}
    for k, v in prefixes.items():
        if isinstance(v, Mapping):
            name = v.get("publisher")
        else:
            name = v
        if isinstance(k, str) and isinstance(name, str) and name:
            out[str(k)] = name
    return out or dict(PUBLISHER_PREFIXES_DEFAULT)


#: 生效的出版者前缀表（模块级；由配置文件载入，回落内联最小集）。
PUBLISHER_PREFIX_MAP: dict[str, str] = load_publisher_prefixes()

#: 出版社名抽取（「…出版社 / 書店 / 书局 / 印书馆」）。
PUBLISHER_RE = re.compile(r"[\u4e00-\u9fff]{2,10}(?:出版社|書店|书店|書局|书局|印书馆|印書館)")

#: 出版年抽取（19xx / 20xx）。
_PUB_YEAR_RE = re.compile(r"(?<![0-9])((?:19|20)[0-9]{2})(?:\s*年)?")

#: **三重闸①：锚词邻近窗口**（字符）。候选 ISBN 必须落在锚词 ±该窗口内才**可采信**。
#: 依据（Kevin 2026-10-11 复核）：《秦印类编》800–834 页是**检索表格**，含大量 `978…` 噪声
#: （`978 / 4226 / 4227 …`）⇒ 靠锚词窗口排掉表格噪声。**单点可改**。
ANCHOR_WINDOW = 120

#: **三重闸③：退化串守卫** —— 一个 ISBN 候选至少须含这么多个**不同**数字。
#: 换来的教训：文本层里的 `1111111111111`（或条码样串）切窗会得到 `1111111111`——
#: **它在数学上恰好是最小合法 ISBN-10（加权和 55 ⇒ 11 整除）**，纯校验位判据拦不住。
#: **单点可改**（真实 ISBN 的实际不同数字数远大于此）。
MIN_DISTINCT_DIGITS = 3

#: 退化串守卫：`1` 连续重复 ≥ 该位数 ⇒ 退化（Kevin 2026-10-11 复核：`1` 重复 ≥4 位归退化）。
ONES_RUN_MIN = 4

#: 退化串守卫：连续递增/递减数字段 ≥ 该长度 ⇒ 退化（如 `1234567890`）。
MONOTONIC_RUN_MIN = 8

#: **三重闸④（形态/长度闸，Kong 2026-10-11 收口）**：规范化后的**数字连续段**上限 ——
#: 单段长度必须恰为 **10 或 13**（ISBN-10 的 10 位 / ISBN-13 的 13 位）。
#: 换来的教训：福庵印缀版权页 OCR 出的 `978-988-19923-2-19789881992321`（规范化后 26 位，
#: 是「真号＋噪声」被连字符/无空格**串接**）会被旧版**滑窗**切成 13/10 位窗口，
#: 其中 `9789881992321`（13 位、校验位恰好合法）冒充成功 ⇒ **必须按长度闸整体拒绝**。
#: 秦印类编 检索表里 `978-7-5508-4722-4787550847224`（25 位）同理，其 10 位窗口
#: `2478755084` 校验位恰好合法、冒充 ISBN-10。**单点可改**。
MAX_ISBN_DIGITS = 13

#: **电子书下载站来源标记**（无号回落中文书名时用于去「书目来源缀」；大小写不敏感）。
#: 命中即在**首个括注 / 下划线**处截断（下载站文件名惯例：`书名_(出版社)_(站点…)`）。**单点可改**。
EBOOK_SOURCE_MARKERS: tuple[str, ...] = (
    "z-library", "z-lib", "1lib", "libgen", "annas-archive", "annas",
    "lib.sk", "zlib", "zlibrary", "23lib", "sanmin", "555lib",
)

#: 前缀命中白名单 ∧ OCR 出版社不一致时的处置。**默认 `conflict`**（口径件 §5-3 / BM-4：
#: 不一致必须 `conflict` 并保留双方证据）。**单点可改**：若裁「落 `unverified`」，置 `True`。
PUBLISHER_MISMATCH_AS_UNVERIFIED = False


# ===========================================================================
# 版权页扫描面（纯函数；供 scan_biblio.py 与单测共用）
# ===========================================================================

def page_face_indices(n_pages: int,
                      head: int = SCAN_FACE_HEAD_PAGES,
                      tail: int = SCAN_FACE_TAIL_PAGES) -> list[int]:
    """⇒ 版权页扫描面的 **0-based** 页下标（**前 `head` 页 ∪ 末 `tail` 页**，升序去重）。

    口径件 §5-2：扫描面 ＝ 前 6 页 ∪ 末 4 页。
    `n_pages` ≤ `head + tail` 时退化为全部页；`n_pages` ≤ 0 ⇒ 空表。
    """
    n = int(n_pages)
    if n <= 0:
        return []
    h = max(0, int(head))
    t = max(0, int(tail))
    head_idx = list(range(0, min(h, n)))
    tail_idx = list(range(max(0, n - t), n))
    return sorted(set(head_idx + tail_idx))


def contains_anchor(text: str, anchors: Iterable[str] = ANCHOR_WORDS) -> bool:
    """`text` 是否含任一锚词（**不区分大小写**；锚词里的中文原样比对）。"""
    if not text:
        return False
    up = text.upper()
    for a in anchors:
        if a.upper() in up:
            return True
    return False


# ===========================================================================
# ISBN 规范化 / 校验位（纯函数）
# ===========================================================================

def normalize_isbn(value: str | None) -> str | None:
    """ISBN 规范化：保留数字与字母 `X`，其余（连字符 / 空格 / 冒号 / 标签）一律丢弃；`x` → `X`。

    返回规范化串（可能为空串），空 / 非串入参 ⇒ `None`。
    **不做位数判断**（由 `validate_isbn` 负责）。
    """
    if value is None:
        return None
    s = str(value)
    out = []
    for ch in s:
        if ch.isdigit():
            out.append(ch)
        elif ch in "Xx":
            out.append("X")
    return "".join(out)


def _isbn10_core(isbn: str) -> str | None:
    s = normalize_isbn(isbn)
    if s is None or len(s) != 10:
        return None
    if not s[:9].isdigit():
        return None
    if not (s[9].isdigit() or s[9] == "X"):
        return None
    return s


def _isbn13_core(isbn: str) -> str | None:
    s = normalize_isbn(isbn)
    if s is None or len(s) != 13 or not s.isdigit():
        return None
    if not s.startswith(("978", "979")):
        return None
    return s


def isbn10_checksum(isbn: str) -> dict[str, Any]:
    """ISBN-10 校验位。⇒ `{"ok","kind","total","check_digit","expected_check","normalized"}`。

    判据：对 10 位（第 10 位可为 `X`＝10）按权重 `10,9,…,1` 求加权和 `total`，
    **`total % 11 == 0` ⇒ 通过**（等价于 `check_digit == expected_check`，其中
    `expected_check = (11 - (Σ 前 9 位权重加权 % 11)) % 11`）。
    """
    s = _isbn10_core(isbn)
    if s is None:
        return {"ok": False, "kind": None, "total": None, "check_digit": None,
                "expected_check": None, "normalized": normalize_isbn(isbn), "reason": "shape"}
    total = 0
    for i, ch in enumerate(s):
        d = 10 if ch == "X" else int(ch)
        total += (10 - i) * d
    check_digit = 10 if s[9] == "X" else int(s[9])
    head = 0
    for i, ch in enumerate(s[:9]):
        head += (10 - i) * int(ch)
    expected = (11 - (head % 11)) % 11
    return {"ok": total % 11 == 0, "kind": "isbn10", "total": total,
            "check_digit": check_digit, "expected_check": expected, "normalized": s}


def isbn13_checksum(isbn: str) -> dict[str, Any]:
    """ISBN-13 校验位。⇒ `{"ok","kind","total","check_digit","expected_check","normalized"}`。

    判据：13 位数字按权重 `1,3,1,3,…` 求加权和 `total`，**`total % 10 == 0` ⇒ 通过**
    （等价于 `check_digit == (10 - (Σ 前 12 位加权 % 10)) % 10`）。
    样本 `9787550847224`：前 12 位加权和 ＝ **136**、校验位 ＝ **4** ⇒ 通过。
    """
    s = _isbn13_core(isbn)
    if s is None:
        return {"ok": False, "kind": None, "total": None, "check_digit": None,
                "expected_check": None, "normalized": normalize_isbn(isbn), "reason": "shape"}
    # `total` ＝ **前 12 位**加权和（照口径件 §2 读数：`9787550847224` ⇒ 136）；
    # 判据等价于「13 位按 1,3,1,3… 加权 µ 10 == 0」。
    total = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(s[:12]))
    check_digit = int(s[12])
    expected = (10 - (total % 10)) % 10
    return {"ok": (total + check_digit) % 10 == 0, "kind": "isbn13", "total": total,
            "check_digit": check_digit, "expected_check": expected, "normalized": s}


def validate_isbn(value: str) -> dict[str, Any]:
    """自动判 10 / 13 位并校验。⇒ `{"normalized","kind","valid","total","check_digit","expected_check"}`。

    `kind ∈ {"isbn10","isbn13",None}`（形状不合 ⇒ `None`、`valid=False`）。**非法校验位 ⇒ `valid=False`。**
    """
    core10 = _isbn10_core(value)
    core13 = _isbn13_core(value)
    if core13 is not None:
        r = isbn13_checksum(core13)
    elif core10 is not None:
        r = isbn10_checksum(core10)
    else:
        r = {"ok": False, "kind": None, "total": None, "check_digit": None,
             "expected_check": None, "normalized": normalize_isbn(value)}
    return {"normalized": r.get("normalized"), "kind": r.get("kind"),
            "valid": bool(r.get("ok")), "total": r.get("total"),
            "check_digit": r.get("check_digit"), "expected_check": r.get("expected_check")}


def isbn10_to_isbn13(isbn10: str) -> str | None:
    """ISBN-10 → ISBN-13（前缀 `978`）。入参不合 ISBN-10 形 ⇒ `None`（**不校验**其校验位）。"""
    s = _isbn10_core(isbn10)
    if s is None:
        return None
    body = "978" + s[:9]
    head = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(body))
    check = (10 - (head % 10)) % 10
    return f"{body}{check}"


def isbn13_to_isbn10(isbn13: str) -> str | None:
    """ISBN-13 → ISBN-10（**仅 `978` 前缀可逆**；`979` 无对应 ISBN-10 ⇒ `None`）。

    入参不合 ISBN-13 形或前缀为 `979` ⇒ `None`；形状合则换算（**不校验**其校验位）。
    """
    s = _isbn13_core(isbn13)
    if s is None or not s.startswith("978"):
        return None
    body = s[3:12]          # 去掉 EAN `978` 与末位校验 ⇒ 9 位
    head = sum((10 - i) * int(ch) for i, ch in enumerate(body))
    check = (11 - (head % 11)) % 11
    tail = "X" if check == 10 else str(check)
    return f"{body}{tail}"


# ===========================================================================
# 从文本抽取（纯函数；供 OCR / 文本层共用）
# ===========================================================================

def _monotonic_run(compact: str) -> bool:
    """是否含 ≥`MONOTONIC_RUN_MIN` 长的**连续递增/递减数字段**（如 `12345678` / `87654321`）。"""
    run = 1
    for a, b in zip(compact, compact[1:]):
        if a.isdigit() and b.isdigit() and abs(int(b) - int(a)) == 1:
            run += 1
            if run >= MONOTONIC_RUN_MIN:
                return True
        else:
            run = 1
    return False


def degenerate_reason(compact: str) -> str | None:
    """**三重闸③ 退化串守卫** —— 返回退化原因（不退化 ⇒ `None`）。

    规则（任一命中即退化；**单点可改**见各常量）：
      * `all_same_char`：全部字符相同（如 `1111111111` / `0000000000`）；
      * `ones_run>=N`：数字 `1` 连续重复 ≥ `ONES_RUN_MIN`；
      * `few_distinct_digits`：不同数字数 < `MIN_DISTINCT_DIGITS`；
      * `monotonic_run`：含 ≥ `MONOTONIC_RUN_MIN` 的连续递增/递减数字段。
    """
    if not compact:
        return "empty"
    if len(set(compact)) == 1:
        return "all_same_char"
    if re.search(r"1{%d,}" % ONES_RUN_MIN, compact):
        return f"ones_run>={ONES_RUN_MIN}"
    digits = [c for c in compact if c.isdigit()]
    if len(set(digits)) < MIN_DISTINCT_DIGITS:
        return "few_distinct_digits"
    if _monotonic_run(compact):
        return "monotonic_run"
    return None


def anchor_near(text: str, start: int, end: int,
                window: int = ANCHOR_WINDOW) -> tuple[bool, str | None]:
    """**三重闸① 锚词邻近** —— 候选 `[start,end)` 的 ±`window` 窗口内是否含锚词。

    ⇒ `(是否命中, 命中锚词|None)`。锚词大小写不敏感（`ISBN` / `cip` 均命中）。
    """
    lo = max(0, start - window)
    hi = min(len(text), end + window)
    seg = text[lo:hi].upper()
    for w in ANCHOR_WORDS:
        if w.upper() in seg:
            return True, w
    return False, None


def shape_reason(compact: str) -> str | None:
    """**三重闸④ 形态/长度闸** —— 规范化后的数字串**整体**是否合 ISBN 形（不合 ⇒ 原因串）。

    规则（**单一整段判定**：不再对超长串做滑窗切片）：
      * 长度 **13** ⇒ 须以 `978`/`979` 起（否则 `prefix_not_978_979`）；
      * 长度 **10** ⇒ 前 9 位数字、末位数字/`X`（否则 `bad_x_position`）；
      * 长度 **> 13** ⇒ `too_long(N)`（拼接噪声：真号＋噪声被连字符/无空格串接）；
      * 其余长度 ⇒ `bad_len(N)`。

    合形 ⇒ `None`。**单点可改**（上限见 `MAX_ISBN_DIGITS`）。
    """
    n = len(compact)
    if n == 0:
        return "empty"
    if n == 13:
        return None if compact.startswith(("978", "979")) else "prefix_not_978_979"
    if n == 10:
        return None if (compact[:9].isdigit() and (compact[9].isdigit() or compact[9] == "X")) \
            else "bad_x_position"
    if n > MAX_ISBN_DIGITS:
        return f"too_long({n})"
    return f"bad_len({n})"


def _candidates_from_compact(compact: str) -> list[str]:
    """从规范化数字串里挑出**合形**的 13 / 10 位候选（**不做校验位判负**，交给 `validate_isbn`）。

    规则（**收口后**：整段判定，**不再滑窗**）：
      * 长度 **13** ⇒ 仅当以 `978`/`979` 起时取全串；
      * 长度 **10** ⇒ 仅当 9 位数字 ＋ 末位数字/`X` 时取全串；
      * 长度 **> 13**（真号＋噪声串接）⇒ **整体拒绝**（`shape_reason` ⇒ `too_long(N)`）；
      * 长度 11/12 / 非 `978`·`979` 前缀 ⇒ 不合形。

    依据（Kong 2026-10-11 收口，见 `MAX_ISBN_DIGITS` 注释）：旧版「长度 > 13 才滑窗」会把
    `978-7-5508-4722-4787550847224`（25 位）切成伪 10 位 `2478755084`、把
    `978-988-19923-2-19789881992321`（26 位）切成伪 13 位 `9789881992321`（校验位恰好合法）。
    退化守卫**不在此处丢弃**（改由 `degenerate_reason` 打标、留痕；见 `find_isbn_candidates`）。
    """
    return [compact] if shape_reason(compact) is None else []


def find_isbn_candidates(text: str, keep_rejected: bool = False) -> list[dict[str, Any]]:
    """从一段文本里抽取 ISBN 候选。⇒ 逐候选 dict（按出现位置升序、去重同串）。

    每条：`{"raw","normalized","kind","valid","total","check_digit","expected_check",
    "start","end","snippet","labeled","anchor_near","anchor_word","shape_reason","rejected_reason"}`。

    * `labeled` ＝ 该候选前面 ~12 字内出现 `ISBN`（含常见 OCR 变体 `lSBN` / `1SBN` / `IS8N`）；
    * `anchor_near` / `anchor_word` ＝ **三重闸①**（锚词 ±`ANCHOR_WINDOW`）；
    * `shape_reason` ＝ **三重闸④** 形态/长度原因（非空 ⇒ 该 token **整体**不合形、**不切片**）；
    * `rejected_reason` ＝ **三重闸④/③** 形态或退化原因（非空 ⇒ 该候选**不可采信**）；
    * `keep_rejected=True` ⇒ **保留**被拒候选（形态/退化均留痕；`kind=None`、`valid=False`）。
    """
    if not text:
        return []
    results: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    def _labeled_at(pos: int) -> bool:
        pre = text[max(0, pos - 12):pos].upper()
        return ("ISBN" in pre) or ("LSBN" in pre) or ("1SBN" in pre) or ("IS8N" in pre)

    for m in ISBN_TOKEN_RE.finditer(text):
        raw = m.group(0)
        # 先按整段 token 处理；再按空白切块处理（防「多个数被空格粘连」）
        chunks = [raw] + [c for c in re.split(r"\s+", raw) if c]
        for chunk in chunks:
            compact = normalize_isbn(chunk)
            if not compact:
                continue
            sr = shape_reason(compact)
            if sr is not None:
                # 三重闸④：整段不合形（如拼接噪声 too_long(26) / bad_len(11)）
                # ⇒ **不切片**（不再产出伪 13/10 位窗口）；仅留痕。
                if keep_rejected:
                    key = (m.start(), "shape:" + compact)
                    if key not in seen:
                        seen.add(key)
                        near, word = anchor_near(text, m.start(), m.end())
                        results.append({
                            "raw": chunk, "normalized": compact, "kind": None,
                            "valid": False, "total": None, "check_digit": None,
                            "expected_check": None, "start": m.start(), "end": m.end(),
                            "snippet": text[max(0, m.start() - 40): m.end() + 40],
                            "labeled": _labeled_at(m.start()), "anchor_near": near,
                            "anchor_word": word, "shape_reason": sr, "rejected_reason": sr,
                        })
                continue
            for cand in _candidates_from_compact(compact):
                key = (m.start(), cand)
                if key in seen:
                    continue
                v = validate_isbn(cand)
                if v["kind"] is None:
                    continue
                rej = degenerate_reason(cand)
                if rej and not keep_rejected:
                    continue
                seen.add(key)
                near, word = anchor_near(text, m.start(), m.end())
                results.append({
                    "raw": chunk,
                    "normalized": v["normalized"],
                    "kind": v["kind"],
                    "valid": v["valid"],
                    "total": v["total"],
                    "check_digit": v["check_digit"],
                    "expected_check": v["expected_check"],
                    "start": m.start(),
                    "end": m.end(),
                    "snippet": text[max(0, m.start() - 40): m.end() + 40],
                    "labeled": _labeled_at(m.start()),
                    "anchor_near": near,
                    "anchor_word": word,
                    "shape_reason": None,
                    "rejected_reason": rej,
                })
    results.sort(key=lambda r: (r["start"], r["normalized"] or ""))
    return results


def is_accepted_candidate(c: Mapping[str, Any]) -> bool:
    """**三重闸合成判据** —— 候选是否**可采信**：校验位过 ∧ 非退化 ∧ 锚词邻近。

    三重闸：① 锚词邻近（`anchor_near`）② 出版社前缀白名单（由 `cross_verify` 落实，未命中 ⇒ `unverified`）
    ③ 非退化串（`rejected_reason` 为空）。
    """
    return bool(c.get("valid")) and not c.get("rejected_reason") and bool(c.get("anchor_near"))


def find_cip_codes(text: str) -> list[dict[str, Any]]:
    """抽取 CIP 核字号。⇒ 逐命中 `{"code","raw","start","end","snippet"}`（`code` 去空白、`號` 不并入）。"""
    if not text:
        return []
    out = []
    for m in CIP_RE.finditer(text):
        code = re.sub(r"\s+", "", m.group("code"))
        out.append({"code": code, "raw": m.group(0), "start": m.start(), "end": m.end(),
                    "snippet": text[max(0, m.start() - 40): m.end() + 40]})
    return out


def cip_code(text: str) -> str | None:
    """⇒ 首个 CIP 核字号 code（如 `2025WX8837`）；无命中 ⇒ `None`。"""
    hits = find_cip_codes(text)
    return hits[0]["code"] if hits else None


def find_publishers(text: str) -> list[str]:
    """抽取出版社名候选（去重、按出现序）。如 `西泠印社出版社` / `文物出版社`。"""
    if not text:
        return []
    out: list[str] = []
    for m in PUBLISHER_RE.finditer(text):
        name = m.group(0)
        if name not in out:
            out.append(name)
    return out


def find_pub_years(text: str) -> list[int]:
    """抽取 19xx / 20xx 出版年候选（出现序、去重）。"""
    if not text:
        return []
    out: list[int] = []
    for m in _PUB_YEAR_RE.finditer(text):
        y = int(m.group(1))
        if y not in out:
            out.append(y)
    return out


# ===========================================================================
# 出版者前缀 与 交叉自证
# ===========================================================================

def publisher_prefix_candidates(isbn: str) -> list[str]:
    """⇒ 该 ISBN 的**出版者前缀候选**（去 EAN / 组号 / 校验位后的数字前缀，长度 ≥2）。

    做法（不依赖完整 ISBN 区间表，**保守取候选集**）：
      ① 规范化 ⇒ 去掉末位校验位 ⇒ `body`；
      ② 候选前缀 ＝ `body` 的各长度前缀 ∪ `body` 去掉**一个**前导组号数字后的各长度前缀。
    如 `9787550847224` ⇒ `body=755084722` ⇒ 去掉组号 `7` ⇒ `55084722` ⇒ 候选含 `5508`。
    """
    s = normalize_isbn(isbn)
    if not s:
        return []
    if len(s) == 13 and s.startswith(("978", "979")):
        body = s[3:12]
    elif len(s) == 10:
        body = s[:9]
    else:
        body = s[:-1] if len(s) > 1 else s
    variants = {body}
    if body.startswith("7"):
        variants.add(body[1:])
    cands: set[str] = set()
    for v in variants:
        for L in range(2, len(v) + 1):
            cands.add(v[:L])
    return sorted(cands)


def publisher_for_isbn(isbn: str, table: Mapping[str, str] | None = None) -> dict[str, Any]:
    """在出版社前缀表里匹配。⇒ `{"prefix","publisher","matched"}`。

    匹配规则：取该 ISBN 的**出版者前缀候选**中最长的、且命中表键者（键须为键集合中的成员）。
    """
    tbl = PUBLISHER_PREFIX_MAP if table is None else table
    cands = publisher_prefix_candidates(isbn)
    best = None
    for p in cands:                      # 取**最长**命中键（前缀越长越具体）
        if p in tbl and (best is None or len(p) > len(best)):
            best = p
    if best is None:
        return {"prefix": None, "publisher": None, "matched": False}
    return {"prefix": best, "publisher": tbl[best], "matched": True}


def _normalize_publisher_name(name: str | None) -> str:
    if not name:
        return ""
    s = str(name)
    s = re.sub(r"[\s\u3000]+", "", s)
    for suffix in ("有限公司", "有限责任公司", "股份有限公司"):
        s = s.replace(suffix, "")
    return s


def _publisher_same(a: str | None, b: str | None) -> bool:
    na, nb = _normalize_publisher_name(a), _normalize_publisher_name(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def cross_verify(isbn: str, ocr_publisher: str | None,
                 table: Mapping[str, str] | None = None) -> dict[str, Any]:
    """**交叉自证**（口径件 §5-3）。⇒ dict。

    逻辑：
      ① 校验位不过 ⇒ `verify_state="checksum_fail"`；
      ② 校验位过 ∧ 出版者前缀命中本地表 ∧ **OCR 出版社一致** ⇒ `ok`；
      ③ 校验位过 ∧ 出版者前缀命中本地表 ∧ **OCR 出版社不一致** ⇒ `conflict`（**保留双方证据**，不静默取一）；
      ④ 校验位过 ∧ 出版者前缀**未命中本地表** ⇒ `unverified`（校验位过、但出版社交叉面无法判定）。

    返回：`{"isbn","normalized","kind","verify_state","prefix","table_publisher",
    "ocr_publisher","match","note","evidence"}`。
    """
    v = validate_isbn(isbn)
    base = {"isbn": isbn, "normalized": v["normalized"], "kind": v["kind"],
            "prefix": None, "table_publisher": None, "ocr_publisher": ocr_publisher,
            "match": None, "note": "", "evidence": {"ocr_publisher": ocr_publisher}}
    if not v["valid"]:
        base["verify_state"] = "checksum_fail"
        base["note"] = (f"校验位不通过：加权和 total={v['total']}，检出校验位="
                        f"{v['check_digit']}，应为 {v['expected_check']}")
        return base

    pf = publisher_for_isbn(v["normalized"], table)
    base["prefix"] = pf["prefix"]
    base["table_publisher"] = pf["publisher"]
    if not pf["matched"]:
        base["verify_state"] = "unverified"
        base["note"] = ("校验位通过；出版者前缀未命中本地表"
                        f"（候选前缀集含 {publisher_prefix_candidates(v['normalized'])[:6]}…）"
                        + (f"；OCR 出版社＝{ocr_publisher}（未参与比对）" if ocr_publisher else "；OCR 未给出出版社"))
        return base

    base["evidence"]["prefix_table_entry"] = f"{pf['prefix']} ＝ {pf['publisher']}"
    if not ocr_publisher:
        base["verify_state"] = "ok"
        base["note"] = (f"校验位通过；出版者前缀 {pf['prefix']} ⇒ {pf['publisher']}"
                        "（OCR 未给出出版社，未参与比对）")
        return base

    if _publisher_same(pf["publisher"], ocr_publisher):
        base["verify_state"] = "ok"
        base["match"] = True
        base["note"] = f"校验位通过；出版者前缀 {pf['prefix']} ⇒ {pf['publisher']} 与 OCR 出版社一致"
    else:
        base["verify_state"] = "conflict"
        base["match"] = False
        base["note"] = (f"冲突：出版者前缀 {pf['prefix']} ⇒ 「{pf['publisher']}」"
                        f" ≠ OCR 出版社「{ocr_publisher}」（双方证据保留，不静默取一）")
    return base


# ===========================================================================
# 目录键推荐（**只给建议，不执行切键**）
# ===========================================================================

def _mechanical_stem(pdf_name: str) -> str:
    """**机械**规范化：去扩展名、去首尾空白、内部连续空白压一格（＝ `naming.normalize_book_name`）。"""
    stem = os.path.splitext(os.path.basename(str(pdf_name)))[0]
    return re.sub(r"\s+", " ", stem).strip()


def _fallback_title(pdf_name: str) -> str:
    """目录键回落用**机械**规范化书名（与 `naming.py:normalize_book_name` 逐字一致）。

    只做机械规范化（**不去书目来源缀**）；去下载站来源缀见 `normalize_chinese_title`。
    """
    return _mechanical_stem(pdf_name)


#: 下载站来源标记正则（大小写不敏感）。
_SOURCE_MARKER_RE = re.compile("|".join(re.escape(m) for m in EBOOK_SOURCE_MARKERS), re.I)


def normalize_chinese_title(pdf_name: str, title: str | None = None) -> str:
    """⇒ 无号回落的**规范化中文书名**（口径件 §5-4 / §6；**三重闸收口·缺陷③**）。

    * 有显式 `title` ⇒ 该标题规范化（压空白）；否则取 PDF 名机械规范化（去扩展名 / 压空白）；
    * **若命中 `EBOOK_SOURCE_MARKERS`（下载站来源标记，如 `z-library` / `1lib`）** ⇒ 在**首个
      括注 / 下划线**处截断（下载站文件名惯例 `书名_(出版社)_(站点…)`）。
      例：`黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk)` ⇒ `黄牧甫印谱`。
    * 不含来源标记者**逐字不动**（如 `秦印类编 检索版` / `福庵印缀 原版 高清` / `吴颐人篆刻作品展示`）。
    """
    if title:
        base = re.sub(r"\s+", " ", str(title)).strip()
    else:
        base = _mechanical_stem(pdf_name)
    if _SOURCE_MARKER_RE.search(base):
        head = re.split(r"[_（(]", base, 1)[0].strip()
        if head:
            return head
    return base


def recommend_dir_key(pdf_name: str, isbn10: str | None = None, isbn13: str | None = None,
                      title: str | None = None, unconfirmed: bool = False,
                      isbn_source: str = "local_ocr") -> dict[str, Any]:
    """**目录键推荐**（口径件 §5-4；**不执行切键、不改名、不改路径**）。⇒ dict。

    优先级（Kong 2026-10-11 收口，与 §5-4 对齐）：
      **① ISBN —— 优先规范化后的 ISBN-13（去连字符，13 位）；仅当无 ISBN-13 时才用 ISBN-10（10 位）；
      ② 中文书名（`title` 或 PDF 名规范化，去下载站来源缀）；③ PDF 名（身份未确认）。**

    调用方（`scan_biblio.summarize_book`）**只把「现场直读」到的形态传进来**：
    只直读 ISBN-10（13 位是派生）时 `isbn13=None` ⇒ 落 10 位；只直读 ISBN-13 时落 13 位。
    这样与既有口径一致：「秦汉印典 / 古玺汇编」（现场只有 10 位）落 `7806350950` / `7501007985`，
    而「秦印类编」（现场直读 13 位 `9787550847224`）落 `9787550847224`（**修正缺陷②**）。

    返回：`{"dir_key","dir_key_source","isbn_source","reason","isbn10","isbn13","derived_from"}`。
    """
    isbn10n = normalize_isbn(isbn10) if isbn10 else None
    isbn13n = normalize_isbn(isbn13) if isbn13 else None
    derived_from = None

    key13 = isbn13n if (isbn13n and len(isbn13n) == 13
                        and isbn13n.startswith(("978", "979"))) else None
    key10 = isbn10n if (isbn10n and len(isbn10n) == 10) else None

    # ① 优先 ISBN-13（去连字符）
    if key13:
        return {"dir_key": key13, "dir_key_source": "ISBN",
                "isbn_source": isbn_source,
                "reason": f"ISBN 优先（ISBN-13）：目录键＝{key13}（去连字符）",
                "isbn10": isbn10n, "isbn13": isbn13n, "derived_from": derived_from}
    # ② 仅当无 ISBN-13 时才用 ISBN-10
    if key10:
        return {"dir_key": key10, "dir_key_source": "ISBN",
                "isbn_source": isbn_source,
                "reason": f"ISBN（仅 ISBN-10 可用）：目录键＝{key10}（去连字符）",
                "isbn10": isbn10n, "isbn13": isbn13n, "derived_from": derived_from}

    if unconfirmed:
        base = os.path.basename(str(pdf_name))
        return {"dir_key": base, "dir_key_source": "pdf_name_unconfirmed",
                "isbn_source": None, "reason": "身份未确认 ⇒ 回落 PDF 名并标记（待确认后改）",
                "isbn10": isbn10n, "isbn13": isbn13n, "derived_from": None}

    name = normalize_chinese_title(pdf_name, title=title)
    return {"dir_key": name, "dir_key_source": "chinese_title",
            "isbn_source": None, "reason": f"无 ISBN ⇒ 落规范化中文书名「{name}」",
            "isbn10": isbn10n, "isbn13": isbn13n, "derived_from": None}


# ===========================================================================
# L1 商用 API 适配层**骨架**（配置驱动；无密钥即跳过并标 `unverified`；本单不接真网）
# ===========================================================================

#: 阶段 1 不接真网、不申请密钥的**逐字理由**（口径件 §5-5 / 待确认 C-2）。
L1_STAGE1_DISABLED_REASON = (
    "阶段 1 骨架：不接真网、不申请密钥（口径件 §5-5 / C-2）。密钥走环境变量（不入仓）；"
    "密钥缺失即跳过并标 unverified，不得伪造成功。"
)

#: L1 供应商配置（**配置驱动**：供应商 / 端点 / 超时 / 限速 / 密钥环境变量名）。
#: `endpoint` 与 `response_fields` 为**登记形态**（待阶段 2 定供应商后填实）；本单不联网。
L1_PROVIDERS: dict[str, dict[str, Any]] = {
    "jisu": {
        "label": "极速数据（ISBN/CIP 查询）",
        "endpoint": "",                              # 待阶段 2 定
        "env_key": "FEICUI_L1_JISU_KEY",             # 密钥走环境变量，不入仓
        "timeout_s": 8.0,
        "rate_limit_qps": 1.0,
        "response_fields": ["isbn13", "isbn10", "cip_code", "title", "publisher",
                            "pub_year", "edition"],
    },
    "juhe": {
        "label": "聚合数据（ISBN 查询）",
        "endpoint": "",
        "env_key": "FEICUI_L1_JUHE_KEY",
        "timeout_s": 8.0,
        "rate_limit_qps": 1.0,
        "response_fields": ["isbn13", "title", "publisher", "pub_year", "cover_url"],
    },
}


def l1_lookup(isbn: str, provider: str, *, config: Mapping[str, Any] | None = None,
              environ: Mapping[str, str] | None = None,
              http_get: Any = None) -> dict[str, Any]:
    """L1 适配层**骨架**调用（口径件 §5-5）。⇒ dict。

    行为（**不得伪造成功、不得阻塞主交付**）：
      * 供应商未登记 ⇒ 抛 `KeyError`；
      * **密钥缺失**（env 无 `env_key`）⇒ `{"skipped": True, "reason": "missing_key", "verify_state": "unverified"}`；
      * **无 http 客户端**（本单默认 `http_get=None`，不接真网）⇒ `{"skipped": True, "reason": "no_http_client"}`；
      * 传入 `http_get`（阶段 2）⇒ 由调用方注入实现，本骨架只做配置装配与限速占位。

    `environ` 缺省读 `os.environ`（**只读，不写**）。
    """
    cfg_all = L1_PROVIDERS if config is None else config
    if provider not in cfg_all:
        raise KeyError(f"未登记的 L1 供应商：{provider}（已知 {sorted(cfg_all)}）")
    cfg = cfg_all[provider]
    env = os.environ if environ is None else environ
    key = env.get(cfg.get("env_key", ""), None)
    base = {"provider": provider, "label": cfg.get("label"), "isbn": isbn,
            "source": f"api_{provider}", "endpoint": cfg.get("endpoint"),
            "timeout_s": cfg.get("timeout_s"), "rate_limit_qps": cfg.get("rate_limit_qps"),
            "key_env": cfg.get("env_key"), "config_driven": True, "called_network": False}
    if not key:
        base.update({"skipped": True, "reason": "missing_key", "verify_state": "unverified",
                     "note": f"环境变量 {cfg.get('env_key')} 缺失 ⇒ 跳过（不伪造成功）："
                             + L1_STAGE1_DISABLED_REASON})
        return base
    if http_get is None:
        base.update({"skipped": True, "reason": "no_http_client", "verify_state": "unverified",
                     "note": "密钥已配置，但本骨架未注入 http 客户端（本单不接真网）⇒ 跳过"})
        return base
    # 阶段 2：真实调用由调用方注入的 http_get 执行（本骨架构装配 ＋ 限速占位，不在此实现网络细节）。
    base.update({"skipped": False, "reason": "delegated", "verify_state": "unverified",
                 "note": "骨架：真实网络调用归阶段 2（此处仅登记装配点，不伪造响应）"})
    return base


# ===========================================================================
# 豆瓣**只读**封面 / 简介：**仅登记接口形态与缓存位，不进校验链**（口径件 §5-6 / X 层）
# ===========================================================================

#: 豆瓣只读登记（**登记形态，不实现网络**；`in_verify_chain=False` 为硬口径）。
DOUBAN_READONLY_REG: dict[str, Any] = {
    "provider": "douban",
    "mode": "read_only",
    "purpose": "封面 / 简介**仅展示**",
    "in_verify_chain": False,
    "network": "disabled_in_stage1",
    "interface": {
        "keyed_by": "isbn13",
        "response_fields": ["isbn13", "title", "publisher", "pubdate", "cover_url", "summary"],
        "endpoint_template": "",          # 登记形态；阶段 2/需联网时再填
        "rate_limit_qps": 0.5,
    },
    "cache_slot": "var/biblio_cache/douban/<isbn13>.json",
    "note": "Kevin 明示：豆瓣**只读封面/简介，不参与元数据校验**（口径件 §2 X 层 / §5-6）。",
}


def douban_registration() -> dict[str, Any]:
    """⇒ 豆瓣只读登记（**深拷贝**，防调用方误改常量；`in_verify_chain=False` 不可改）。"""
    return json.loads(json.dumps(DOUBAN_READONLY_REG))
