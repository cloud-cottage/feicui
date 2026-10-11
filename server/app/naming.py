"""印面影像命名地基（Kong / 命名单 · 2026-10-11）。

**纯函数模块**：只依赖标准库；**不 import 任何 DB / 图像栈**（`sqlite3` / `cv2` / `pymupdf` /
`PIL` 一律不出现），因此可被接口层（`server/.venv`，无图像栈）与 worker 侧（`venv`，有图像栈）
**两侧共用**，与 `server/app/colorcal.py` 同款约束。

## 口径（真源：`docs/image-naming-draft-v0.1.md` §6 结论 ＋ §6.1 落地清单）

名字形 `P<页码>-C<列号>-R<行号>`：**大写 `P`/`C`/`R` ＋ 短横、不补零**（如 `P299-C1-R3`）。

**原始切片 `-O`（2026-10-11 新增；口径真源 `docs/image-original-crop-draft-v0.1.md` §2）**：
每枚印面除**校正件** `P<页>-C<列>-R<行>.tiff` 外，另出一份**原始切片**
`P<页>-C<列>-R<行>-O.tiff`（`O` ＝ Original）：

* **`-O` 后缀排在扩展名之前**（大写 `O`、短横分隔、不补零）；
* **同几何、同容器、同目录**（同 `bbox` / 同渲染倍率 / TIFF RGB 8-bit ＋ Deflate）；
* **无颜色处理**（不跑 V3）；`O` 路径由命名规则**派生**
  （校正件名把 `.tiff` 换成 `-O.tiff`）⇒ **不落库、不新增列**。


| 位 | 口径 |
| --- | --- |
| `P` | ＝ `stamps.page`（**1-based**；不用书上印刷页码） |
| `C` | ＝ **页面级列号**（左→右，`1` 起）；按 **x 中心**做 1D 间隙聚类，**列间阈值 ＝ 中位印宽 × 0.6，下限 8 px** |
| `R` | ＝ **该列内自上而下的位次**（`1` 起；**秩次法**，构造上**页内唯一**） |

落点 `output/books/<目录键>/`；目录键：**尽可能 ISBN，无 ISBN 落中文书名**，未确认者回落 PDF 名
（见 `config/book_dir_keys.json`，加法文件，待 Jing 入册）。

## 红线（本模块自身不改任何状态）

只读、无副作用：不写盘、不写库、不建 job。写盘 / 落库由调用方负责。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    # 常量
    "NAME_RE",
    "NAME_RE_TIFF",
    "ORIGINAL_SUFFIX",
    "NAME_RE_ORIG",
    "COLUMN_GAP_WIDTH_FACTOR",
    "COLUMN_GAP_MIN_PX",
    "DEFAULT_DIR_KEYS_PATH",
    # C/R 推导
    "assign_cr",
    "assign_cr_ex",
    "column_gap_threshold",
    "n_columns",
    # 自检
    "page_duplicate_pairs",
    "assert_page_unique",
    "is_page_unique",
    # 名字 / 目录键
    "name_for",
    "name_for_original",
    "is_original_name",
    "parse_name",
    "parse_original_name",
    "matches_name",
    "matches_original_name",
    "original_name_from_corrected",
    "normalize_book_name",
    "dir_key_for",
    "dir_key_entry",
    "load_dir_keys",
]

# ---------------------------------------------------------------------------
# 常量（**全部单点可改**）
# ---------------------------------------------------------------------------

#: 列间阈值因子：阈值 ＝ 中位印宽 × 本因子（口径 §6.1-1）。
COLUMN_GAP_WIDTH_FACTOR = 0.6
#: 列间阈值下限（px）——防「整页同一列」被过窄的印面拉碎（口径 §6.1-1）。
COLUMN_GAP_MIN_PX = 8.0

#: 名字形通用正则（大写 P/C/R、短横、不补零；扩展名须为 `.xxx`）。
NAME_RE = re.compile(r"^P(?P<page>[0-9]+)-C(?P<col>[0-9]+)-R(?P<row>[0-9]+)\.(?P<ext>[A-Za-z0-9]+)$")
#: 本单验收用的 TIFF 面正则（逐字照派单 (b)）。**只匹配校正件**（`-O` 原片不匹配）。
NAME_RE_TIFF = re.compile(r"^P[0-9]+-C[0-9]+-R[0-9]+\.tiff$")

#: 原始切片后缀（`O` ＝ Original）；**排在扩展名之前**（口径件 §2「命名」）。
ORIGINAL_SUFFIX = "-O"
#: 原始切片名字形正则：`P<页>-C<列>-R<行>-O.<ext>`（大写 `O`、短横、不补零）。
NAME_RE_ORIG = re.compile(
    r"^P(?P<page>[0-9]+)-C(?P<col>[0-9]+)-R(?P<row>[0-9]+)-O\.(?P<ext>[A-Za-z0-9]+)$"
)

#: 目录键表（加法文件）默认路径：`<feicui>/config/book_dir_keys.json`。
DEFAULT_DIR_KEYS_PATH = Path(__file__).resolve().parents[2] / "config" / "book_dir_keys.json"


# ---------------------------------------------------------------------------
# C / R 推导（纯函数）
# ---------------------------------------------------------------------------

def _median(values: Sequence[float]) -> float:
    """中位数（偶数个取中间两者均值）。空序列由调用方保证不进入。"""
    xs = sorted(float(v) for v in values)
    n = len(xs)
    if n == 0:
        raise ValueError("median of empty sequence")
    mid = n // 2
    if n % 2 == 1:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def column_gap_threshold(widths: Iterable[float]) -> float:
    """列间阈值 ＝ `max(中位印宽 × COLUMN_GAP_WIDTH_FACTOR, COLUMN_GAP_MIN_PX)`。

    `widths` ＝ 页内各枚印面 bbox 的宽（`x2 - x1`）。空页 ⇒ 阈值取下限。
    """
    ws = [float(w) for w in widths]
    if not ws:
        return COLUMN_GAP_MIN_PX
    return max(_median(ws) * COLUMN_GAP_WIDTH_FACTOR, COLUMN_GAP_MIN_PX)


def assign_cr(bboxes: Iterable[Sequence[float]]) -> list[tuple[int, int]]:
    """入参〔页内各枚印面 bbox `(x1,y1,x2,y2)`〕⇒ 逐枚 `(C, R)`（**与入参同序**）。

    算法（口径 §6.1-1）：
      ① 每枚取 **x 中心**，按 x 中心升序（并列时按 y 中心、再按原下标，保证确定性）；
      ② **1D 间隙切分**：相邻 x 中心差 `> 阈值` 即开新列 ⇒ 列号 `C` 自左向右 `1..K`；
      ③ 列内按 **y 中心**升序得 **秩次** `R` 自 `1` 起。

    构造上 **页内 `(C,R)` 恒唯一**（见 `assert_page_unique`：
    同列内 `R` 互异；不同列 `C` 互异 ⇒ 二元组不可能重复；完全相同 bbox 的重复项也会因秩次而分到不同 `R`）。
    """
    boxes = [(float(b[0]), float(b[1]), float(b[2]), float(b[3])) for b in bboxes]
    n = len(boxes)
    if n == 0:
        return []
    if n == 1:
        return [(1, 1)]

    widths = [x2 - x1 for (x1, _y1, x2, _y2) in boxes]
    thr = column_gap_threshold(widths)

    def cx(i: int) -> float:
        x1, _y1, x2, _y2 = boxes[i]
        return (x1 + x2) / 2.0

    def cy(i: int) -> float:
        _x1, y1, _x2, y2 = boxes[i]
        return (y1 + y2) / 2.0

    order = sorted(range(n), key=lambda i: (cx(i), cy(i), i))

    columns: list[list[int]] = []
    cur: list[int] = [order[0]]
    for prev_i, i in zip(order, order[1:]):
        if cx(i) - cx(prev_i) > thr:
            columns.append(cur)
            cur = [i]
        else:
            cur.append(i)
    columns.append(cur)

    result: list[Any] = [None] * n
    for col_idx, members in enumerate(columns, start=1):
        for row_idx, i in enumerate(sorted(members, key=lambda j: (cy(j), cx(j), j)), start=1):
            result[i] = (col_idx, row_idx)
    return result  # type: ignore[return-value]


def assign_cr_ex(bboxes: Iterable[Sequence[float]]) -> tuple[list[tuple[int, int]], int]:
    """`assign_cr` ＋ **列数**（页内 `C` 的最大值；空页 ⇒ `0`）。"""
    pairs = assign_cr(bboxes)
    return pairs, n_columns(pairs)


def n_columns(assignments: Sequence[tuple[int, int]]) -> int:
    """列数 ＝ 页内出现的最大 `C`（空 ⇒ `0`）。"""
    return max((c for c, _r in assignments), default=0)


# ---------------------------------------------------------------------------
# 页内唯一性自检（构造上恒真；此处提供**断言函数**以机械判负）
# ---------------------------------------------------------------------------

def page_duplicate_pairs(assignments: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """返回页内 **重复**的 `(C,R)`（升序去重；空 ⇒ 页内唯一）。"""
    seen: set[tuple[int, int]] = set()
    dups: set[tuple[int, int]] = set()
    for c, r in assignments:
        key = (int(c), int(r))
        if key in seen:
            dups.add(key)
        seen.add(key)
    return sorted(dups)


def is_page_unique(assignments: Sequence[tuple[int, int]]) -> bool:
    """页内 `(C,R)` 唯一 ⇒ `True`。"""
    return not page_duplicate_pairs(assignments)


def assert_page_unique(assignments: Sequence[tuple[int, int]]) -> None:
    """页内 `(C,R)` 唯一性**断言**（构造上应恒真）。

    违则抛 `AssertionError`（机械判负；不静默、不回落）。
    """
    dups = page_duplicate_pairs(assignments)
    if dups:
        pretty = ", ".join(f"C{c}-R{r}" for c, r in dups)
        raise AssertionError(f"页内 (C,R) 撞名：{pretty}")


# ---------------------------------------------------------------------------
# 文件名 / 目录键
# ---------------------------------------------------------------------------

def name_for(page: int, c: int, r: int, ext: str = ".tiff") -> str:
    """名字形 `P<页码>-C<列号>-R<行号>.<ext>`（**大写、短横、不补零**）。

    `page`/`c`/`r` 均须 `>= 1`；`ext` 可带或不带前导点（如 `"tiff"` 与 `".tiff"` 等价）。
    """
    p, cc, rr = int(page), int(c), int(r)
    if p < 1 or cc < 1 or rr < 1:
        raise ValueError(f"页码/列号/行号须 >= 1：page={p} c={cc} r={rr}")
    if not ext:
        raise ValueError("ext 不得为空")
    if not ext.startswith("."):
        ext = "." + ext
    return f"P{p}-C{cc}-R{rr}{ext}"


def name_for_original(page: int, c: int, r: int, ext: str = ".tiff") -> str:
    """原始切片名字形 `P<页码>-C<列号>-R<行号>-O.<ext>`（**大写 `O`、短横、不补零**）。

    口径真源 `docs/image-original-crop-draft-v0.1.md` §2「命名」：`O` ＝ Original，
    **后缀排在扩展名之前**（例 `P40-C1-R1-O.tiff`）。`page`/`c`/`r` 均须 `>= 1`。
    """
    base = name_for(page, c, r, ext)          # 复用校验（页码/列号/行号 + 扩展名口径）
    suffix = _ext_with_dot(ext)
    return base[: -len(suffix)] + ORIGINAL_SUFFIX + suffix


def _ext_with_dot(ext: str) -> str:
    """扩展名规范化（补前导点）；空 ⇒ 抛错（与 `name_for` 同口径）。"""
    if not ext:
        raise ValueError("ext 不得为空")
    return ext if ext.startswith(".") else "." + ext


def is_original_name(name: str) -> bool:
    """`name` 是否合**原始切片**名字形（`P<p>-C<c>-R<r>-O.<ext>`）。"""
    return NAME_RE_ORIG.match(str(name)) is not None


def parse_original_name(name: str) -> dict[str, Any] | None:
    """解析**原始切片**名字形 ⇒ `{"page","col","row","ext"}`；不合形 ⇒ `None`。"""
    m = NAME_RE_ORIG.match(str(name))
    if not m:
        return None
    return {
        "page": int(m.group("page")),
        "col": int(m.group("col")),
        "row": int(m.group("row")),
        "ext": m.group("ext"),
    }


def matches_original_name(name: str, ext: str | None = None) -> bool:
    """`name` 是否合原始切片名字形；`ext` 给出时还须扩展名相同。"""
    info = parse_original_name(name)
    if info is None:
        return False
    if ext is None:
        return True
    want = ext[1:] if ext.startswith(".") else ext
    return info["ext"] == want


def original_name_from_corrected(name: str) -> str | None:
    """**校正件名 → 原始切片名**（派生；口径件 §2「落库」＝O 路径由命名派生）。

    `P40-C1-R1.tiff` ⇒ `P40-C1-R1-O.tiff`。入参不合校正件名字形 ⇒ `None`。
    """
    if not NAME_RE.match(str(name)):
        return None
    stem, dot, ext = str(name).rpartition(".")
    return f"{stem}{ORIGINAL_SUFFIX}{dot}{ext}"


def parse_name(name: str) -> dict[str, Any] | None:
    """解析名字形 ⇒ `{"page","col","row","ext"}`；不合形 ⇒ `None`。"""
    m = NAME_RE.match(name)
    if not m:
        return None
    return {
        "page": int(m.group("page")),
        "col": int(m.group("col")),
        "row": int(m.group("row")),
        "ext": m.group("ext"),
    }


def matches_name(name: str, ext: str | None = None) -> bool:
    """`name` 是否合名字形；`ext` 给出时（如 `"tiff"` / `".tiff"`）还须扩展名相同。"""
    info = parse_name(name)
    if info is None:
        return False
    if ext is None:
        return True
    want = ext[1:] if ext.startswith(".") else ext
    return info["ext"] == want


def normalize_book_name(pdf_name: str) -> str:
    """PDF 名 → **目录键回落用**的规范化书名：去扩展名、去首尾空白、内部连续空白压一格。

    只做机械规范化，**不猜书名**；ISBN 等映射一律走 `config/book_dir_keys.json`（显式、单点可改）。
    """
    stem = os.path.splitext(os.path.basename(str(pdf_name)))[0]
    return re.sub(r"\s+", " ", stem).strip()


def _books_table(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """兼容两种入参：整表（含顶层 `books`）或 `books` 子表本身。"""
    if not isinstance(mapping, Mapping):
        return {}
    books = mapping.get("books")
    if isinstance(books, Mapping):
        return books
    return mapping


def dir_key_entry(pdf_name: str, mapping: Mapping[str, Any] | None) -> tuple[str, str]:
    """⇒ `(dir_key, dir_key_source)`。

    已登记 ⇒ 取其 `dir_key` / `dir_key_source`；未登记 ⇒ 回落
    `(normalize_book_name(pdf_name), "fallback_unregistered")`（**未登记即暴露**，不静默）。
    """
    entry = _books_table(mapping).get(str(pdf_name))
    if isinstance(entry, Mapping) and entry.get("dir_key"):
        return str(entry["dir_key"]), str(entry.get("dir_key_source") or "unspecified")
    return normalize_book_name(pdf_name), "fallback_unregistered"


def dir_key_for(pdf_name: str, mapping: Mapping[str, Any] | None) -> str:
    """PDF 名 → **目录键**（`output/books/<目录键>/`）。

    已登记 ⇒ 表中 `dir_key`（ISBN 或中文书名）；未登记 ⇒ 回落规范化书名。
    """
    return dir_key_entry(pdf_name, mapping)[0]


def load_dir_keys(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """读入 `config/book_dir_keys.json`（默认路径见 `DEFAULT_DIR_KEYS_PATH`）。"""
    p = Path(path) if path is not None else DEFAULT_DIR_KEYS_PATH
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)
