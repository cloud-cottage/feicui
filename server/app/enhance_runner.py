#!/usr/bin/env python
"""`POST /api/tools/enhance` 的 **worker 侧执行体**（子进程，stdin → stdout）——Kong。

**必须**由 `feicui/venv/bin/python` 运行（numpy / cv2 / Pillow 只在该 venv 内；接口层 `server/.venv`
无 numpy/cv2，见规范 §6.5 解释器矩阵）。**cwd ＝ `feicui/` 根**。

本脚本**只做纯计算**（红线：不写 DB、不读 DB、不建 job、不碰 `exports/` `output/`）：
  1. 从 stdin 读一行 JSON（`image_b64` ＋ `width` ＋ `background`）；
  2. 解码一律走 Pillow 并 `convert("RGB")`（用户样例底色是暖米白 (252,250,237)、alpha 全 255
     ⇒ **不得**假设纯白底，也不得让 alpha 进算法）；
  3. **唯一实现**＝`app.seal_canvas.compose()`（纯函数，本脚本不复制、不改写任何算法常量/步骤）；
  4. 宽度口径（本单关键）：`compose(canvas_long_side=X)` 是**按长边**定画布、A 口径画布 AR 取**原图** AR
     ⇒ 要让**宽恰为 width**，先算 `long_side = round(width · max(1, src_h/src_w))` 再调 compose；
     竖图（src_w < src_h）时 width 是**短边**，必须走这条换算，否则会得到「宽＝短边、高＝width」；
  5. 落盘（编码）前用 **PIL 实测**成品宽度：取整差 1 px 时用 LANCZOS 归一到
     `(width, round(width·src_h/src_w))`，再编码 PNG（无损），编码后**从 PNG 字节读回**尺寸复核。

通信协议（一行一个 JSON，带标记前缀）：stdout 只输出一行 `FEICUI_ENHANCE=<json>`（成品 PNG 走
`image_base64` ⇒ **全程不落盘**）；诊断一律走 stderr（调用侧按标记行解析，不直接 json.loads 整个 stdout）。
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sys
import time
import traceback
from pathlib import Path

MARKER = "FEICUI_ENHANCE="

HERE = Path(__file__).resolve()                      # <feicui>/server/app/enhance_runner.py
SERVER_DIR = HERE.parents[1]                         # <feicui>/server
ROOT = Path(os.environ.get("FEICUI_ROOT") or SERVER_DIR.parent).resolve()
for _p in (str(ROOT), str(SERVER_DIR)):              # SERVER_DIR 必须在前：ROOT 下有个同名 `app.py`
    if _p not in sys.path:                            # （会把 `app` 包遮成模块 ⇒ 与 square_runner 同序）
        sys.path.insert(0, _p)

# 算法＝唯一实现（纯函数；numpy/cv2/PIL 在其内部延迟导入）
import app.seal_canvas as sc  # noqa: E402


def log(msg: str) -> None:
    print(f"[enhance_runner {os.getpid()}] {msg}", file=sys.stderr, flush=True)


def _pil():
    from PIL import Image  # 延迟导入：本进程必然有，缺失时由 main 兜住

    return Image


def _lanczos():
    Image = _pil()
    res = getattr(Image, "Resampling", None)
    if res is not None and hasattr(res, "LANCZOS"):
        return res.LANCZOS
    return Image.LANCZOS  # type: ignore[attr-defined]


class BadImage(ValueError):
    """上传内容不是可解码的图片（⇒ 接口层 400 BAD_IMAGE）。"""


class NoInk(ValueError):
    """掩膜为空＝图上没有印泥像素（⇒ 接口层 422 NO_INK）。"""


def target_size(src_w: int, src_h: int, width: int) -> tuple[int, int]:
    """契约尺寸：**宽恰为 width**，高按原图 AR 取整。"""
    return int(width), max(1, int(round(int(width) * int(src_h) / float(src_w))))


def long_side_for_width(src_w: int, src_h: int, width: int) -> int:
    """`canvas_long_side` 的换算值：让 `compose` 算出的**画布宽**恰为 width。

    * 横向/正方形（src_w ≥ src_h）：画布长边＝宽 ⇒ long_side 就是 width；
    * 竖向（src_w < src_h） ：画布长边＝高 ⇒ long_side ＝ round(width·src_h/src_w)。
    """
    src_w, src_h = int(src_w), int(src_h)
    return int(round(int(width) * max(1.0, src_h / float(src_w))))


def decode(image_bytes: bytes):
    """字节 → (RGB uint8 ndarray, (w, h), mode)。一律 `convert('RGB')`（不假设白底、丢弃 alpha）。"""
    import numpy as np

    Image = _pil()
    if not image_bytes:
        raise BadImage("上传内容为空（0 字节）")
    try:
        im = Image.open(io.BytesIO(image_bytes))
        im.load()
    except Exception as exc:  # noqa: BLE001 - 任何解码异常都落 BAD_IMAGE
        raise BadImage(f"Pillow 无法解码该内容：{type(exc).__name__}: {exc}") from exc
    src_mode = str(im.mode)
    rgb = np.asarray(im.convert("RGB"))
    w, h = int(rgb.shape[1]), int(rgb.shape[0])
    return rgb, (w, h), src_mode


def process(req: dict) -> dict:
    """字节 → 成品 PNG（base64）＋ 读数。纯计算，不落任何文件。"""
    t0 = time.perf_counter()
    width = int(req.get("width") or sc.CANVAS_LONG_SIDE)
    background = str(req.get("background") or sc.BACKGROUND_PAPER)
    raw = base64.b64decode(req["image_b64"])
    rgb, (src_w, src_h), src_mode = decode(raw)

    long_side = long_side_for_width(src_w, src_h, width)
    out = sc.compose(
        rgb,
        caliber=sc.CALIBER_A,
        seed=sc.BG_SEED_DEFAULT,
        canvas_long_side=long_side,
        subject_ratio=sc.SUBJECT_LONG_SIDE_RATIO,
        halo=True,
        halo_policy=sc.HALO_POLICY_SEAL,
        background=background,
    )
    canvas = out["canvas"]
    canvas_size_before = [int(canvas.shape[1]), int(canvas.shape[0])]

    # ---- 宽度口径收口：PIL 实测 → 必要时 LANCZOS 归一（取整差 1 px 的唯一修正处）----
    want_w, want_h = target_size(src_w, src_h, width)
    normalized = False
    if (canvas_size_before[0], canvas_size_before[1]) != (want_w, want_h):
        import numpy as np

        Image = _pil()
        canvas = np.asarray(Image.fromarray(canvas).resize((want_w, want_h), _lanczos()))
        normalized = True

    # ---- 编码 PNG（无损）----
    Image = _pil()
    buf = io.BytesIO()
    Image.fromarray(canvas).save(buf, format="PNG")
    data = buf.getvalue()

    # ---- 从**编码后的 PNG 字节**读回尺寸复核（＝落盘前 PIL 实测宽度）----
    with Image.open(io.BytesIO(data)) as back:
        out_w, out_h = int(back.size[0]), int(back.size[1])
    if (out_w, out_h) != (want_w, want_h):
        raise RuntimeError(f"成品尺寸与契约不符：编码后 {out_w}x{out_h}，期望 {want_w}x{want_h}")

    elapsed_ms = int(round((time.perf_counter() - t0) * 1000))
    return {
        "ok": True,
        "mime": "image/png",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "image_base64": base64.b64encode(data).decode("ascii"),
        "width": out_w,
        "height": out_h,
        "source": {
            "width": src_w,
            "height": src_h,
            "mode": src_mode,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "params_used": {
            "width": width,
            "background": background,
            "caliber": sc.CALIBER_A,
            "subject_ratio": float(out["meta"]["subject_ratio"]),
            "seed": int(out["meta"]["seed"]),
            "halo_policy": out["meta"]["halo_policy"],
        },
        "readings": out["readings"],
        "canvas_long_side": int(long_side),
        "canvas_size_before_normalize": canvas_size_before,
        "normalized_to_target": normalized,
        "elapsed_ms_worker": elapsed_ms,
    }


def main() -> int:
    payload: dict
    try:
        req = json.loads(sys.stdin.read() or "{}")
        payload = process(req)
    except BadImage as exc:
        payload = {"ok": False, "error": "BAD_IMAGE", "detail": str(exc)}
    except NoInk as exc:
        payload = {"ok": False, "error": "NO_INK", "detail": str(exc)}
    except ValueError as exc:
        msg = str(exc)
        if "掩膜为空" in msg or "无印泥" in msg:
            payload = {"ok": False, "error": "NO_INK", "detail": msg}
        else:
            payload = {"ok": False, "error": "RUNNER_ERROR", "detail": msg}
    except KeyError as exc:
        payload = {"ok": False, "error": "BAD_REQUEST", "detail": f"缺字段：{exc}"}
    except Exception as exc:  # noqa: BLE001 - 任何异常都必须是可解析的 JSON
        log(f"未预期异常：{exc!r}\n{traceback.format_exc()}")
        payload = {"ok": False, "error": "RUNNER_ERROR", "detail": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(MARKER + json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
