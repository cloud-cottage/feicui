"""把 `paddleocr` 的 import 变成**惰性**（真正用 OCR 时才加载）——Kong。

## 为什么需要它

`processor.py` 顶部有一句 `from paddleocr import PaddleOCR`（模块级 import），而 PaddleOCR 的 import
要拉整套推理栈（实测 `import paddleocr` ≈ 1.28s，`import processor` 合计 ≈ 1.4～3.2s）。**纯函数端点**
`POST /api/tools/square-crop`（`app/square_runner.py`）只用到 `processor.detect_stamp_regions`
（HSV 红掩膜 → CLOSE → findContours，**只用 cv2/numpy**），**一次 OCR 都不做** ⇒ 这笔冷启动开销是纯浪费。

## 做法（不动 `processor.py` 一个字节）

在 `import processor` **之前**往 `sys.modules["paddleocr"]` 装一个**惰性替身模块**：它的
`PaddleOCR` 属性是一个 shim 类，**只有真正被实例化时**才去加载**真包**并构造**真的 `PaddleOCR`**。
于是：

* `processor.detect_stamp_regions` 走的是**同一份源码**（`processor.py` 未被复制、未被修改）；
* OCR 路径**行为不变** —— 谁真调 OCR，替身就透明地把真包加载回来（延迟到那时才付 1.28s），
  并在真包缺失时如实抛 `ModuleNotFoundError`（与没装 shim 时同形）；
* 检测口径与输出字节**零影响**（替身只替换「模块名 → 类」的解析，不参与任何计算）。

## 边界

* 只在**明确知道本进程不走 OCR** 的执行体里调用（当前唯一调用方：`square_runner.py`）；
* 已被真包占用（`sys.modules` 里已有真 `paddleocr`）⇒ **不动**，返回 `False`；
* 逃生开关：环境变量 `FEICUI_SQUARE_NO_LAZY_OCR=1` ⇒ 不装替身（用于 A/B 对比与回滚）。
"""
from __future__ import annotations

import importlib
import os
import sys
import types

ENV_DISABLE = "FEICUI_SQUARE_NO_LAZY_OCR"
SHIM_MARK = "_feicui_lazy_ocr_shim"


def _load_real_paddleocr():
    """加载**真** `paddleocr` 包（先把替身从 `sys.modules` 摘除，失败则装回）。"""
    shim = sys.modules.pop("paddleocr", None)
    try:
        return importlib.import_module("paddleocr")
    except BaseException:
        if shim is not None:
            sys.modules["paddleocr"] = shim
        raise


class LazyPaddleOCR:
    """`paddleocr.PaddleOCR` 的惰性替身：**实例化时**才加载真包 + 真类。"""

    _feicui_lazy_shim = True

    def __init__(self, *args, **kwargs) -> None:
        real = _load_real_paddleocr()
        real_cls = getattr(real, "PaddleOCR")
        object.__setattr__(self, "_impl", real_cls(*args, **kwargs))

    def __getattr__(self, item: str):
        if item == "_impl":  # 防御：__init__ 未走完时的递归保护
            raise AttributeError(item)
        return getattr(self._impl, item)


def is_installed() -> bool:
    """替身是否已生效（`sys.modules["paddleocr"]` 就是本替身）。"""
    return bool(getattr(sys.modules.get("paddleocr"), SHIM_MARK, False))


def install_lazy_paddleocr() -> bool:
    """装替身。返回 `True`＝本次真的装了；`False`＝不需要/不允许（已装过 / 被真包占用 / 关掉）。"""
    if os.environ.get(ENV_DISABLE) == "1":
        return False
    existing = sys.modules.get("paddleocr")
    if existing is not None:  # 真包已导入 ⇒ 尊重现状，不动
        return False
    mod = types.ModuleType("paddleocr")
    mod.PaddleOCR = LazyPaddleOCR
    setattr(mod, SHIM_MARK, True)
    sys.modules["paddleocr"] = mod
    return True


__all__ = ["ENV_DISABLE", "LazyPaddleOCR", "install_lazy_paddleocr", "is_installed"]
