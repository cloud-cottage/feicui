"""方形化几何 + 参数真源（**纯函数**；无 cv2 / numpy / DB 依赖）——Kong / `POST /api/tools/square-crop`。

为什么单独一个模块：本单的「**方形化**」是斐萃既有口径（红掩膜 → 外扩 bbox）**之上新增的一步**，
且它是**纯算术**——因此它可以同时被两侧 import：
  * API 侧（`server/.venv`，**无图像栈**，§6.5 解释器矩阵）用于读参数 / 组 `params_used`；
  * worker 侧（`feicui/venv/bin/python`，有 cv2/numpy）由 `app/square_runner.py` import 后做真正的方形化。

本模块只做三件事：
  1. `templates_path()` / `load_template_params()`：读参数真源 —— 优先 `config/templates.json` 的 `default` 项
     （**该键当前不存在**，见下），读不到则用**内建兜底常量**，并把**实际用了哪个来源**如实回给调用侧；
  2. `resolve_params()`：把「请求入参 + 模板默认」合成**实际生效参数**（回给客户端的 `params_used`）；
  3. `square_bbox()`：把 `processor.detect_stamp_regions` 给出的**外扩后 bbox** 方形化（冻结规则 ①～⑤）。

### 参数真源与来源标签（**如实标注**，见 `load_template_params`）

`config/templates.json` 实测**只有三本书名键**（`黄牧甫印谱…` / `秦汉印典…` / `古玺汇编…`），
**没有 `default` 键**。因此：

* 有 `default` 项 ⇒ `source="templates.json:default"`（真源）；
* 没有 `default` 项 ⇒ `source` 写成 `builtin(corpus-identical·verified 3/3·square.py:BUILTIN_TEMPLATE_PARAMS)`
  形态 —— 明确告知「用的是**内建兜底常量**、它住在 `square.py:BUILTIN_TEMPLATE_PARAMS`、并且刚**核验过**
  与模板里现有 N 本书的 `(hsv_low, hsv_high, min_area)` **逐字一致**」。**绝不写成 `templates.json:default`**
  （引用不存在的键＝来源失真，本单修掉）。
* 若三本书之间**不一致** ⇒ 标签写成 `builtin(corpus-DIVERGENT·…)`（如实说明「语料自身不统一 ⇒ 用内建常量」）。

`min_area_eff` 的换算（模板 `min_area × processor.AREA_SCALE`）**始终**发生在 worker 侧，
其来源标签由 `min_area_source_label()` 统一生成 ⇒ 与 `template_source` **同口径、不可能互相矛盾**。

方形化规则（Zang 冻结契约，逐字实现；本模块即其唯一实现处）：
  ① 先按现有逻辑得到**外扩后的 bbox**（`detect_stamp_regions` 已含 `pad_ratio` 外扩，本模块不重算）；
  ② **边长 side = max(外扩后 w, 外扩后 h)**；
  ③ **以 bbox 中心为中心取 side×side 的正方形**；
  ④ 若超出图像边界，**整体平移回边界内（仍保持正方形）**；
  ⑤ 若图像短边 < side，则 side 降为短边（仍为正方形）并在响应里**如实标注已降级**。
"""
from __future__ import annotations

import json
from pathlib import Path

# 模板文件相对工程根的位置（与 `processor.load_templates()` 的相对路径 `config/templates.json` 同源）
TEMPLATES_REL = ("config", "templates.json")

# 模板里的默认项名（**当前 `config/templates.json` 里没有这个键**；有 ⇒ 它就是参数真源）
DEFAULT_TEMPLATE_KEY = "default"

# `config/templates.json` 当前**没有** `default` 项（实测核验：键为三本书名）⇒ 这里给出与三本书现行模板
# **逐字一致**的内建兜底（hsv_low/hsv_high/min_area 三本书相同；pad_ratio 取规范默认 0.15）。
# 这是**兜底**不是真源：一旦模板里出现 `default` 项，`load_template_params()` 立刻改用它（见其返回的 source）。
# 来源标签一律由 `_builtin_source()` 生成 ⇒ **不会**把这常量说成是 `templates.json:default`。
BUILTIN_TEMPLATE_PARAMS: dict = {
    "hsv_low": [0, 120, 70],
    "hsv_high": [10, 255, 255],
    "min_area": 800,
    "pad_ratio": 0.15,
}

# 内建兜底常量在源码里的**确切位置**（写进来源标签，方便人工按图索骥核对该常量）
BUILTIN_PARAMS_LOCUS = "square.py:BUILTIN_TEMPLATE_PARAMS"

# 与 `processor.AREA_SCALE` 同源：RENDER_DPI=400 / BASE_DPI=144 ⇒ (400/144)^2。
# 这里**只作文档性复算**（worker 侧一律直接取 `processor.AREA_SCALE`，见 `square_runner.py`）。
AREA_SCALE_EXPECTED = (400.0 / 144.0) ** 2

# 入参边界（越界 ⇒ 400，见 routers/tools.py）
PAD_RATIO_MIN, PAD_RATIO_MAX = 0.0, 1.0
QUALITY_MIN, QUALITY_MAX = 1, 100
PAD_RATIO_DEFAULT = 0.15
QUALITY_DEFAULT = 95
MAX_SIDE_DEFAULT = 0  # 0 = 不缩放


def templates_path(root: Path) -> Path:
    """`<feicui 根>/config/templates.json`（参数真源文件）。"""
    p = Path(root)
    for seg in TEMPLATES_REL:
        p = p / seg
    return p


def _template_items(data) -> list[dict]:
    """`templates.json` 里形如「书模板」的项（含 `hsv_low/hsv_high/min_area` 的 dict）。"""
    if not isinstance(data, dict):
        return []
    return [
        v
        for v in data.values()
        if isinstance(v, dict) and "hsv_low" in v and "hsv_high" in v and "min_area" in v
    ]


def _corpus_matches_builtin(items: list[dict]) -> bool:
    """各书模板的 `(hsv_low, hsv_high, min_area)` 是否都与**内建常量**逐字一致。**只用于标签**。"""
    if not items:
        return False
    for it in items:
        if list(it["hsv_low"]) != list(BUILTIN_TEMPLATE_PARAMS["hsv_low"]):
            return False
        if list(it["hsv_high"]) != list(BUILTIN_TEMPLATE_PARAMS["hsv_high"]):
            return False
        if float(it["min_area"]) != float(BUILTIN_TEMPLATE_PARAMS["min_area"]):
            return False
    return True


def _builtin_source(n_books: int, agree: bool) -> str:
    """内建兜底的来源标签（**如实**：指明常量位置 + 与语料的核对结果）。"""
    if n_books and agree:
        return f"builtin(corpus-identical·verified {n_books}/{n_books}·{BUILTIN_PARAMS_LOCUS})"
    if n_books:
        return f"builtin(corpus-DIVERGENT·{n_books}书模板不一致·{BUILTIN_PARAMS_LOCUS})"
    return f"builtin(no-corpus-template·{BUILTIN_PARAMS_LOCUS})"


def load_template_params(root: Path) -> tuple[dict, str]:
    """读模板参数真源，返回 `(params, source)`。

    * `source="templates.json:default"` —— 模板里**确有** `default` 项（**真源**）；
    * `source="builtin(corpus-identical·verified N/N·square.py:BUILTIN_TEMPLATE_PARAMS)"`
      —— 模板里**没有** `default` 项时用内建兜底常量（当前实况），并已**核验**该常量与模板里
      现有 N 本书的 `(hsv_low, hsv_high, min_area)` 逐字一致；
    * `source="builtin(corpus-DIVERGENT·…)` —— 没有 `default` 项、且各书之间**不一致**（如实标注）；
    * `source="builtin(no-corpus-template·…)"` —— 模板里没有任何可识别的书模板项；
    * `source="builtin(no-template-file·…)"` / `"builtin(template-unreadable·…)"` —— 模板文件缺失/读不出。

    **绝不引用不存在的键**（历史缺陷：曾把内建常量写成 `templates.json:default`，已于本单修正）。
    任何异常都不抛（端点侧只需可读错误 + 可解释的 `params_used`），但**绝不猜**：
    走了兜底就一定把 `source` 如实回给客户端。
    """
    path = templates_path(root)
    if not path.is_file():
        return dict(BUILTIN_TEMPLATE_PARAMS), f"builtin(no-template-file·{BUILTIN_PARAMS_LOCUS})"
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return dict(BUILTIN_TEMPLATE_PARAMS), f"builtin(template-unreadable·{BUILTIN_PARAMS_LOCUS})"
    item = data.get(DEFAULT_TEMPLATE_KEY) if isinstance(data, dict) else None
    if isinstance(item, dict) and "hsv_low" in item and "hsv_high" in item and "min_area" in item:
        merged = dict(BUILTIN_TEMPLATE_PARAMS)
        merged.update({k: item[k] for k in ("hsv_low", "hsv_high", "min_area")})
        merged["pad_ratio"] = item.get("pad_ratio", PAD_RATIO_DEFAULT)
        return merged, "templates.json:default"
    items = _template_items(data)
    return dict(BUILTIN_TEMPLATE_PARAMS), _builtin_source(len(items), _corpus_matches_builtin(items))


def min_area_source_label(template_source: str, template_min_area: float, area_scale: float) -> str:
    """`params_used.min_area_source` 的**唯一**生成处：由 `template_source` 派生 ⇒ 两者同口径。

    形如 `builtin(corpus-identical·verified 3/3·square.py:BUILTIN_TEMPLATE_PARAMS)·
    min_area=800.0×processor.AREA_SCALE=7.716049`。公式部分描述的是**现口径**（与
    `processor.process_page` 第 ~298 行逐字相同：模板 `min_area × AREA_SCALE`），
    真值由 worker 侧的 `processor.AREA_SCALE` 传入，**不做 API 侧复算**。
    """
    return (
        f"{template_source}·min_area={float(template_min_area)}"
        f"×processor.AREA_SCALE={float(area_scale):.6f}"
    )


def resolve_params(
    root: Path,
    *,
    pad_ratio: float | None = None,
    min_area_eff: float | None = None,
) -> dict:
    """合成**请求口径参数**（模板默认 + 请求显式值）。

    `min_area_eff` 的口径（**本单明写的解释**，登记为规范缺口）：
      * **显式传入** ⇒ 原样作为**有效像素面积阈值**直接交给 `detect_stamp_regions`（调用方自负责 DPI 口径）；
      * **不传**（此处为 `None`）⇒ worker 侧用模板默认项换算：`template.min_area * processor.AREA_SCALE`
        （`AREA_SCALE` ＝ (400/144)²，与 `process_page` / `feicui_worker.process_page` 的现口径逐字相同）。
        换算**在 worker 侧发生**（那里才 import 得到 `processor.AREA_SCALE`），并把实际用到的值回传，
        于是 `params_used.min_area_eff` 是**真实生效值**而非 API 侧的复算值。

    返回的字典随后交给 `square_runner`；`template_source` 如实标注参数真源（见 `load_template_params`）。
    """
    params, source = load_template_params(root)
    return {
        "hsv_low": list(params["hsv_low"]),
        "hsv_high": list(params["hsv_high"]),
        "template_min_area": float(params["min_area"]),
        "min_area_eff": None if min_area_eff is None else float(min_area_eff),
        "pad_ratio": float(PAD_RATIO_DEFAULT if pad_ratio is None else pad_ratio),
        "template_source": source,
        "template_pad_ratio_default": float(params.get("pad_ratio", PAD_RATIO_DEFAULT)),
    }


def square_bbox(bbox, width: int, height: int) -> dict:
    """把外扩后的 bbox 方形化（冻结规则 ①～⑤）。**纯整数算术，无 cv2/numpy。**

    入参 `bbox=(x1,y1,x2,y2)`（半开区间，与 `processor._pad_bbox` 的返回同形）、图像尺寸 `width/height`。
    返回 `{"square": (x1,y1,x2,y2), "side": int, "degraded": bool, "degraded_reasons": [str]}`。

    * `square` **恒为正方形**：`x2-x1 == y2-y1 == side`，且恒落在 `[0,width]×[0,height]` 内；
    * `degraded` ＝ 发生过下列任一回退（`degraded_reasons` 逐条给出是哪一个）：
        - `SHORT_SIDE_CLAMP`：规则 ⑤（图像短边 < side ⇒ side 降为短边）；
        - `BOUNDARY_SHIFT`：规则 ④（越界 ⇒ 整体平移回边界内）。
      **注**：契约里 ④ 只要求「平移」、⑤ 才明说「标注已降级」。本实现把 ④ 也计入 `degraded`（**如实标注**，
      并由 `degraded_reasons` 区分二者），避免「平移过却报 degraded=false」这种失真（登记为规范缺口）。
    """
    W, H = int(width), int(height)
    if W <= 0 or H <= 0:
        raise ValueError(f"图像尺寸非法：width={W} height={H}")
    x1, y1, x2, y2 = (int(round(float(v))) for v in bbox)
    # 先夹到图像内（外扩已由 detect_stamp_regions 做过，这里是防御性夹取，不改口径）
    x1 = max(0, min(W, x1))
    y1 = max(0, min(H, y1))
    x2 = max(x1, min(W, x2))
    y2 = max(y1, min(H, y2))

    reasons: list[str] = []
    w, h = x2 - x1, y2 - y1
    side = max(w, h)                      # 规则 ②
    if side <= 0:
        raise ValueError(f"bbox 退化（面积 0）：{bbox}")

    short = min(W, H)
    if short < side:                      # 规则 ⑤
        side = short
        reasons.append("SHORT_SIDE_CLAMP")

    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2   # 规则 ③：以 bbox 中心为中心
    sx1, sy1 = cx - side // 2, cy - side // 2
    sx2, sy2 = sx1 + side, sy1 + side

    # 规则 ④：越界 ⇒ 整体平移回边界内（仍保持正方形；side ≤ 短边 ⇒ 一定能放下）
    if sx1 < 0:
        sx1, sx2 = 0, side
        reasons.append("BOUNDARY_SHIFT")
    elif sx2 > W:
        sx1, sx2 = W - side, W
        reasons.append("BOUNDARY_SHIFT")
    if sy1 < 0:
        sy1, sy2 = 0, side
        reasons.append("BOUNDARY_SHIFT")
    elif sy2 > H:
        sy1, sy2 = H - side, H
        reasons.append("BOUNDARY_SHIFT")

    if sx2 - sx1 != side or sy2 - sy1 != side:  # 自证：绝不返回非正方形
        raise AssertionError(f"方形化失败：square={(sx1, sy1, sx2, sy2)} side={side}")

    return {
        "square": (int(sx1), int(sy1), int(sx2), int(sy2)),
        "side": int(side),
        "degraded": bool(reasons),
        "degraded_reasons": reasons,
    }


def scale_for_max_side(side: int, max_side: int) -> int:
    """`max_side` 生效后的输出边长（**只缩不放**；`max_side<=0` 或 `side<=max_side` ⇒ 原值）。"""
    if max_side is None or int(max_side) <= 0:
        return int(side)
    return int(min(int(side), int(max_side)))
