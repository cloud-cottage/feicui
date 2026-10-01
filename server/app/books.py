"""书级只读元数据（模板 / 书简码 / 影像目录规则）——Kong / 阶段 1b-i。

**用途**：worker 池派任务前，把「这本书用哪个模板、影像落在哪个目录、`img_path` 存什么」
这三件事算清楚，传参给 worker 进程（worker 侧不读 DB、不猜配置）。

**纪律**：
  * **只读**：本模块只读 `config/templates.json` / `config/book_codes.json`，**不写任何文件**；
  * **不复制口径、不发明口径**：模板别名规则与 `export.py::template_for` **同构**
    （先按 `pdf_name` 直查，未命中再看 `config/book_codes.json` 的 `template_alias`）；
    影像目录规则照 `feicui.spec.md` v1.2 §4.1 D-4②（`output/faces/<book_key>/p<页4位>_<idx2位>.<ext>`）
    与 §4.2.1（`img_path` 一律**相对 `feicui/`**）。
  * **不改既有文件**：本模块是新增文件；`export.py` / `processor.py` 一行未动。

规范锚点：§4.1 D-4、§4.2、§1.2 I-1（解析仍是同一份实现）。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

# server/app/books.py -> app -> server -> feicui
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
TEMPLATES_PATH = CONFIG_DIR / "templates.json"
BOOK_CODES_PATH = CONFIG_DIR / "book_codes.json"

# 模板条目里 process_page 真正会读的键（缺一不可；缺失即视为模板不可用）
REQUIRED_TEMPLATE_KEYS = ("hsv_low", "hsv_high", "min_area", "text_offset", "density_min", "density_max")


def _load_json(path: Path, default):
    if not path.is_file():
        return default
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_templates() -> dict:
    data = _load_json(TEMPLATES_PATH, {})
    return data if isinstance(data, dict) else {}


def load_book_codes() -> dict:
    data = _load_json(BOOK_CODES_PATH, {"books": {}})
    return data if isinstance(data, dict) else {"books": {}}


def book_code_entry(pdf_name: str, codes: dict | None = None) -> dict:
    codes = codes if codes is not None else load_book_codes()
    ent = (codes.get("books") or {}).get(pdf_name)
    return ent if isinstance(ent, dict) else {}


def template_for(pdf_name: str, templates: dict | None = None) -> tuple[dict, str | None]:
    """返回 `(模板条目, 别名来源书)`；找不到返回 `({}, None)`。

    与 `export.py::template_for` **同一条规则**（别名只在 `book_codes.json` 的
    `template_alias` 上生效），否则同一本书的解析与导出会取到不同模板（I-1 判负面）。
    """
    templates = templates if templates is not None else load_templates()
    ent = templates.get(pdf_name)
    if isinstance(ent, dict):
        return ent, None
    alias = book_code_entry(pdf_name).get("template_alias")
    if alias and isinstance(templates.get(alias), dict):
        return templates[alias], alias
    return {}, None


def template_usable(template: dict) -> bool:
    return isinstance(template, dict) and all(k in template for k in REQUIRED_TEMPLATE_KEYS)


def missing_template_keys(template: dict) -> list[str]:
    if not isinstance(template, dict):
        return list(REQUIRED_TEMPLATE_KEYS)
    return [k for k in REQUIRED_TEMPLATE_KEYS if k not in template]


_SAFE = re.compile(r"[^0-9A-Za-z_\-]+")


def book_key_for(pdf_name: str, codes: dict | None = None) -> str:
    """书简码（影像目录名）：优先 `book_codes.json` 的 `key`；否则退化为文件名主干。

    退化路径只用于「本地简码尚未登记」的书；**不得**把它当平台签发的 `short_code` 用
    （`short_code` 与 `issued` 的语义见 `config/book_codes.json` 顶部 note）。
    """
    key = book_code_entry(pdf_name, codes).get("key")
    if isinstance(key, str) and key.strip():
        return _SAFE.sub("_", key.strip()) or "UNKNOWN"
    stem = os.path.splitext(os.path.basename(pdf_name))[0]
    return _SAFE.sub("_", stem)[:40] or "UNKNOWN"


def face_relpath(book_key: str, page: int, idx: int, ext: str = "webp") -> str:
    """§4.1 D-4② 的稳定命名：`output/faces/<book_key>/p<页4位>_<idx2位>.<ext>`。

    **稳定**是幂等的前提（§4.2.2：同 `(pdf_name,page,idx)` 重跑 ⇒ 同一路径）；
    **不得**在热路径生成带时间戳 / 随机后缀的名字（§4.2.3）。
    """
    return f"output/faces/{book_key}/p{int(page):04d}_{int(idx):02d}.{ext}"


def resolve_faces_dir(faces_dir: Path, relpath: str) -> Path:
    return Path(faces_dir) / Path(relpath).relative_to("output/faces")


def img_path_for(faces_dir: Path, book_key: str, page: int, idx: int, ext: str = "webp", *, root: Path | None = None) -> str:
    """DB 里要存的 `img_path`：**相对 `feicui/`**（§4.2.1）。

    * 默认形态（`faces_dir` 就在 `feicui/` 下）⇒ 就是 `output/faces/<book_key>/…`；
    * **自测**会用一个仓库内但不在 `output/` 的临时 faces 目录（避免动 `output/` 既有产物），
      此时返回相对于 `feicui/` 的相对路径（不含前导 `/`，仍可被 E5 的
      `os.path.join(FEICUI_ROOT, img_path)` 正确定位）。
    """
    root = Path(root) if root is not None else REPO_ROOT
    abs_path = (Path(faces_dir) / book_key / f"p{int(page):04d}_{int(idx):02d}.{ext}").resolve()
    try:
        return os.path.relpath(abs_path, root)
    except ValueError:  # 跨盘（本机不会发生，兜底不掩盖）
        return str(abs_path)
