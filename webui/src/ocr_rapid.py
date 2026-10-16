# webui/src/ocr_rapid.py
"""「斐萃」本地版 · RapidOCR（onnxruntime）适配层 —— **纯逻辑，无 GUI 依赖**。

分层纪律（与 `webui/api.py` / `webui/selftest.py` 同规）：
  本文件 **不 import streamlit、不 import webview、不 import api/app**，
  只依赖 `rapidocr`（＋其 onnxruntime 引擎）与 `numpy/cv2`，可被脚本直接 import 做单测。

为什么要适配层（而不是到处裸调 rapidocr）：
  本仓既有 OCR 调用面是 **Paddle** 形态 —— `processor.py::ocr_text()` /
  `labeling/scripts/run_abc.py` 都是
      `out = ocr.predict(img)` → 从 `item.json["res"]["rec_texts"]`（pipeline，list）
      或 `["rec_text"]`（`TextRecognition`，单值）取值。
   **那个 `rec_texts` vs `rec_text` 的键差是本仓踩过的坑**（`labeling/README.md` §5：
   rec-only 用错键 ⇒ 248/248 全空，修正后才是 128/248）⇒ 迁移到别的引擎时
   **取值面必须现取实测**，不得凭记忆套键名。

  RapidOCR 3.x **没有** `rec_texts/rec_text` 这套字典键：`engine(img)` 直接返回
  `rapidocr.utils.output.RapidOCROutput`，字段是 **`boxes` / `txts` / `scores`**
  （实测：rapidocr 3.10.0 ＋ onnxruntime 1.31.0，见 `ops/ocr-rapid/README.md`
  「取值面实测」）。本适配层把这套字段**规范化成本仓既有形态**：

      engine(img)          -> [(box, text, score), ...]        # 调用面
      ocr_image(src)       -> {"texts": [...], "scores": [...], "boxes": [...]}
      to_rec_texts(res)    -> (拼接文本, [分数])                # 与 rec_texts 同形的回落面

用法：
    from src.ocr_rapid import ocr_image
    r = ocr_image("/path/page.png")        # 或 numpy 图（BGR 或 RGB 均可，见下）
    print(r["texts"], r["scores"], r["boxes"])

命令行自检（不需要 GUI、不需要老工程）：
    venv/bin/python webui/src/ocr_rapid.py --selftest [--image a.png --image b.png]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

__all__ = [
    "OCR_ENGINE_NAME",
    "build_engine",
    "get_engine",
    "engine",
    "ocr_image",
    "to_rec_texts",
    "normalize_output",
    "last_error",
]

OCR_ENGINE_NAME = "rapidocr-onnxruntime"
#: 默认构造参数（3.x 的 params 是「段.键」扁平字典；实测见 `ops/ocr-rapid/README.md`）
#:
#: ⚠ **踩过的坑（实测，勿踩）**：随手传 `Det.limit_side_len` 会让 **det 全空**
#:   —— 该键在 3.x 是 `limit_type="min"` 语义的**放大下界**（默认 736：小图放大到 min 边 736），
#:   传 2000 会把小图放到离谱尺寸再判空（实测 120×460 合成图 `len(out)==0`；
#:   去掉该键立刻恢复 `('FEICUI','123')`）。真要限制边长，用 `Global.max_side_len`（默认已是 2000）。
#:   ⇒ **只钉引擎类型，其余留库默认**；动任何键都要像本单一样实测一遍。
DEFAULT_PARAMS: dict[str, Any] = {}
"""预留的额外默认参数（**当前为空** —— 本单只钉后端，其余一律留库默认，理由见上）。

⚠ 实测两个「传了反而更糟」的键（别抄网上的老写法）：
  ① `Det.limit_side_len` = 2000 ⇒ **det 全空**（该键是 `limit_type="min"` 的放大下界，默认 736；
     要限长边请用 `Global.max_side_len`，默认已是 2000）；
  ② `*.engine_type` 的值**必须是 `rapidocr.EngineType` 枚举** —— 传字符串 `"onnxruntime"`
     直接 `TypeError: The value of Det.engine_type must be Enum Type.`（由 `_default_params()` 现造）。
"""


def _default_params() -> dict[str, Any]:
    """现取 `EngineType.ONNXRUNTIME` 枚举钉后端（字符串会被拒，实测）。"""
    from rapidocr import EngineType

    et = EngineType.ONNXRUNTIME
    return {"Det.engine_type": et, "Cls.engine_type": et, "Rec.engine_type": et}

_ENGINES: dict[str, Any] = {}
_ENGINE_LOCK = threading.Lock()
_LAST_ERROR: str | None = None


def last_error() -> str | None:
    """最近一次构造/推理失败的原文（给 UI 与自检报错用，不抛栈）。"""
    return _LAST_ERROR


#: rec-only 配置（关 det/cls，整图直接喂 rec）—— 在 `engine(..., params=...)` 里现用，
#: 也是 `ops/ocr-rapid/run_rapid.py` 评测 C 口径时用的配置。
REC_ONLY: dict[str, Any] = {"Global.use_det": False, "Global.use_cls": False}
#: 默认管线（det + cls + rec）
PIPELINE: dict[str, Any] = {"Global.use_det": True, "Global.use_cls": True, "Global.use_rec": True}


def build_engine(params: dict[str, Any] | None = None, **overrides: Any):
    """构造 RapidOCR 实例（不缓存）。模型随 wheel 落盘 ⇒ **离线可用、不联网下载**。"""
    from rapidocr import RapidOCR  # 延迟导入：import 本模块本身不付 onnxruntime 启动代价

    p = _default_params()
    p.update(DEFAULT_PARAMS)
    if params:
        p.update(params)
    p.update(overrides)
    t0 = time.perf_counter()
    eng = RapidOCR(params=p)
    setattr(eng, "_feicui_init_s", time.perf_counter() - t0)
    return eng


def get_engine(params: dict[str, Any] | None = None):
    """进程内缓存（按 params 取键）。

    **逐件独立子进程**纪律见 `webui/build/README.md` §2.1：崩的是「反复销毁/重建原生
    推理上下文」，不是「同进程复用实例」⇒ 一个子进程内复用（含同时持有 pipeline 与
    rec-only 两个实例）是安全的，本单 248×2 枚即按此跑通。
    """
    global _LAST_ERROR
    key = json.dumps(params or {}, sort_keys=True, default=str)
    if key not in _ENGINES:
        with _ENGINE_LOCK:
            if key not in _ENGINES:
                try:
                    _ENGINES[key] = build_engine(params)
                    _LAST_ERROR = None
                except Exception as exc:  # noqa: BLE001 —— 上层要「降级」而不是「崩」
                    _LAST_ERROR = f"{type(exc).__name__}: {exc}"
                    raise
    return _ENGINES[key]


def _norm_boxes(boxes: Any) -> list[list[list[int]]]:
    if boxes is None:
        return []
    arr = np.asarray(boxes)
    if arr.size == 0:
        return []
    out: list[list[list[int]]] = []
    for poly in arr.reshape(-1, arr.shape[-2], arr.shape[-1]) if arr.ndim == 3 else arr.reshape(-1, 1, 2):
        pts = np.asarray(poly, dtype=float)[:, :2]
        out.append([[int(round(float(x))), int(round(float(y)))] for x, y in pts])
    return out


def normalize_output(out: Any) -> tuple[list[Any], list[str], list[float]]:
    """把 RapidOCR 的返回**实际取到值**再规范化（取值面实测见模块 docstring）。

    兼容两种真实形态：
      ① `RapidOCROutput`（3.x 默认）：`.boxes`(N,4,2) / `.txts`(tuple[str]) / `.scores`(tuple[float])
      ② `(res, elapse)` 元组（旧 rapidocr_onnxruntime 1.x）：`res = [(box, text, score), ...]`
    取不到的空面（某字段为 None / 空图）一律回落成空列表，**不抛**。
    """
    boxes: list[Any] = []
    texts: list[str] = []
    scores: list[float] = []
    if out is None:
        return boxes, texts, scores
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[0], (list, tuple)):
        out = out[0]
    if isinstance(out, (list, tuple)):
        for it in out:
            if isinstance(it, (list, tuple)) and len(it) >= 2:
                boxes.append(it[0])
                texts.append(str(it[1]))
                scores.append(float(it[2]) if len(it) > 2 and it[2] is not None else 0.0)
        return boxes, texts, scores
    # RapidOCROutput / TextRecOutput：逐一现取；None ⇒ 空
    # ⚠ 实测坑：`Global.use_det=False` 时返回的**根本不是 `RapidOCROutput`，而是
    #   `rapidocr.ch_ppocr_rec.typings.TextRecOutput`**（字段 `imgs/txts/scores`，**没有 `boxes`**）
    #   ⇒ 取值必须按「有 boxes 用 boxes、没有就只取 texts/scores」分支，
    #   不能「按 boxes 长度对齐后截断」（那样会把 rec-only 的文本整批截成空）。
    bx = getattr(out, "boxes", None)
    tx = getattr(out, "txts", None)
    sc = getattr(out, "scores", None)
    texts = [str(t) for t in (tx if tx is not None else [])]
    scores = [float(s) for s in (sc if sc is not None else [])]
    boxes = _norm_boxes(bx)
    if boxes and len(texts) and len(boxes) != len(texts):  # 理论不该发生；对齐时宁可少不可错位
        n = min(len(boxes), len(texts))
        boxes, texts, scores = boxes[:n], texts[:n], scores[:n]
    return boxes, texts, scores


def engine(img: Any, eng: Any = None, params: dict[str, Any] | None = None,
           **kwargs: Any) -> list[tuple[Any, str, float]]:
    """**调用面**：`engine(img) -> [(box, text, score), ...]`。

    `img`：文件路径（str/Path）或 numpy 图。RapidOCR 的 `LoadImage` 同时接受
    BGR / RGB 三通道 ndarray（BGR 会被转 RGB 再推理 —— 本仓 cv2 读到的就是 BGR，
    实测两者在书页图上文本一致，见 `ops/ocr-rapid/README.md`）。

    `params`：「段.键」参数字典（如 `{"Global.use_det": False}`）—— **构造期**参数，
    与 `eng` 二选一（给了 `eng` 就复用，不再构造）。`**kwargs` 才是**调用期**参数
    （RapidOCR `__call__` 实际不接受自定义 kwargs ⇒ 平常不要传）。
    """
    if eng is None:
        eng = get_engine(params)
    global _LAST_ERROR
    try:
        out = eng(img, **kwargs) if kwargs else eng(img)
        _LAST_ERROR = None
    except Exception as exc:  # noqa: BLE001
        _LAST_ERROR = f"{type(exc).__name__}: {exc}"
        raise
    boxes, texts, scores = normalize_output(out)
    # ⚠ 实测坑：rec-only（`Global.use_det=False`）**没有 box**，`zip(boxes, texts, ...)`
    #   会因空 boxes 把文本整条截掉（文本在、框不在）⇒ 这里按「最长者对齐」，
    #   缺的 box 填 `None`（调用方按 `(box, text, score)` 三元组取，`box is None`
    #   ＝「该行无位置信息，只有整图识别结果」）。
    n = max(len(boxes), len(texts), len(scores))
    return [(boxes[i] if i < len(boxes) else None,
             texts[i] if i < len(texts) else "",
             scores[i] if i < len(scores) else 0.0) for i in range(n)]


def to_rec_texts(res: Any) -> tuple[str, list[float]]:
    """**回落面**：把结果压成 Paddle `rec_texts` 同形（拼接文本 ＋ 分数列表）。

    给「既有按 `"".join(rec_texts)` 拼文本的调用方」直接换引擎用：
        txt, scores = to_rec_texts(engine(img))
    """
    triples = res if isinstance(res, list) else engine(res)
    if triples and isinstance(triples[0], tuple):
        return "".join(str(t[1]) for t in triples), [float(t[2]) for t in triples]
    boxes, texts, scores = normalize_output(res)
    return "".join(texts), scores


def ocr_image(path_or_array: Any, eng: Any = None, **kwargs: Any) -> dict[str, Any]:
    """**公开入口**：`ocr_image(path_or_array) -> {texts, scores, boxes, elapse_s, ...}`。

    - 空图 / 无文本：`texts=[]`（**不抛**），`texts_joined=""`。
    - 幂等：同一输入重复调用结果一致（模型固定、无随机性）。
    """
    t0 = time.perf_counter()
    triples = engine(path_or_array, eng=eng, **kwargs)
    elapse = time.perf_counter() - t0
    boxes = [t[0] for t in triples]
    texts = [t[1] for t in triples]
    scores = [t[2] for t in triples]
    return {
        "engine": OCR_ENGINE_NAME,
        "source": str(path_or_array) if isinstance(path_or_array, (str, Path)) else "ndarray",
        "texts": texts,
        "scores": scores,
        "boxes": boxes,
        "texts_joined": "".join(texts),
        "n_lines": len(texts),
        "elapse_s": round(elapse, 4),
    }


def _selftest(images: Sequence[str]) -> int:
    import onnxruntime as ort

    rows = []
    try:
        from rapidocr._version import __version__ as rv  # type: ignore
    except Exception:  # noqa: BLE001
        rv = "unknown"
    print(f"[selftest] rapidocr={rv} onnxruntime={ort.__version__} providers={ort.get_available_providers()}")
    eng = get_engine()
    print(f"[selftest] engine init={getattr(eng, '_feicui_init_s', -1):.2f}s")

    # ① 合成图（黑字白底）—— 不依赖任何外部资产
    import cv2

    synth = np.full((120, 460, 3), 255, np.uint8)
    cv2.putText(synth, "FEICUI 123", (12, 80), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 4)
    r0 = ocr_image(synth, eng=eng)
    rows.append({"case": "synthetic", "texts": r0["texts"], "scores": r0["scores"],
                 "elapse_s": r0["elapse_s"]})
    print(f"[selftest] synthetic -> {r0['texts']!r} {[round(s,3) for s in r0['scores']]} "
          f"in {r0['elapse_s']:.3f}s")

    # ② 真实图（可选）：路径 & ndarray(BGR) 两条入口必须同文本
    for p in images:
        if not Path(p).exists():
            print(f"[selftest] SKIP missing {p}")
            continue
        r1 = ocr_image(str(p), eng=eng)
        img = cv2.imread(str(p))
        r2 = ocr_image(img, eng=eng)
        same = r1["texts"] == r2["texts"]
        rows.append({"case": Path(p).name, "path_texts": r1["texts"], "ndarray_texts": r2["texts"],
                     "same": same, "elapse_s": r1["elapse_s"], "scores": r1["scores"]})
        print(f"[selftest] {Path(p).name} path={r1['texts']!r} ndarray={r2['texts']!r} same={same}")

    # ③ 回归面：rec-only（无 det ⇒ 无 boxes）
    #    实测坑：早期实现「按空 boxes 长度 zip/截断」把文本整条吃掉 ⇒ 此处必须复现出文本，
    #    否则 rec-only 会以「跑通但全空」的假绿通过（本单踩过一次）。
    rec_txt, rec_scores = to_rec_texts(engine(synth, params=REC_ONLY))
    print(f"[selftest] rec_only(synthetic) -> {rec_txt!r} {[round(s, 3) for s in rec_scores]}")
    rows.append({"case": "rec_only_synthetic", "text": rec_txt, "scores": rec_scores})

    ok = bool(rows) and all(("same" not in r) or r["same"] for r in rows)
    # 合成图必须真的认出 "123"：否则「跑通但全空」会被误判成 PASS（本单实测过这个坑）
    ok = ok and any("123" in "".join(r.get("texts", [])) for r in rows)
    ok = ok and bool(rec_txt)
    print(f"[selftest] {'PASS' if ok else 'FAIL'} rows={len(rows)}")
    print(json.dumps(rows, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="RapidOCR 适配层自检（无需 GUI / 无需老工程）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--image", action="append", default=[])
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(_selftest(a.image))
    ap.print_help()
