#!/usr/bin/env python
# local-dist/src/field_extract.py
"""tab2 切图台：**印格字段提取**（印章 ↔ 释文 / 状态字 / 编号 ＋ 阅读顺序推断）。

## 来历与对拍

算法**逐条移植**自已跑通 6/6 的离线 PoC
`~/.hermes/profiles/zang/cache/scratch/poc_field_extract.py`（未重写、未加新招）。
测样：用户 2026-10-20 提供的二列三行印谱页（1222×1802，六枚印，编号 0421–0426）——
`local-dist/tests/fixtures/sample_rtl_ttb.png`；单测 `local-dist/tests/test_field_extract.py`
断言 **6/6 三字段全对**、`reading_order=='rtl-ttb'`、`order_source=='code-sequence'`。

## 流程（四轮过滤 ⇒ 就近归属 ⇒ 分类 ⇒ 纠错/排序）

1. 红印检测（复用 `src/seal_detect.py`，400dpi 系）；
2. 整页 OCR（`src/ocr_rapid.py`；可注入 `ocr_fn`，单测用假 OCR 跑纯逻辑）；
3. **四轮过滤**（顺序即优先级，先命中先归属）：
   * ① **印章内**：文本框中心落在某枚印章 bbox（外扩 6%）内 ⇒ 篆书区，一律剔；
   * ② **页边带**：左 4.5%、上 5.5%、**下仅 2.2%**（末行印格的状态字/编号贴着版心底，
     下边距给大就误剔）；右边缘不判（右列常贴裁切边）；
   * ③ **离印章过远**：与最近印章框距 > `印章平均边长 × 2.2`（且不小于页短边 10%）⇒ 版心外栏目名；
   * ④ **噪声**：纯数字短串（页码、用户手写标注号 1–6 等）。
4. **就近归属**：按「bbox 边缘距」把剩余文本归到最近的一枚印；
5. **分类**：3–5 位数字（`O/o` 归一成 `0`）⇒ 编号 `code`；**仅汉字**单字 ⇒ 状态字 `status`；
   其余多字串 ⇒ 释文 `inscription`（取最长；并列取分数高者）；数字/符号单字 ⇒ 噪声。
   **释文污染先剔**（`is_noise_text`）：纯中文数字页码（`〇七二`）与类目标题
   （`單姓單名字印`）在归属前就进 `dropped.noise_text`，不进释文候选；某印剔完无释文 ⇒
   释文留空 ＋ `needs_review=True`。
   **状态字按位置窗口 + 全局一对一归属**（`allocate_status`，`strict_status=True` 默认）：
   候选中心须落在「印章左缘左 1.6 倍中位印宽 ~ 右缘右 10%」且「印章底边下方 −0.05~2.4 倍印高」
   的窗口内（印谱把状态字排在本格左侧的字栏/编号行上）；所有（印章×候选）对按 bbox 间距升序
   **贪心**分配，每个候选最多归一枚、每枚最多一个，**抢不到的印章留空**（不猜、不拿隔壁的）。
   旧口径「取距印章最近的汉字单字」保留在 `status_legacy` 里仅供对比（`strict_status=False`
   即完全回落旧行为）。
6. **纠错硬口径（用户 2026-10-20 裁定）**：**禁止猜测式改字**（曾把正确的「中羞行府」误改成
   「中差行府」）。只允许两个来源：
   * ① 权威词表 `authoritative`：`{原始: 核定}` 映射（人工真值/已核定映射）——**唯一允许改字**的路径；
   * ② 同页多数票：同一释文出现 ≥ `min_votes`（默认 3）次且完全一致 ⇒ 标 `inscription_verified`。
   其余**原样输出**；`inscription_score < 0.95` 且未验证 ⇒ 标 `needs_review`（交人工确认，不改字）。
7. **阅读顺序**：优先按编号序列推断（编号即版序）⇒ 比较首末 x 得 rtl/ltr、同列相邻 y 得 ttb/btt
   （本样本 ⇒ `rtl-ttb`）；无编号 ⇒ 用调用方传入，其次**书级元数据**（`book.reading_order`
   ⇒ `book-meta`），最后兜底 `fallback_order`（缺省 `ltr-ttb`；切图台传 `rtl-ttb`）。
   `order_source ∈ {code-sequence, manual, book-meta, fallback}`。
   另出 **`order_audit`**：逐页判「带编号页里编号升序是否与 (C,R) 字典序升序一致」⇒
   `consistent / inconsistent / no-code`（**只审计、不阻断裁切**）。

## C/R 方向（与 `seal_crop` 同一真源）

`grid_positions(boxes, reading_order=…)`：**行带（R）按垂直方向**编号（`ttb` 上行为 R1，
`btt` 下行为 R1），**列（C）按水平方向**编号（`rtl` **右列＝C1**，`ltr` 左列＝C1）。
之前按 x 升序把左列当 C1，本书是反的 —— 命名正确性就靠这一条。

## 返回（**永不抛**）

`extract_fields(...)` ⇒
`{ok, size, reading_order, order_source, order_audit, strict_status, ocr_available,
seals:[{read_order, idx, c, r, box, inscription, inscription_score, inscription_verified,
status, status_score, status_legacy, code, code_score, needs_review, inscription_dropped_noise,
candidates, text_boxes}], dropped:{inside_seal, edge, far, noise, noise_text},
dropped_texts:{…}, far_limit, count, elapsed_s}`；失败 ⇒ `{ok: False, reason, msg}`。

## 无 OCR 时的降级（`斐萃_lite` / 阶段 1 包）

`ocr_capable()` 只**探测**（`importlib.util.find_spec`，不加载模型）：`rapidocr` 或适配层
`src.ocr_rapid` 任一缺失 ⇒ False。此时 `extract_fields` **仍返回 `ok: True`**：

* 只做**红印检测**（`seal_detect`，不依赖 OCR），`boxes` 照常给；
* 每枚 `seals[i]` 的 `inscription/status/code` 均为**空字符串**，三个 `*_score` 为 `None`；
* `ocr_available: False`，`note` ＝ `OCR_UNAVAILABLE_NOTE`（提示手动填 / 改用 `斐萃_pro`）；
* `reading_order` 回落 `ltr-ttb`、`order_source='fallback'`（无编号可推断）。

## 红线

纯逻辑层：**不 import webview / streamlit / ui**；不写盘、不落库、不联网；模块顶层**只用 stdlib**
（重依赖 `cv2/numpy/OCR` 都在函数内延迟 import）。
"""
from __future__ import annotations

import importlib.util
import re
import time

__all__ = [
    "DETECT_DPI",
    "READING_ORDERS",
    "DEFAULT_READING_ORDER",
    "FALLBACK_READING_ORDER",
    "EDGE_BANDS",
    "FAR_FACTOR",
    "MIN_VOTES",
    "LOW_SCORE",
    "STATUS_LEFT_FACTOR",
    "STATUS_RIGHT_TOL",
    "STATUS_BELOW",
    "CJK_NUMERAL_CHARS",
    "CATEGORY_TITLE_WORDS",
    "CATEGORY_TITLE_MIN_LEN",
    "OCR_UNAVAILABLE_NOTE",
    "normalize_reading_order",
    "grid_positions",
    "reading_sequence",
    "classify_text",
    "is_noise_text",
    "center_in",
    "bbox_gap",
    "detect_seals",
    "render_page",
    "infer_reading_order",
    "audit_order",
    "ocr_capable",
    "extract_fields",
]

#: 检测/预览 dpi —— 与库内 `stamps` bbox 同系（别改）。
DETECT_DPI = 400
#: 阅读顺序取值（`<horiz>-<vert>`；`ttb-rtl` 这类反向写法也能识别，见 `normalize_reading_order`）。
READING_ORDERS = ("rtl-ttb", "ltr-ttb", "rtl-btt", "ltr-btt")
#: 无编号且调用方没指定时的兜底（**保持改动前行为**：左列 C1、上行 R1）。
DEFAULT_READING_ORDER = "ltr-ttb"
#: **本书级兜底**：书级元数据里没有 `reading_order` 时，切图台（`autocrop`）用这一档 ——
#: 中文印谱版序常态是 **右起竖排**（本书《秦印类编 检索版》即 rtl）。`extract_fields` 本体
#: 仍以 `DEFAULT_READING_ORDER` 为缺省（老单测/工具端点的行为一字不改）。
FALLBACK_READING_ORDER = "rtl-ttb"
#: 页边带（占页宽/页高比例）：左 / 上 / 下。**下边距只 2.2%**（贴版心底的字段不能误剔）。
EDGE_BANDS = {"left": 0.045, "top": 0.055, "bottom": 0.022}
#: 「离印章过远」阈值因子：印章平均边长 × 2.2（且不小于页短边 10%）。
FAR_FACTOR = 2.2
#: 多数票门槛（同页同一释文完全一致的次数）。
MIN_VOTES = 3
#: 低分警戒线：未验证且低于此分 ⇒ `needs_review`。
LOW_SCORE = 0.95

# ── 状态字：**位置约束**（旧规则「取最近的汉字单字」在密集排版下会串格，见模块 docstring §5）──
#: 候选允许落在印章**左缘再往左**多少倍「本页中位印宽」（印谱把状态字排在各格左侧的
#: 字栏里，实测质心在 `-1.1 ~ -2.8` 倍印宽之间；用中位印宽而不是各自印宽，窄印不会把窗口撑歪）。
STATUS_LEFT_FACTOR = 1.6
#: 右缘容差（占中位印宽）：状态字**不排到印章右边**，只留一点点容差。
STATUS_RIGHT_TOL = 0.10
#: y 窗口（相对印高）：候选中心必须落在「印章底边下方 `lo×h` 到 `hi×h`」之间 ——
#: 即**本格的下方字段行**（编号/状态字那一行），不许取上一行/下一行格里的字。
STATUS_BELOW = (-0.05, 2.4)

# ── 释文污染（页码 / 类目标题）——归属前先剔，别让它进释文候选 ──────────────
#: 中文数字（含 `〇`）：纯这些字符组成的串 ⇒ 页码（实测 6.6% 释文是 `〇〇三` 这类）。
CJK_NUMERAL_CHARS = "〇零一二三四五六七八九十百千"
#: 类目标题关键词白名单（长度 ≥ `CATEGORY_TITLE_MIN_LEN` 且含其一 ⇒ 判污染）。
CATEGORY_TITLE_WORDS = ("單姓", "複姓", "名字印", "字印", "姓名印", "官印", "私印",
                        "單名", "複名", "姓名", "類編", "目錄")
#: 类目标题**最短长度**：`官印`/`私印` 这种 2 字本身可能是真释文，只剔 4 字以上的标题串。
CATEGORY_TITLE_MIN_LEN = 4

#: 无 OCR 能力时的**可读**提示（UI 原样显示；口径同 `api.OCR_*`）。
OCR_UNAVAILABLE_NOTE = ("本版不含 OCR（斐萃_lite）⇒ 释文/状态/编号请手动填写，"
                        "或改用 斐萃_pro（含 OCR）自动识别")

_CODE_RE = re.compile(r"[0-9O]{3,5}")
_DIGITS_RE = re.compile(r"[0-9Oo]+")
_HAN_RE = re.compile(r"[\u4e00-\u9fff]")


# ── 几何 ────────────────────────────────────────────────────────────────────
def _as_box(b) -> tuple[int, int, int, int]:
    """宽容入参（`{x1..y2}` / 四元组）⇒ 整数 `(x1,y1,x2,y2)`（自动正序）。"""
    if isinstance(b, dict):
        vals = [b.get(k) for k in ("x1", "y1", "x2", "y2")]
    else:
        vals = list(b)[:4]
    if len(vals) < 4 or any(v is None for v in vals):
        raise ValueError(f"框缺字段：{b!r}")
    nums = [float(v) for v in vals if v is not None]      # 上面已拦 None（供类型检查）
    x1, y1, x2, y2 = (int(round(v)) for v in nums)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def bbox_gap(a, b) -> float:
    """两 bbox 的**边缘距离**（相交 ⇒ 0）。"""
    ax1, ay1, ax2, ay2 = _as_box(a)
    bx1, by1, bx2, by2 = _as_box(b)
    dx = max(0, max(ax1, bx1) - min(ax2, bx2))
    dy = max(0, max(ay1, by1) - min(ay2, by2))
    return (dx * dx + dy * dy) ** 0.5


def center_in(box, outer, pad_ratio: float = 0.06) -> bool:
    """`box` 中心是否落在 `outer`（外扩 `pad_ratio`）内 —— 判「篆书区文本」用。"""
    x1, y1, x2, y2 = _as_box(outer)
    px, py = (x2 - x1) * pad_ratio, (y2 - y1) * pad_ratio
    bx1, by1, bx2, by2 = _as_box(box)
    cx, cy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
    return (x1 - px) <= cx <= (x2 + px) and (y1 - py) <= cy <= (y2 + py)


def normalize_reading_order(value) -> str | None:
    """任意写法 ⇒ 规范 `<horiz>-<vert>`（`ttb-rtl`／`rtl_ttb`／`RTL-TTB` 都认）；认不出 ⇒ `None`。"""
    if value is None:
        return None
    parts = [p for p in re.split(r"[-_\s]+", str(value).strip().lower()) if p]
    h = next((p for p in parts if p in ("rtl", "ltr")), None)
    v = next((p for p in parts if p in ("ttb", "btt")), None)
    if not h or not v:
        return None
    return f"{h}-{v}"


def grid_positions(boxes, row_overlap: float = 0.5,
                   reading_order: str = DEFAULT_READING_ORDER) -> list[tuple[int, int]]:
    """⇒ **与入参同序**的 `(C, R)`（1 起）；列向/行向由 `reading_order` 决定。

    * 行带：按 y 中心升序扫，与已有带「垂直重叠 ≥ 较矮框高 × `row_overlap`」⇒ 归同带；
    * `R`：`ttb` ⇒ 最上带 R1；`btt` ⇒ 最下带 R1；
    * `C`：`ltr` ⇒ 带内自左向右 C1；`rtl` ⇒ 带内**自右向左** C1（**右列＝C1**）。
    """
    order = normalize_reading_order(reading_order) or DEFAULT_READING_ORDER
    horiz, vert = order.split("-")
    norm = [_as_box(b) for b in (boxes or [])]
    n = len(norm)
    if n == 0:
        return []
    info = []
    for i, b in enumerate(norm):
        info.append({"i": i, "y1": b[1], "y2": b[3], "cx": (b[0] + b[2]) / 2.0,
                     "cy": (b[1] + b[3]) / 2.0, "h": max(1, b[3] - b[1])})
    bands: list[list[dict]] = []
    for it in sorted(info, key=lambda d: (d["cy"], d["cx"], d["i"])):
        for band in bands:                       # 自上而下第一个「够得着」的带
            top = min(x["y1"] for x in band)
            bot = max(x["y2"] for x in band)
            od = min(bot, it["y2"]) - max(top, it["y1"])
            short = min(min(x["h"] for x in band), it["h"])
            if od >= row_overlap * short:
                band.append(it)
                break
        else:
            bands.append([it])
    out: list = [None] * n
    nb = len(bands)
    for bi, band in enumerate(bands):
        r = (bi + 1) if vert == "ttb" else (nb - bi)
        rev = (horiz == "rtl")
        for c, it in enumerate(sorted(band, key=lambda d: (d["cx"], d["i"]), reverse=rev), start=1):
            out[it["i"]] = (c, r)
    return out  # type: ignore[return-value]


def reading_sequence(boxes, reading_order: str = DEFAULT_READING_ORDER) -> list[int]:
    """⇒ **入参下标**的阅读序（列优先：同一 C 自上而下读完后换下一列 —— 印谱竖排读法）。"""
    pos = grid_positions(boxes, reading_order=reading_order)
    return [i for i, _ in sorted(enumerate(pos), key=lambda kv: (kv[1][0], kv[1][1]))]


# ── 分类 / 过滤 ───────────────────────────────────────────────────────────────
def classify_text(text) -> str:
    """⇒ `code` | `status` | `inscription` | `noise`（规则见模块 docstring §5）。"""
    t = str(text or "").strip()
    if _CODE_RE.fullmatch(t):
        return "code"
    if _DIGITS_RE.fullmatch(t):
        return "noise"                       # 页码 / 标注号 1–6
    if len(t) == 1:
        return "status" if _HAN_RE.fullmatch(t) else "noise"
    return "inscription"


def normalize_code(text) -> str:
    """编号归一：常见误识 `O/o → 0`（只动数字位，不改字）。"""
    return str(text or "").replace("O", "0").replace("o", "0")


def is_noise_text(text, extra_words=None) -> bool:
    """**释文污染**判定 ⇒ True 表示「这不是释文，是版面元信息」（页码 / 类目标题 / 纯编号）。

    三条规则（**归属前先剔**，不剔就会 6.6% 页码 ＋ 6.8% 类目标题混进释文）：

    1. **纯中文数字页码**：整串只由 `CJK_NUMERAL_CHARS`（`〇零一二…百千`）＋ 全角/半角数字
       组成，长度 ≥1 ⇒ 页码（实测形态 `〇〇三` / `〇七二` / `二七二`）。单一数字字符串也命中
       （它只可能当状态字用，不会被当成释文）。
    2. **类目标题**：长度 ≥ `CATEGORY_TITLE_MIN_LEN`（4）且含 `CATEGORY_TITLE_WORDS` 任一
       关键词（`單姓`/`複姓`/`名字印`/`字印`/`姓名印`/`官印`/`私印` …，`extra_words` 可加）。
       只剔 4 字以上 ⇒ `官印`/`私印` 这种 2 字真释文不受影响。
    3. **纯编号**：`3–5 位数字`（含 `O/o` 误识）本身就是编号字段，**不得回流成释文**；
       这一条与 `classify_text` 的 `code` 分支一致，此处兜一层防回归。

    `extra_words`：本书特有的类目标题词（白名单可配，不写死在调用点）。
    """
    t = str(text or "").strip()
    if not t:
        return False                                   # 空串不算污染（是「没识别到」，另走留空逻辑）
    if _CODE_RE.fullmatch(t) or _DIGITS_RE.fullmatch(t):
        return True                                    # ③ 纯编号 / 纯数字
    if all(ch in CJK_NUMERAL_CHARS or ch.isdigit()
           or ch in "０１２３４５６７８９" for ch in t):
        return True                                    # ① 纯中文数字页码
    words = tuple(CATEGORY_TITLE_WORDS) + tuple(extra_words or ())
    if len(t) >= int(CATEGORY_TITLE_MIN_LEN) and any(w and w in t for w in words):
        return True                                    # ② 类目标题
    return False


def _median(values) -> float:
    vals = sorted(float(v) for v in values if v is not None)
    if not vals:
        return 0.0
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def status_window(seal_box, median_w: float = 0.0) -> tuple[float, float, float, float]:
    """状态字候选的**允许矩形** `(x1,y1,x2,y2)`（中心须落在其内）。

    * x：`[印章左缘 − STATUS_LEFT_FACTOR×中位印宽, 印章右缘 + STATUS_RIGHT_TOL×中位印宽]`
      —— 印谱把状态字排在**本格左侧的字栏**里（实测质心 −1.1 ~ −2.8 倍印宽），
      而「印章正下方」只是其中一种版式；窗口按**中位印宽**量，窄印/大印都不歪。
    * y：`[印章底边 + STATUS_BELOW[0]×印高, 印章底边 + STATUS_BELOW[1]×印高]`
      —— 只认**本格下方**那一行字段，上下邻格的字进不来。
    """
    x1, y1, x2, y2 = _as_box(seal_box)
    h = max(1.0, float(y2 - y1))
    mw = float(median_w) if median_w else float(max(1, x2 - x1))
    lo, hi = STATUS_BELOW
    return (x1 - STATUS_LEFT_FACTOR * mw, y2 + lo * h,
            x2 + STATUS_RIGHT_TOL * mw, y2 + hi * h)


def _center_in_rect(box, rect) -> bool:
    bx1, by1, bx2, by2 = _as_box(box)
    cx, cy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
    rx1, ry1, rx2, ry2 = rect
    return rx1 <= cx <= rx2 and ry1 <= cy <= ry2


def allocate_status(seal_boxes, candidates, *, strict: bool = True,
                    median_w: float | None = None) -> list[dict | None]:
    """状态字归属 ⇒ **与 `seal_boxes` 同序**的候选（`None` ＝ 留空）。

    **一对一**（`strict=True`，默认）：先把所有「印章 × 候选」的合法配对找出来 ——
    * 候选必须是纯汉字单字（`classify_text(...) == 'status'`）、中心落在 `status_window` 内；
    * 再按 **bbox 边缘距升序贪心**分配：每个候选最多归一枚印章、每枚最多一个状态字；
    * **抢不到的印章 ⇒ 留空**（不猜、不拿隔壁的 —— 旧「取最近单字」就是在这里串格的）。

    `strict=False` ⇒ 回落旧行为（每个印章取「最近的汉字单字」，不做一对一、不看位置），
    只用于对比，不作生产口径。
    """
    seals = [_as_box(b) for b in (seal_boxes or [])]
    cands = [c for c in (candidates or []) if str(c.get("text") or "").strip()
             and classify_text(c.get("text")) == "status"]
    if not seals or not cands:
        return [None] * len(seals)
    out: list[dict | None] = [None] * len(seals)
    if not strict:                                        # 旧口径：各自取最近单字（可重复、可串格）
        for i, sb in enumerate(seals):
            best = min(cands, key=lambda c: bbox_gap(c.get("box"), sb))
            out[i] = best
        return out
    mw = median_w if median_w is not None else _median([b[2] - b[0] for b in seals])
    pairs: list[tuple[float, int, int]] = []
    for i, sb in enumerate(seals):
        win = status_window(sb, mw)
        for j, c in enumerate(cands):
            if _center_in_rect(c.get("box"), win):
                pairs.append((bbox_gap(c.get("box"), sb), i, j))
    pairs.sort(key=lambda p: (p[0], p[1], p[2]))
    used_c: set[int] = set()
    for gap, i, j in pairs:
        if out[i] is not None or j in used_c:
            continue
        out[i] = cands[j]
        used_c.add(j)
    return out


def audit_order(seals) -> dict:
    """**编号 ↔ (C,R) 一致性审计**（只读、不改任何字段、不阻断裁切）。

    ⇒ `{"status": "consistent"|"inconsistent"|"no-code", "coded": n, "seals": n,
        "violations": [{"code","c","r","prev_code"}]}`。

    判法：取**带编号**的印章按编号字符串升序；若它们的 `(C, R)` 也恰好是字典序升序 ⇒
    `consistent`；有编号但顺序不一致 ⇒ `inconsistent`（逐条列出越位的那几枚）；
    有编号的不足 2 枚 ⇒ `no-code`（没有可比较的序列）。
    """
    seals = list(seals or [])
    coded = [s for s in seals if str(s.get("code") or "").strip()]
    info = {"status": "no-code", "coded": len(coded), "seals": len(seals), "violations": []}
    if len(coded) < 2:
        return info
    seq = sorted(coded, key=lambda s: str(s.get("code")))
    positions = [(int(s.get("c") or 0), int(s.get("r") or 0)) for s in seq]
    if all(positions[k] < positions[k + 1] for k in range(len(positions) - 1)):
        info["status"] = "consistent"
        return info
    info["status"] = "inconsistent"
    for k in range(1, len(positions)):
        if positions[k] <= positions[k - 1]:
            info["violations"].append({"code": seq[k].get("code"),
                                       "prev_code": seq[k - 1].get("code"),
                                       "c": positions[k][0], "r": positions[k][1],
                                       "prev_c": positions[k - 1][0], "prev_r": positions[k - 1][1]})
    return info



def is_edge_text(box, width: int, height: int, *,
                 left: float = EDGE_BANDS["left"], top: float = EDGE_BANDS["top"],
                 bottom: float = EDGE_BANDS["bottom"]) -> bool:
    """版心外文本（书名/页码/栏目标签）⇒ True。**右边缘不判**（右列常贴裁切边）。"""
    x1, y1, x2, y2 = _as_box(box)
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    return cx < width * left or cy < height * top or cy > height * (1 - bottom)


# ── 检测 / 渲页（复用既有实现）────────────────────────────────────────────────
def detect_seals(bgr, **kw) -> list[tuple[int, int, int, int]]:
    """红印检测 ⇒ 四元组列表（复用 `src/seal_detect.detect_seals`；参数透传，`merge` 默认开）。"""
    from src import seal_detect as _sd
    boxes = _sd.detect_seals(bgr, **kw)
    return [_as_box(b) for b in boxes]


def render_page(pdf, page: int, dpi: int = DETECT_DPI):
    """渲一页 ⇒ **BGR uint8**（复用 `src/seal_detect.render_page`；1-based）。"""
    from src import seal_detect as _sd
    return _sd.render_page(pdf, page, dpi)


# ── OCR 适配 ─────────────────────────────────────────────────────────────────
def ocr_capable(ocr_fn=None) -> bool:
    """本机/本包**能不能**做 OCR —— 只探测，**不加载模型**（不 import onnxruntime）。

    * 已注入 `ocr_fn` ⇒ True（单测 / 离线纯逻辑路径）；
    * 否则 `rapidocr` 与适配层 `src.ocr_rapid` **都要在**：阶段 1 打包件
      （`斐萃_lite.app`，`feicui.spec` 把 `rapidocr`/`onnxruntime` 全进 `excludes`）两者都没有
      ⇒ False，调用方据此**优雅降级**（只做红印检测，字段留空交人工填），而不是点一下就
      `ModuleNotFoundError`。
    """
    if ocr_fn is not None:
        return True
    try:
        if importlib.util.find_spec("rapidocr") is None:
            return False
        return importlib.util.find_spec("src.ocr_rapid") is not None
    except Exception:                                    # 探测本身失败 ⇒ 当作不可用（不抛）
        return False


def _ocr_items(bgr, ocr_fn=None) -> list[dict]:
    """OCR ⇒ `[{text, score, box}]`（`ocr_fn` 可注入：签名 `fn(bgr) -> {texts,scores,boxes}`）。"""
    if ocr_fn is None:
        from src import ocr_rapid as _ocr
        ocr_fn = _ocr.ocr_image
    res = ocr_fn(bgr) or {}
    texts = list(res.get("texts") or [])
    scores = list(res.get("scores") or [])
    boxes = list(res.get("boxes") or [])
    items: list[dict] = []
    for i, t in enumerate(texts):
        b = boxes[i] if i < len(boxes) else None
        if not b:
            continue
        xs = [float(p[0]) for p in b]
        ys = [float(p[1]) for p in b]
        score = float(scores[i]) if i < len(scores) and scores[i] is not None else 0.0
        items.append({"text": str(t), "score": score,
                      "box": (min(xs), min(ys), max(xs), max(ys))})
    return items


# ── 阅读顺序推断 ─────────────────────────────────────────────────────────────
def infer_reading_order(seals, book_order=None,
                        fallback_order: str = DEFAULT_READING_ORDER) -> tuple[str, str]:
    """阅读顺序 ⇒ `(order, source)`，四级优先：**编号 > 本书元数据 > 兜底**。

    * `source='code-sequence'`：全部印章都有编号且 ≥2 枚 —— 比较首末 x 得 rtl/ltr、
      同列相邻 y 得 ttb/btt（判法照 PoC）；
    * `source='book-meta'`：无编号可用、但调用方给了**书级元数据** `book_order`
      （`book.reading_order`，如 `rtl-ttb`）⇒ 用它（`fallback` 页不许再瞎猜方向）；
    * `source='fallback'`：两者都没有 ⇒ 用 `fallback_order`（缺省 `DEFAULT_READING_ORDER`；
      切图台传 `FALLBACK_READING_ORDER`＝`rtl-ttb`，因为中文印谱版序常态右起）。
    """
    seals = list(seals or [])
    codes = [s.get("code") for s in seals]
    if len(seals) >= 2 and all(codes):
        ordered = sorted(seals, key=lambda s: str(s["code"]))
        xs = [(_as_box(s["box"])[0] + _as_box(s["box"])[2]) / 2.0 for s in ordered]
        ys = [(_as_box(s["box"])[1] + _as_box(s["box"])[3]) / 2.0 for s in ordered]
        span = (max(xs) - min(xs)) or 1.0
        horiz = "rtl" if xs[-1] < xs[0] else "ltr"
        same_col_y = [ys[i] for i in range(1, len(ys)) if abs(xs[i] - xs[i - 1]) < span * 0.35]
        vert = "btt" if len(same_col_y) >= 2 and same_col_y[-1] < same_col_y[0] else "ttb"
        return f"{horiz}-{vert}", "code-sequence"
    meta = normalize_reading_order(book_order)
    if meta:
        return meta, "book-meta"
    return (normalize_reading_order(fallback_order) or DEFAULT_READING_ORDER), "fallback"


# ── 纠错（只认权威词表与多数票）──────────────────────────────────────────────
def _apply_corrections(seals, authoritative=None, min_votes: int = MIN_VOTES) -> None:
    """就地打分/纠错：**唯一改字路径**是 `authoritative` 的 `{原始: 核定}` 映射；多数票只标验证。

    `authoritative` 可为 list/set（已核定释文）或 dict（原始 ⇒ 核定映射）。为空 ⇒ **一字不动**。
    """
    vocab: set[str] = set()
    mapping: dict[str, str] = {}
    if isinstance(authoritative, dict):
        for k, v in authoritative.items():
            mapping[str(k)] = str(v)
            vocab.add(str(v))
    elif authoritative:
        for v in authoritative:
            vocab.add(str(v))

    texts = [s.get("inscription") for s in seals if s.get("inscription")]
    votes = {t for t, c in _counter(texts).items() if c >= max(1, int(min_votes))}

    for s in seals:
        t = s.get("inscription")
        if t and t in mapping and mapping[t] != t:
            s["inscription_raw"] = t
            s["inscription"] = mapping[t]
            s["inscription_corrected_by"] = "authoritative"
            t = mapping[t]
        s["inscription_verified"] = bool(t) and (t in vocab or t in votes)
        low = float(s.get("inscription_score") or 1.0) < LOW_SCORE
        s["needs_review"] = bool(t) and (not s["inscription_verified"]) and low


def _counter(items):
    try:
        from collections import Counter
        return Counter(items)
    except Exception:                                    # pragma: no cover
        out: dict = {}
        for x in items:
            out[x] = out.get(x, 0) + 1
        return out


# ── 主流程 ───────────────────────────────────────────────────────────────────
def extract_fields(bgr, boxes=None, *, ocr_fn=None, reading_order: str = "auto",
                   authoritative=None, min_votes: int = MIN_VOTES,
                   book_reading_order=None, fallback_order=None,
                   strict_status: bool = True, category_words=None) -> dict:
    """印格字段提取主流程（**永不抛**；返回结构见模块 docstring §返回）。

    * `strict_status=True`（默认）⇒ 状态字按**位置窗口 + 全局一对一贪心**归属，抢不到留空；
      `False` ⇒ 回落旧口径「取最近的汉字单字」（可重复/可串格），**仅供对比**；
    * `book_reading_order` ⇒ 书级元数据（`book.reading_order`）；无编号可推断时用它，
      `order_source='book-meta'`；
    * `fallback_order` ⇒ 两者都无时的兜底（缺省 `DEFAULT_READING_ORDER`；切图台传
      `FALLBACK_READING_ORDER`＝`rtl-ttb`）；
    * `category_words` ⇒ 本书特有的类目标题词（`is_noise_text` 白名单追加）。
    """
    t0 = time.time()
    try:
        if bgr is None or getattr(bgr, "size", 0) == 0:
            return {"ok": False, "reason": "NO_IMAGE", "msg": "没有页图（先渲页 / 检测）"}
        has_ocr = ocr_capable(ocr_fn)
        H, W = int(bgr.shape[0]), int(bgr.shape[1])
        raw_boxes = list(boxes) if boxes else None
        seal_boxes = [_as_box(b) for b in raw_boxes] if raw_boxes else detect_seals(bgr)
        fallback_ord = normalize_reading_order(fallback_order) or DEFAULT_READING_ORDER
        if not seal_boxes:
            return {"ok": True, "size": [W, H], "reading_order": fallback_ord,
                    "order_source": "fallback", "seals": [], "count": 0,
                    "dropped": {"inside_seal": 0, "edge": 0, "far": 0, "noise": 0,
                                "noise_text": 0},
                    "dropped_texts": {"inside_seal": [], "edge": [], "far": [], "noise": [],
                                      "noise_text": []},
                    "far_limit": 0.0, "ocr_available": has_ocr,
                    "order_audit": {"status": "no-code", "coded": 0, "seals": 0, "violations": []},
                    "elapsed_s": round(time.time() - t0, 2),
                    "note": "未检测到印章"}

        # **降级闸**：本包不带 OCR（斐萃_lite）⇒ 只做红印检测，字段留空字符串交人工填，
        # 绝不 import 适配层（否则 `ModuleNotFoundError` 会把「检测成功」变成「点了就炸」）。
        items = _ocr_items(bgr, ocr_fn) if has_ocr else []
        blank = None if has_ocr else ""        # 无 OCR 时三字段是**空串**（不是 None，UI 直接可编辑）

        # ① 四轮过滤
        avg_side = sum(min(b[2] - b[0], b[3] - b[1]) for b in seal_boxes) / max(len(seal_boxes), 1)
        far_limit = max(avg_side * FAR_FACTOR, min(W, H) * 0.10)
        inside: list[dict] = []
        edge: list[dict] = []
        far: list[dict] = []
        noise: list[dict] = []
        noise_text: list[dict] = []
        kept: list[dict] = []
        for it in items:
            if any(center_in(it["box"], sb) for sb in seal_boxes):
                inside.append(it)
                continue
            if is_edge_text(it["box"], W, H):
                edge.append(it)
                continue
            nearest = min(bbox_gap(it["box"], sb) for sb in seal_boxes)
            if nearest > far_limit:
                far.append(it)
                continue
            kind = classify_text(it["text"])
            if kind == "noise":
                noise.append(it)
                continue
            # 释文污染：页码（`〇七二`）/ 类目标题（`單姓單名字印`）——**归属前剔**，不进释文候选。
            # 编号（`0424`）与纯汉字单字不在此列：前者是正字段，后者只可能当状态字。
            if kind != "code" and is_noise_text(it["text"], extra_words=category_words):
                it = dict(it, kind="noise_text")
                noise_text.append(it)
                continue
            kept.append(it)

        # ② 就近归属
        buckets: dict[int, list[dict]] = {i: [] for i in range(len(seal_boxes))}
        for it in kept:
            dists = sorted((bbox_gap(it["box"], sb), i) for i, sb in enumerate(seal_boxes))
            buckets[dists[0][1]].append(it)

        # ②b 状态字：**位置窗口 + 全局一对一**（抢不到 ⇒ 留空）。旧口径留 `status_legacy` 供对比。
        status_alloc = allocate_status(seal_boxes, kept, strict=bool(strict_status))
        # 被剔的释文污染落到哪枚印上（用于「剔除后无释文 ⇒ needs_review」）
        noise_by_seal: dict[int, int] = {i: 0 for i in range(len(seal_boxes))}
        for it in noise_text:
            d = sorted((bbox_gap(it["box"], sb), i) for i, sb in enumerate(seal_boxes))
            noise_by_seal[d[0][1]] += 1

        # ③ 分类 + 择一
        seals: list[dict] = []
        for i, sb in enumerate(seal_boxes):
            got = sorted(buckets[i], key=lambda it: bbox_gap(it["box"], sb))   # 越近越可信
            kinds: dict[str, list[dict]] = {"inscription": [], "status": [], "code": [], "noise": []}
            for it in got:
                kinds[classify_text(it["text"])].append(it)
            seal = {
                "idx": i + 1, "box": [int(v) for v in sb],
                "inscription": blank, "inscription_score": None,
                "status": blank, "status_score": None,
                "code": blank, "code_score": None,
                "candidates": {k: [it["text"] for it in v] for k, v in kinds.items() if v},
                "text_boxes": [{"text": it["text"], "score": round(it["score"], 4),
                                "kind": classify_text(it["text"]),
                                "box": [int(round(float(v))) for v in it["box"]]} for it in got],
            }
            if kinds["inscription"]:
                best = max(kinds["inscription"], key=lambda it: (len(it["text"]), it["score"]))
                seal["inscription"] = best["text"]
                seal["inscription_score"] = round(best["score"], 4)
                extra = [it["text"] for it in kinds["inscription"] if it is not best]
                if extra:
                    seal["inscription_extra"] = extra
            legacy = kinds["status"][0] if kinds["status"] else None
            seal["status_legacy"] = legacy["text"] if legacy else blank   # 旧口径（取最近单字）
            assigned = status_alloc[i]
            if not strict_status:                     # 回落旧行为：最近单字（可重复、可串格）
                seal["status"] = legacy["text"] if legacy else blank
                seal["status_score"] = round(legacy["score"], 4) if legacy else None
            elif assigned is not None:                # 窗口内、且在这轮贪心里没被更强的印章抢走
                seal["status"] = assigned["text"]
                seal["status_score"] = round(assigned["score"], 4)
            else:                                     # 抢不到 ⇒ 留空（不猜、不拿隔壁的）
                seal["status"] = blank
                seal["status_score"] = None
            if noise_by_seal.get(i):
                seal["inscription_dropped_noise"] = int(noise_by_seal[i])
            if kinds["code"]:
                seal["code"] = normalize_code(kinds["code"][0]["text"])
                seal["code_score"] = round(kinds["code"][0]["score"], 4)
            seals.append(seal)

        # ④ 纠错（只认权威词表 + 多数票；不改字是默认）
        _apply_corrections(seals, authoritative=authoritative, min_votes=min_votes)
        for s in seals:                             # 释文被**污染剔除**后留空 ⇒ 交人工确认
            if s.get("inscription_dropped_noise") and not s.get("inscription"):
                s["needs_review"] = True

        # ⑤ 阅读顺序 + 读数
        explicit = normalize_reading_order(reading_order) if str(reading_order or "auto").lower() != "auto" else None
        if explicit:
            order, source = explicit, "manual"
        else:
            order, source = infer_reading_order(seals, book_order=book_reading_order,
                                                fallback_order=fallback_ord)
        boxes_in = [s["box"] for s in seals]
        pos = grid_positions(boxes_in, reading_order=order)
        if source == "code-sequence":
            seq = sorted(range(len(seals)), key=lambda i: str(seals[i]["code"]))
        else:
            seq = reading_sequence(boxes_in, order)
        for rank, i in enumerate(seq, start=1):
            seals[i]["read_order"] = rank
            seals[i]["c"], seals[i]["r"] = int(pos[i][0]), int(pos[i][1])

        order_audit = audit_order(seals)            # 编号升序 vs (C,R) 字典序（只审计，不阻断裁切）

        out = {"ok": True, "size": [W, H],
               "reading_order": order, "order_source": source,
               "seals": seals, "count": len(seals),
               "ocr_available": has_ocr,
               "order_audit": order_audit,
               "strict_status": bool(strict_status),
               "dropped": {"inside_seal": len(inside), "edge": len(edge),
                           "far": len(far), "noise": len(noise),
                           "noise_text": len(noise_text)},
               "dropped_texts": {"inside_seal": [it["text"] for it in inside],
                                 "edge": [it["text"] for it in edge],
                                 "far": [it["text"] for it in far],
                                 "noise": [it["text"] for it in noise],
                                 "noise_text": [it["text"] for it in noise_text]},
               "far_limit": round(far_limit, 1),
               "ocr_items": len(items), "elapsed_s": round(time.time() - t0, 2)}
        if not has_ocr:
            out["note"] = OCR_UNAVAILABLE_NOTE
        return out
    except Exception as exc:                              # noqa: BLE001 —— 本地版永不抛
        return {"ok": False, "reason": "ERROR",
                "msg": f"字段提取失败：{exc.__class__.__name__}: {exc}",
                "elapsed_s": round(time.time() - t0, 2)}
