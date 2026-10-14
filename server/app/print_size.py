"""「印刷尺寸即实物尺寸」（print_size_1to1）——工具函数 ＋ 配置读写（**additive**，2026-10）。

需求（Kevin ②）：印谱常**原大（1:1）印刷** ⇒ 印面实物尺寸可由 bbox 像素 ÷ 扫描 dpi 反算：
`mm = px / dpi × 25.4`。用户导入/建 job 时给**勾选框【印刷尺寸即实物尺寸】**；落地面：

* **配置侧**：`config/book_dir_keys.json` 对应书目条目落 `print_size_1to1: true`
  （加法字段，与既有键**同名同义**；该文件是加法文件，本模块**只增不改**——
  既不删键、不改既有键值，只把目标书目的该字段与来源注记补上）。
* **job 侧**：`jobs` 表加法列 `print_size_1to1`（迁移 `1a-0005`；NULL＝未指定）。
* **下游闭环**：当该值为 true，E3 印面记录可由 `bbox px + 实际渲染 dpi` 推算 `size_mm`
  （见 `size_mm_for_bbox`；在 `records.build_items` 里逐条挂 `size_mm` 顶层字段）。

纪律：
* 本模块是**接口层安全**的：只用 stdlib（json/os/pathlib/datetime），**不 import**
  cv2 / numpy / pymupdf（§6.5 解释器矩阵：`server/.venv` 无图像栈）。
* dpi 真源：`feicui/processor.py::RENDER_DPI`（生产渲染 400 dpi，`stamps.x1..y2` 的坐标轴）。
  接口层不能 import processor（它 import cv2）⇒ 此处**镜像常量**，先例＝`square.py`
  的 RENDER_DPI/BASE_DPI 镜像注释。改渲染 dpi 时两处一起改（单点可改常量）。
* 配置写**失败不阻断 E1**（调用方 catch）；写盘原子（`.part` → `os.replace`）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

#: 生产渲染 dpi（`feicui/processor.py::RENDER_DPI` 的镜像；`stamps` bbox 的坐标轴）。
RENDER_DPI = 400.0

#: 默认目录键表（与 `naming.DEFAULT_DIR_KEYS_PATH` 同一文件）。
DEFAULT_DIR_KEYS_PATH = Path(__file__).resolve().parents[2] / "config" / "book_dir_keys.json"

#: MM 换算保留位数（亚 0.01 mm 无意义：扫描 dpi 本身有 ±2 pt 抖动）。
MM_DIGITS = 3


def px_to_mm(px: float, dpi: float = RENDER_DPI) -> float:
    """`mm = px / dpi × 25.4`（印刷尺寸即实物尺寸的唯一换算式）。"""
    if not dpi or dpi <= 0:
        raise ValueError(f"dpi 必须为正：{dpi!r}")
    return round(px / dpi * 25.4, MM_DIGITS)


def size_mm_for_bbox(
    x1: float | None, y1: float | None, x2: float | None, y2: float | None,
    *, dpi: float = RENDER_DPI,
) -> dict[str, Any] | None:
    """bbox px → `{"width_mm", "height_mm", "dpi", "basis"}`；bbox 缺任一角 ⇒ `None`（不臆造）。"""
    if x1 is None or y1 is None or x2 is None or y2 is None:
        return None
    w_px = abs(float(x2) - float(x1))
    h_px = abs(float(y2) - float(y1))
    return {
        "width_mm": px_to_mm(w_px, dpi),
        "height_mm": px_to_mm(h_px, dpi),
        "dpi": dpi,
        "basis": "print_size_1to1(px/dpi*25.4)",
    }


# --------------------------------------------------------------------------- 读
def load_books(dir_keys_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """`config/book_dir_keys.json` 的 `books` 表（文件缺失/形状不符 ⇒ `{}`，不抛）。"""
    p = Path(dir_keys_path) if dir_keys_path is not None else DEFAULT_DIR_KEYS_PATH
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    books = data.get("books") if isinstance(data, dict) else None
    return books if isinstance(books, dict) else {}


def print_size_1to1_for(pdf_name: str, dir_keys_path: str | os.PathLike[str] | None = None) -> bool:
    """该书是否登记了「印刷尺寸即实物尺寸」（键＝PDF 文件名逐字；未登记 ⇒ False）。"""
    entry = load_books(dir_keys_path).get(str(pdf_name))
    return bool(isinstance(entry, dict) and entry.get("print_size_1to1"))


def book_flags(dir_keys_path: str | os.PathLike[str] | None = None) -> dict[str, bool]:
    """全部书目的 `print_size_1to1` 旗标（供前端在打开表单时按书名默认勾选）。"""
    return {
        str(name): bool(entry.get("print_size_1to1"))
        for name, entry in load_books(dir_keys_path).items()
        if isinstance(entry, dict)
    }


# --------------------------------------------------------------------------- 写（只增不改）
def set_print_size_1to1(
    pdf_name: str,
    value: bool,
    *,
    dir_keys_path: str | os.PathLike[str] | None = None,
    source: str = "e1_api",
) -> dict[str, Any]:
    """把 `print_size_1to1` 写进对应书目条目（**加法字段**；返回该条目写后形态）。

    * 条目已存在且该字段已是目标值 ⇒ **no-op**（不重写文件，幂等）；
    * 条目存在 ⇒ 只补该字段 ＋ `print_size_1to1_set_at` / `print_size_1to1_source`
      两个注记键；**既有键（含 `print_size_1to1_evidence`）一字不动**；
    * 条目不存在 ⇒ 新建最小条目（`pdf_name` ＋ 字段 ＋ 注记）；目录键照旧由
      `naming.dir_key_entry` 回落（无 `dir_key` 的条目不影响既有回落逻辑）。
    """
    p = Path(dir_keys_path) if dir_keys_path is not None else DEFAULT_DIR_KEYS_PATH
    with p.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    books = data.get("books")
    if not isinstance(books, dict):
        raise ValueError(f"{p}: 顶层缺 books 表（形状不符，不写）")
    entry = books.get(pdf_name)
    if not isinstance(entry, dict):
        entry = {"pdf_name": pdf_name}
        books[pdf_name] = entry
    entry_any: dict[str, Any] = entry
    if entry_any.get("print_size_1to1") is value:
        return entry_any  # 幂等：已同值 ⇒ 不动文件
    entry_any["print_size_1to1"] = bool(value)
    entry_any["print_size_1to1_set_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    entry_any["print_size_1to1_source"] = source
    part = p.with_name(p.name + ".part")
    with part.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(part, p)
    return entry
