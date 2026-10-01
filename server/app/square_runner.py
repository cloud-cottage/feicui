#!/usr/bin/env python
"""`POST /api/tools/square-crop` 的 **worker 侧执行体**（子进程，stdin → stdout）——Kong。

**必须**由 `feicui/venv/bin/python` 运行（OCR / 图像栈在该 venv 内；接口层 `server/.venv` **无** cv2/numpy，
见规范 §6.5 解释器矩阵）。**cwd 必须是 `feicui/` 根**（`processor.py` 的相对路径口径）。

它**只做纯计算**，与 jobs 体系**完全无关**（红线：不写 DB、不读 `stamps`、不建 job、不碰 `exports/` `output/`）：
  1. 从 stdin 读一行 JSON 请求（`image_b64` ＋ 参数）；
  2. **复用**斐萃现状口径：`processor.detect_stamp_regions`（HSV 红掩膜 → CLOSE → findContours → 面积门限
     → 长宽比筛选 → `_pad_bbox` 外扩）；本脚本**不复制任何检测算法**；
  3. **新增**的只有「方形化」这一步 —— `app.square.square_bbox`（纯几何；API 侧与 worker 侧同一份实现）；
  4. **复用** `worker.feicui_worker.encode_webp`（q95 逐字同口径）编码 WebP；`quality` 非 95 时走
     `_encode_webp_q`（同 imencode 口径、仅把 95 换成请求值；因 `server/worker/**` 不在本单可改范围，
     `encode_webp` 的默认行为一字未动）。

通信协议（**一行一个 JSON，带标记前缀**）：stdout 只输出一行 `FEICUI_SQUARE=<json>`；诊断一律走 stderr
（stdout 可能混入第三方库的提示行，故调用侧按**标记行**解析，不直接 `json.loads` 整个 stdout）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

MARKER = "FEICUI_SQUARE="

HERE = Path(__file__).resolve()                      # <feicui>/server/app/square_runner.py
SERVER_DIR = HERE.parents[1]                         # <feicui>/server
ROOT = Path(os.environ.get("FEICUI_ROOT") or SERVER_DIR.parent).resolve()
for _p in (str(ROOT), str(SERVER_DIR)):              # processor 在 ROOT；app.* / worker.* 在 SERVER_DIR
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.chdir(ROOT)                                       # processor 相对路径口径（config/、output/）

import cv2  # noqa: E402
import numpy as np  # noqa: E402

# ---- 冷启动优化（本单新增）：在 `import processor` **之前**把 `paddleocr` 换成惰性替身 ----
# `processor.py` 顶部 `from paddleocr import PaddleOCR` 会拉整套推理栈（实测 ≈1.28s），而本脚本
# 只走 `detect_stamp_regions`（纯 cv2/numpy）、**一次 OCR 都不做**。替身只改「模块名→类」的解析，
# 不参与任何计算 ⇒ 检测口径与输出字节零影响；真调 OCR 时替身会透明加载真包（见 app/ocr_lazy.py）。
# 逃生开关：`FEICUI_SQUARE_NO_LAZY_OCR=1`（不装替身，用于 A/B 与回滚）。
from app.ocr_lazy import install_lazy_paddleocr  # noqa: E402

LAZY_OCR_INSTALLED = install_lazy_paddleocr()

import processor  # noqa: E402  —— 同一份检测实现（§1.2 I-1）
from app.square import (  # noqa: E402  —— 同一份方形化实现 + 来源标签生成处
    min_area_source_label,
    scale_for_max_side,
    square_bbox,
)
from worker.feicui_worker import encode_webp  # noqa: E402  —— 同一份 WebP 编码（q95）


def log(msg: str) -> None:
    print(f"[square_runner {os.getpid()}] {msg}", file=sys.stderr, flush=True)


def _encode_webp_q(crop, quality: int) -> bytes:
    """WebP 编码：`quality==95` ⇒ **逐字复用** `feicui_worker.encode_webp`（本单默认路径）。

    请求显式给了别的 `quality` 时，用**同一个 imencode 口径**换参数（`encode_webp` 把 95 写死、
    且 `server/worker/**` 不在本单可改范围内 ⇒ 不改它、只在此处给出等价通路）。
    """
    q = int(quality)
    if q == 95:
        return encode_webp(crop)
    ok, buf = cv2.imencode(".webp", crop, [int(cv2.IMWRITE_WEBP_QUALITY), q])
    if not ok:
        raise RuntimeError("webp 编码失败")
    return bytes(buf.tobytes())


def decode_image(image_bytes: bytes):
    """解码上传字节。返回 BGR 三通道 ndarray；解不出来 ⇒ `ValueError('DECODE_FAILED')`。"""
    if not image_bytes:
        raise ValueError("DECODE_FAILED")
    buf = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("DECODE_FAILED")
    if img.ndim == 2:                                     # 灰度
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:                               # 带 alpha
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    elif img.shape[2] != 3:
        raise ValueError("DECODE_FAILED")
    return np.ascontiguousarray(img)


def process(req: dict) -> dict:
    """纯函数主体：字节 → 候选（方形化 + WebP + sha256）。"""
    raw = base64.b64decode(req["image_b64"])
    img = decode_image(raw)
    H, W = img.shape[:2]

    pad_ratio = float(req.get("pad_ratio", 0.15))
    explicit_min_area = req.get("min_area_eff")
    if explicit_min_area is None:                          # 现口径换算（与 process_page 逐字相同）
        min_area_eff = float(req["template_min_area"]) * float(processor.AREA_SCALE)
        # 来源标签**由 `template_source` 派生**（同口径，不可能互相矛盾）；**绝不**写死
        # `templates.json:default` —— 该键在 `config/templates.json` 里并不存在（本单修正）。
        min_area_source = min_area_source_label(
            str(req.get("template_source") or "UNKNOWN_SOURCE"),
            req["template_min_area"],
            processor.AREA_SCALE,
        )
    else:
        min_area_eff = float(explicit_min_area)
        min_area_source = "explicit(min_area_eff)"

    quality = int(req.get("quality", 95))
    max_side = int(req.get("max_side", 0))

    # ---- ①～② 现状口径：红掩膜检测 + pad_ratio 外扩（**复用**，不另写）----
    cands = processor.detect_stamp_regions(
        img, req["hsv_low"], req["hsv_high"], min_area_eff, pad_ratio
    )

    out = []
    for c in cands:
        bbox = [int(v) for v in c["bbox"]]
        sq = square_bbox(bbox, W, H)                       # ---- ③～⑤ 本单新增：方形化 ----
        sx1, sy1, sx2, sy2 = sq["square"]
        crop = np.ascontiguousarray(img[sy1:sy2, sx1:sx2])
        out_side = scale_for_max_side(sq["side"], max_side)
        if out_side != sq["side"]:                         # max_side>0 ⇒ 只缩不放，缩放后仍是正方形
            crop = cv2.resize(crop, (out_side, out_side), interpolation=cv2.INTER_AREA)
        data = _encode_webp_q(crop, quality)
        out.append(
            {
                "idx": -1,  # 排序后回填（见下）
                "bbox": bbox,
                "square": [sx1, sy1, sx2, sy2],
                "side": int(sq["side"]),
                "width": int(crop.shape[1]),
                "height": int(crop.shape[0]),
                "mime": "image/webp",
                "sha256": hashlib.sha256(data).hexdigest(),
                "image_base64": base64.b64encode(data).decode("ascii"),
                "area": float(c["area"]),
                "aspect": float(c["aspect"]),
                "degraded": bool(sq["degraded"]),
                "degraded_reasons": list(sq["degraded_reasons"]),
            }
        )

    # 排序：**面积降序**（冻结契约；`idx` = 排序后的位次，0 起 ⇒ 前端默认取第一个 = idx 0）
    out.sort(key=lambda c: (-c["area"], c["bbox"][0], c["bbox"][1]))
    for i, c in enumerate(out):
        c["idx"] = i

    return {
        "ok": True,
        "count": len(out),
        "source": {"width": int(W), "height": int(H)},
        "candidates": out,
        "degraded": any(c["degraded"] for c in out),
        "params_used": {
            "hsv_low": list(req["hsv_low"]),
            "hsv_high": list(req["hsv_high"]),
            "min_area_eff": min_area_eff,
            "min_area_source": min_area_source,
            "pad_ratio": pad_ratio,
            "quality": quality,
            "max_side": max_side,
            "template_source": req.get("template_source"),
        },
    }


def main() -> int:
    payload: dict = {}
    try:
        req = json.loads(sys.stdin.read() or "{}")
        payload = process(req)
    except ValueError as exc:
        payload = {"ok": False, "error": str(exc) or "DECODE_FAILED"}
    except KeyError as exc:
        payload = {"ok": False, "error": "BAD_REQUEST", "detail": f"缺字段：{exc}"}
    except Exception as exc:  # noqa: BLE001 - 任何异常都必须是可解析的 JSON，不得让调用侧看到半截 stdout
        log(f"未预期异常：{exc!r}")
        payload = {"ok": False, "error": "RUNNER_ERROR", "detail": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(MARKER + json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
