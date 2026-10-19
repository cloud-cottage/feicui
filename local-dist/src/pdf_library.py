# src/pdf_library.py
"""tab1「1_Original_PDF」**纯逻辑层**：本地目录校验 / PDF 盘点 / 页数几何探针 / 元数据侧车。

架构纪律（Kevin 2026-10-16）：**逻辑与 UI 分层 ⇒ 换壳（Streamlit → PyWebView/Tauri）不返工**。
本模块**不 import streamlit**，也不含任何 `st.` 调用；`webui.py` 只做编排与渲染。
凡需要「复用老工程能力」的地方一律走**子进程或独立模块**，不在本文件重写渲染/解析算法。

口径（对齐老工程 `/feicui/pdf-records` 语义，但**只操作本地目录**）：
  * 根 ＝ 用户选定的本地 `feicui/` 目录（登录后校验通过的那个）；
  * PDF 面 ＝ `<root>/1_Original_PDF/*.pdf`（**只读盘点**——本模块不改动 PDF 本体）；
  * 元数据侧车 ＝ `local-dist/var/pdf_meta.json`（**不入库**，`.gitignore` 的 `var/` 覆盖）；
    侧车内同时缓存**派生读数**（页数 / 页尺寸 / 扫描 dpi）⇒ 重扫描不必重复解析。
"""
from __future__ import annotations

import json
import os
import re
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ============================================================
# 常量（目录口径 = 老工程 output 四总目录的三项，次序即 tab 次序）
# ============================================================
FEICUI_NAME = "feicui"
ORIGINAL_DIR = "1_Original_PDF"
HIGHRES_DIR = "2_HighRes_PDF"
TIFF_DIR = "3_Cropped_Tiff"
SUB_DIRS = [ORIGINAL_DIR, HIGHRES_DIR, TIFF_DIR]

PDF_SUFFIXES = (".pdf",)

#: 朝代值域（**逐字同值于老工程 `server/app/pdf_registry.py::DYNASTY_OPTIONS`**，
#: 该处又逐字同值于 xiai `VALUE_DOMAINS.DYNASTY_OPTIONS`；繁体口径，不得自造值）
DYNASTY_OPTIONS = (
    "商周暨春秋", "戰國", "秦", "漢", "魏晉", "隋唐", "宋元", "明早中期", "晚明",
    "清初", "清中期", "晚清", "民國", "新中國", "當代",
)

META_SCHEMA = "feicui.webui.pdf_meta.v1"

#: 侧车默认落点（local-dist/var/ 已被仓根 `.gitignore` 的 `var/` 规则忽略）
#: 打包态（PyInstaller）下资源根在 `.app` 内、**不可写** ⇒ 由入口设 `FEICUI_DATA_DIR`
#: 指到用户目录（`~/Library/Application Support/斐萃/var/pdf_meta.json`）；源码态不设 ⇒ 逐字不变。
_DATA_DIR = Path(os.environ.get("FEICUI_DATA_DIR") or Path(__file__).resolve().parents[1])
DEFAULT_META_PATH = _DATA_DIR / "var" / "pdf_meta.json"


# ============================================================
# 目录校验（**逐字保留旧行为**：目录名必须是 feicui、恰好三个子目录、3_Cropped_Tiff 不嵌套）
# ============================================================
def verify_feicui_dir(root: Path) -> tuple[bool, str]:
    """校验 feicui 目录结构。返回 (ok, msg)。"""
    root = Path(root)
    if not root.exists() or not root.is_dir():
        return False, "目录不存在"
    if root.name != FEICUI_NAME:
        return False, f"目录名称必须是 `{FEICUI_NAME}`，当前为 `{root.name}`"

    entries = list(root.iterdir())
    dirs = [e for e in entries if e.is_dir()]
    files = [e for e in entries if e.is_file() and not e.name.startswith(".")]
    if files:
        file_names = [f.name for f in files]
        return False, f"feicui 根目录不能包含文件，发现：{file_names}"
    dir_names = sorted([d.name for d in dirs])
    if dir_names != sorted(SUB_DIRS):
        return False, (
            f"feicui 根目录必须恰好包含：{SUB_DIRS}，"
            f"当前为：{dir_names}"
        )

    tiff_root = root / TIFF_DIR
    for sub in tiff_root.iterdir():
        if sub.is_dir():
            for inner in sub.iterdir():
                if inner.is_dir():
                    return False, (
                        f"3_Cropped_Tiff 不支持多级嵌套："
                        f"在 `{sub.name}` 下发现子目录 `{inner.name}`"
                    )
    return True, "目录校验通过"


def ensure_standard_subdirs(root: Path) -> tuple[bool, str]:
    """管理员一键建标准子目录（旧行为：仅在目录名为 feicui 时允许）。"""
    root = Path(root)
    if root.exists() and root.is_dir() and root.name == FEICUI_NAME:
        for sub in SUB_DIRS:
            (root / sub).mkdir(exist_ok=True)
        return True, "已创建三个标准子目录，请重新点击「校验目录并进入」"
    return False, "请先选择名为 feicui 的目录，再自动创建子目录"


# ============================================================
# 侧车元数据（读 / 写 / 改名）
# ============================================================
def load_meta(store: Path | str | None = None) -> dict:
    """读侧车；不存在/损坏 ⇒ 空壳（**不抛**，本地版要能在任何用户机器上起得来）。"""
    p = Path(store) if store else DEFAULT_META_PATH
    empty = {"schema": META_SCHEMA, "books": {}}
    if not p.exists():
        return empty
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("books"), dict):
            return empty
        return data
    except Exception:
        return empty


def save_meta(data: dict, store: Path | str | None = None) -> Path:
    """原子写侧车（先写 .part 再 replace ⇒ 断电不会留半截 JSON）。"""
    p = Path(store) if store else DEFAULT_META_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    data.setdefault("schema", META_SCHEMA)
    data.setdefault("books", {})
    tmp = p.with_suffix(p.suffix + ".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def validate_dynasty(value: str | None) -> tuple[bool, str | None]:
    """空串 ⇒ (True, None)。非空必须 ∈ 15 枚举（**绝不静默放行**）。"""
    if value is None or str(value).strip() == "":
        return True, None
    v = str(value).strip()
    if v not in DYNASTY_OPTIONS:
        return False, f"朝代必须是以下之一：{' / '.join(DYNASTY_OPTIONS)}（当前「{v}」）"
    return True, v


def update_book_meta(filename: str, *, dynasty=None, author=None, notes=None,
                     store: Path | str | None = None) -> tuple[bool, str]:
    """人工补填：写入侧车（``local-dist/var/pdf_meta.json``）。缺省键＝不改。"""
    ok, dyn = validate_dynasty(dynasty)
    if not ok:
        return False, dyn  # type: ignore[return-value]
    data = load_meta(store)
    book = data["books"].setdefault(str(filename), {})
    now = datetime.now().isoformat(timespec="seconds")
    if dynasty is not None:
        book["dynasty"] = dyn
    if author is not None:
        book["author"] = str(author).strip() or None
    if notes is not None:
        book["notes"] = str(notes).strip() or None
    book["updated_at"] = now
    save_meta(data, store)
    return True, "元数据已保存"


# ============================================================
# PDF 盘点 + 几何/页数探针（pymupdf 可用时；缺栈只降级报「—」，不静默失败）
# ============================================================
@dataclass
class PdfRow:
    """tab1 一行（一个本地 PDF）＝ 盘上事实 ＋ 侧车元数据 ＋ 派生读数。"""
    filename: str
    path: str
    size_bytes: int
    mtime: str
    page_count: int | None = None
    page_mm: str | None = None
    scan_dpi: int | None = None
    probe_error: str = ""
    dynasty: str | None = None
    author: str | None = None
    notes: str | None = None
    updated_at: str = ""

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / 1024 / 1024, 1)

    def as_row(self) -> dict:
        """给 UI 表格的行（键面固定，便于换壳时复用）。"""
        return {
            "文件名": self.filename,
            "大小(MB)": self.size_mb,
            "页数": self.page_count if self.page_count is not None else "—",
            "页面尺寸": self.page_mm or "—",
            "扫描dpi(估)": self.scan_dpi if self.scan_dpi else "—",
            "朝代": self.dynasty or "—",
            "作者": self.author or "—",
            "备注": self.notes or "—",
            "改时间": self.mtime,
            "探针": self.probe_error or "ok",
        }


def list_pdf_files(root: Path) -> list[Path]:
    """`<root>/1_Original_PDF/*.pdf`（跳过 dotfile / 子目录；按名排序）。"""
    d = Path(root) / ORIGINAL_DIR
    if not d.is_dir():
        return []
    return sorted(
        [p for p in d.iterdir()
         if p.is_file() and p.suffix.lower() in PDF_SUFFIXES and not p.name.startswith(".")],
        key=lambda p: p.name,
    )


def probe_pdf(pdf_path: Path, pages_scan: int = 3) -> dict:
    """读页数 ＋ 页面尺寸(mm) ＋ **估算**扫描 dpi。

    扫描 dpi 的估算式与老工程渲染脚本同源：``dpi = 内嵌图宽px × 72 / 页宽pt``
    （页 29 实测 2125 px / 510.0 pt ⇒ 300 dpi）。**只作前置提示**（tab2 用它判
    「目标 dpi 是否为扫描 dpi 的整数倍」），渲染真值一律以 `render_page_2400.py`
    自己解析的 `scan_dpi` 为准。
    """
    try:
        import pymupdf as fitz  # 老工程 venv：`pymupdf`
    except Exception:
        try:
            import fitz  # 备选模块名
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": f"未安装 pymupdf（{exc.__class__.__name__}）",
                    "page_count": None, "page_mm": None, "scan_dpi": None}

    try:
        with fitz.open(str(pdf_path)) as doc:
            n = doc.page_count
            page = doc[0]
            w_pt, h_pt = page.rect.width, page.rect.height
            page_mm = f"{w_pt / 72 * 25.4:.1f}×{h_pt / 72 * 25.4:.1f} mm"
            scan_dpi = None
            for i in range(min(pages_scan, n)):
                pg = doc[i]
                imgs = sorted(pg.get_images(full=True), key=lambda t: t[2] * t[3], reverse=True)
                if not imgs:
                    continue
                xref = imgs[0][0]
                info = doc.extract_image(xref)
                iw = info.get("width") or 0
                if iw and pg.rect.width > 0:
                    scan_dpi = int(round(iw * 72.0 / pg.rect.width))
                break
            return {"ok": True, "error": "", "page_count": int(n),
                    "page_mm": page_mm, "scan_dpi": scan_dpi}
    except Exception as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}",
                "page_count": None, "page_mm": None, "scan_dpi": None}


def scan(root: Path, *, store: Path | str | None = None, probe: bool = True,
         force_probe: bool = False, on_progress=None) -> dict:
    """盘点 tab1 全部 PDF ⇒ 行 + 统计，并把派生读数回写侧车（幂等）。

    返回 ``{"root":…, "rows":[…], "stats":{…}, "probe_available":bool}``。
    探针**只在「件变了 / 没读过 / force」时才跑**（重扫描＝秒回）。
    """
    root = Path(root)
    meta = load_meta(store)
    books = meta["books"]
    rows: list[PdfRow] = []
    probe_ok = False
    probed = 0
    files = list_pdf_files(root)
    for idx, p in enumerate(files, 1):
        stt = p.stat()
        mtime = datetime.fromtimestamp(stt.st_mtime).strftime("%Y-%m-%d %H:%M")
        m = books.get(p.name, {}) or {}
        stale = (m.get("size_bytes") != stt.st_size
                 or m.get("mtime_ts") != int(stt.st_mtime)
                 or m.get("page_count") is None)
        page_count, page_mm, scan_dpi, err = (
            m.get("page_count"), m.get("page_mm"), m.get("scan_dpi"), m.get("probe_error", ""))
        if probe and (force_probe or stale):
            if on_progress:
                on_progress(idx, len(files), p.name)
            info = probe_pdf(p)
            probed += 1
            if info.get("ok"):
                probe_ok = True
                page_count, page_mm, scan_dpi = (
                    info["page_count"], info["page_mm"], info["scan_dpi"])
                err = ""
            else:
                err = info.get("error", "探针失败")
                page_count, page_mm, scan_dpi = None, None, None
            books.setdefault(p.name, {}).update({
                "page_count": page_count, "page_mm": page_mm, "scan_dpi": scan_dpi,
                "probe_error": err, "size_bytes": stt.st_size,
                "mtime_ts": int(stt.st_mtime), "scanned_at": datetime.now().isoformat(timespec="seconds"),
            })
        elif m.get("page_count") is not None:
            probe_ok = True
        rows.append(PdfRow(
            filename=p.name, path=str(p), size_bytes=stt.st_size, mtime=mtime,
            page_count=page_count, page_mm=page_mm, scan_dpi=scan_dpi, probe_error=err or "",
            dynasty=m.get("dynasty"), author=m.get("author"), notes=m.get("notes"),
            updated_at=m.get("updated_at", ""),
        ))
    if probed:
        save_meta(meta, store)
    # 盘上已消失的条目：**保留**侧车里的人工元数据（不静默删），只在统计里报
    on_disk = {r.filename for r in rows}
    gone = sorted(set(books) - on_disk)
    stats = {
        "count": len(rows),
        "total_bytes": sum(r.size_bytes for r in rows),
        "with_pages": sum(1 for r in rows if r.page_count is not None),
        "annotated": sum(1 for r in rows if r.dynasty or r.author or r.notes),
        "probed_now": probed,
        "missing_from_disk": gone,
        "meta_store": str(store or DEFAULT_META_PATH),
    }
    return {"root": str(root), "rows": rows, "stats": stats, "probe_available": probe_ok}


# ============================================================
# tab3「3_Cropped_Tiff」的**现有**能力（原样迁出，逻辑面；旧行为一字不改）
# ============================================================
def list_subdirs(root: Path) -> list[str]:
    """列出 3_Cropped_Tiff 下的一级子目录。"""
    d = Path(root) / TIFF_DIR
    if not d.exists():
        return []
    return sorted([x.name for x in d.iterdir() if x.is_dir()])


def list_tiff_files(root: Path, subdir_name: str) -> list[str]:
    """列出某个一级子目录下的 tiff/tif 文件。"""
    d = Path(root) / TIFF_DIR / subdir_name
    if not d.exists():
        return []
    out = []
    for f in sorted(d.iterdir()):
        if f.is_file() and f.suffix.lower() in (".tiff", ".tif"):
            out.append(f.name)
    return out


#: 随机测试数据（逐字保留旧行为）
RANDOM_SHIWEN = ["长乐未央", "吉祥如意", "延年益寿", "清心", "淡泊明志",
                 "宁静致远", "翰墨", "金石寿", "得自在", "安且吉兮"]
RANDOM_DYNASTY = ["汉", "唐", "宋", "明", "清", "战国", "秦", "元"]
RANDOM_AUTHOR = ["陈巨来", "吴昌硕", "齐白石", "邓石如", "赵之谦", "吴让之"]


def generate_test_tiff(root: Path, subdir_name: str, placeholder: Path) -> str | None:
    """在指定一级子目录生成一个测试 tiff（合规命名，P/C/R 自动递增不重复）。

    与旧实现逐字等价（连"随机值取自哪些列表"也一致）；只把 `feicui_root` /
    占位图路径改成显式入参，方便换壳复用。
    """
    shiwen = random.choice(RANDOM_SHIWEN)
    dynasty = random.choice(RANDOM_DYNASTY)
    author = random.choice(RANDOM_AUTHOR)

    target_dir = Path(root) / TIFF_DIR / subdir_name
    target_dir.mkdir(parents=True, exist_ok=True)

    used_pages = set()
    for f in target_dir.iterdir():
        if f.is_file() and f.suffix.lower() in (".tiff", ".tif"):
            m = re.match(r"P(\d{3})-C\d-R\d-", f.name)
            if m:
                used_pages.add(int(m.group(1)))

    page = 1
    while page in used_pages:
        page += 1
    page_str = f"{page:03d}"

    used_digits = {int(d) for d in page_str}
    col = random.choice([d for d in range(10) if d not in used_digits])
    used_digits.add(col)
    row = random.choice([d for d in range(10) if d not in used_digits])

    name = f"P{page_str}-C{col}-R{row}-{shiwen}-{dynasty}-{author}.tiff"
    target = target_dir / name
    idx = 1
    while target.exists():
        idx += 1
        name = f"P{page_str}-C{col}-R{row}-{shiwen}_{idx}-{dynasty}-{author}.tiff"
        target = target_dir / name

    placeholder = Path(placeholder)
    if not placeholder.exists():
        return None
    target.write_bytes(placeholder.read_bytes())
    return target.name
