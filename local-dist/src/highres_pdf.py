#!/usr/bin/env python
# local-dist/src/highres_pdf.py
"""tab1 一键高清化 **v2**：源 PDF → **全页**高清 PDF（选定页段渲高清位图 · 其余页原样复制）。

## 干什么

`render_pdf_to_pdf(src_pdf, out_pdf, dpi=1200, page_from, page_to, …)`：

输出 PDF **恒含源 PDF 的全部页**，且 **输出第 i 页 ≡ 源第 i 页**（页数 / 顺序 / pt 尺寸一致）
⇒ 下游 tab2 切图台按页索引取页、命名 `P<页>` 时，**页索引与原件页码一一对应**（v1 只输出页段，
页码锚定丢失，这是 v2 修掉的结构性缺陷）。组装、**落盘后必须把 `.part` 重新打开真校验**：
页数 = 源页数，且逐页 `rect` 与源页误差 ≤ 0.01pt（内存里 `built.page_count` 是构造即知的
恒真断言 —— 死分支，已删）。不符 ⇒ 删 `.part`、结构化失败
`{"ok": False, "reason": "PAGE_COUNT_MISMATCH", "expected_pages", "actual_pages", "page"}`，
**`out_pdf` 一字节不变**；通过才 `replace(out)`。

### 页的角色三分（每页恰好一种）

| 角色 | 条件 | 组装动作 |
| --- | --- | --- |
| `highres` | 该页登记表里有 **dpi ≥ 本次档位**的位图且位图取得到（或该页不在本次范围内，但已有位图：**保持原档不降级**） | **跳过渲染**，嵌已存位图 |
| `render` | 在本次页范围内，且无达标位图（含「有位图但 dpi 更低」⇒ 升级重渲） | 渲本次档位 |
| `passthrough` | 不在本次范围内，且**从未高清化过** | `built.insert_pdf(src, p-1, p-1)` 原样复制页对象（不重渲、不降质、页尺寸不变、文字层保留） |

⚠ **曾经高清化过、本次不在范围内**的页必须**保持高清**（嵌已存位图），不能降级成 `passthrough`。

### 位图可得性优先级（D：多次实施不重复做）

1. 页缓存 `page_bytes_dir/P####.png`（`api.tab1_highres_start` 默认 `keep_page_pngs=true`
   ⇒ `var/highres_pages/<目录键>/<书名>/`，显式目录**本模块不删**）—— **必须验像素**：
   用 `fitz.open(png)` 读真实宽高与登记表 `px` **逐值相等**才可用（缓存被换/截断成错尺寸图 ⇒
   当「不可用」走下一级，不静默把错图当整页嵌）；
2. **已存在的 `out_pdf` 同页** `doc.extract_image(xref)` 取回 —— 同样校验像素尺寸与登记表 `px` 一致方可用
   （旧版 range-only 输出用进度里的页清单做**页映射**，不会张冠李戴）；
3. 都没有 ⇒ 重渲该页，并更新登记表（按**本次**档位登记）。

⇒ 即使页缓存被清理、只要旧 PDF 还在，多次运行仍不重复做已达标页。
**不把取回的位图写回页缓存**（避免重新膨胀几个 GB 的隐藏目录）：下次仍从旧 PDF 取，
代价是每页一次位图拷贝（≈13 MB，秒级），远低于重渲（≈6 s/页）。

### 页级 dpi 登记表（进度文件 schema **v2**）

`<out>.progress.json`：

```
{"schema": "feicui.highres.progress.v2", "src", "out", "pages_total",
 "units": {"7": {"dpi": 1200, "px": [w, h], "png": "P0007.png", "png_bytes": 13300000,
                 "pt": [w_pt, h_pt], "at": "2026-…"}},
 "run": {"dpi": 600, "want": [1, …, 10], "rendered": 7, "skipped": 3, "passthrough": 0,
         "at": "2026-…"},
 "bytes", "updated_at"[, "finished_at", "out_bytes", "status": "done"]}
```

`units` 是**按页**的登记表（v1 是「单一 dpi + 本次区间 done」，换档/换区间就整段丢弃重来 ⇒ v2 改掉）。
**兼容读 v1**：`prog.done` 各项以 `prog.dpi` 迁成 `units`（仅当该页 PNG 缓存仍在或可从旧 PDF 恢复时）。
续跑判据只剩「同 `src` + 同 `out`」；换档 / 换区间**不再丢已做工作**。

### 幂等 / 空转

同参数连跑两次，第二次 `rendered_pages = 0`。全部页都已是 `highres` 时先**校验** `out_pdf`
（页数 = 源页数、每张高清页位图 `px` 与登记表一致；页缓存里的 PNG 若被判为错尺寸则不算达标
⇒ 走重渲/旧 PDF 恢复）⇒ 合格就**不重建**（省掉整本组装），
不合格（例：旧版 range-only）⇒ 重建为全页数，**已达标页不重渲**。
`overwrite=true` 由 `api.tab1_highres_start` 先清 `out_pdf` + 进度 ⇒ 全量重渲。

* **页尺寸保真**：高清页宽高逐页取自 `src.page.rect`（pt）⇒ 输出页与原页**同 pt 尺寸**
  ⇒ 下游 400dpi 坐标系（`stamps` bbox）与 1200dpi 裁切**同一比例尺**。
* **不落中间 JPEG**（红线）：页图只以 PNG 形态存在于内存 / 页缓存目录；
  最终 PDF 里每页是一张 `/FlateDecode` 8bit RGB 图（`/DCTDecode` 一律不出现）。
* **体积告警**：累计**高清 PNG 字节**（`units` 的 `png_bytes` 之和）超 `size_limit_bytes`
  （默认 15 GiB）⇒ 结构化 `{"ok": False, "reason": "SIZE_LIMIT", …}`
  （**不静默继续**，也不删已有产物/进度）。**`passthrough` 页不计入**（它们不是本次新增的高清位图）。
* **可取消**：`cancel_event.is_set()` ⇒ 结构化 `{"ok": False, "reason": "CANCELLED", …}`。
* **失败不写半截**：`CANCELLED` / `SIZE_LIMIT` / `PAGE_COUNT_MISMATCH` / 任何异常 ⇒
  `out_pdf` **保持上一版不变**（只写 `.part` 再 `replace`），进度与 `units` 保留可续。
* **永不抛**：任何异常都变成 `{"ok": False, "reason": "ERROR", "msg": …}`（js_api 桥不许断）。

## dpi 白名单（Kevin 2026-10-20 补充口径）

**只接受 300 / 600 / 1200**（默认 **1200**）；非法值 ⇒ `{"ok": False, "reason": "BAD_DPI",
"allowed": [300, 600, 1200]}`，**一页都不渲**（先校验再开文档）。

## ⚠️ 反直觉：**1200dpi 的 PNG 比 600dpi 更小**（实测，别"优化"成 600）

白底黑字红印的印谱（`秦印类编 检索版.pdf` 第 370 页，510×734 pt）实测，同一页三档：

| dpi | 像素 | PNG 字节 | 折合 Mpx |
| --- | --- | --- | --- |
| 300 | 2125×3059 | 5.36 MB | 6.5 |
| 600 | 4250×6118 | 15.5 MB | 26.0 |
| **1200** | **8500×12236** | **13.3 MB** | **104.0** |

**1200 反而比 600 小 14%**：600dpi 正落在扫描件墨边/网点的"半软"频段，抗锯齿灰阶多、
熵高；1200dpi 已完全解析原扫描点的硬边，二值化倾向强、大片同色 ⇒ zlib 压得更好。
⇒ **别把默认档从 1200 降到 600**（体积更大、清晰度更低，双输）；父级在另一页量到
1200dpi 7.4 MB/页，量级一致（页内容不同，绝对值会浮动）。

## 耗时（macOS 本机，venv/PyMuPDF 1.28.2，p370 实测）

**拆开量**：渲染 1200dpi **0.21 s/页**（MuPDF 只解码）＋ **PNG 编码 2.85 s/页**（zlib 是瓶颈）
＋ 组装 PDF ≈ 1.2 s/页（含 13 MB 落盘）⇒ **端到端 ≈ 6 s/页**
（3 页 p370–372 全流程实测 **18.5 s**，含组装与落盘）。
851 页的书 ≈ **80–90 分钟**（父级估 1 小时，同量级；本机单页 ±20% 浮动）。
**批量跑前务必先跑 3 页量一次本机**；PNG 编码是单线程纯 CPU，多页并行收益有限（磁盘会成瓶颈）。
v2 的 `passthrough` 页只做页对象复制（**≪ 0.1 s/页**），所以「只高清化 20 页」不再需要渲整本。

## 返回（全部 JSON 可序列化；**永不抛**）

成功：`{"ok": True, "out", "bytes", "pages_done", "pages_total", "pages", "dpi", "elapsed_s",
"resumed_from", "page_bytes_dir", "page_png_bytes", "note",
"pdf_pages_total", "rendered_pages", "skipped_pages", "passthrough_pages",
"units_total", "units_best_dpi"}`

* `pages_total` = **本次范围内**页数（UI 进度条分母）；`pdf_pages_total` = **输出**页数（= 源页数）；
* `resumed_from` = **`skipped`**（＝本次因已达标而跳过的页数；**不含** `passthrough` ——
  那些页是从未处理过的，不是「续跑」）；
* `skipped_pages` = 复用已存位图**未重渲**的页数（含「范围外仍保持高清」的页）；
* `rendered_pages` / `passthrough_pages` 同名字面义 ⇒ `rendered + skipped + passthrough == pdf_pages_total`；
* `units_total` = 登记表里已高清化的页数；`units_best_dpi` = 登记表里的最高档。

失败：`{"ok": False, "reason": <BAD_DPI|BAD_RANGE|SRC_MISSING|PAGE_COUNT_MISMATCH|SIZE_LIMIT|
CANCELLED|ERROR>, …, "pages_done", "pages_total"}` —— 除 `BAD_*` / `SRC_MISSING` 外
**保留进度与页缓存**，可续跑。

## 红线

纯逻辑层：**不 import webview / streamlit / ui**、不读写 DB、不发网络；只碰 `src_pdf` /
`out_pdf` / 页缓存目录 / 进度文件。页缓存目录由本模块创建时，成功收尾会**删掉**
（除非 `page_bytes_dir` 是调用方显式给的 —— 那是给 tab2 切图复用的，**不删**）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

try:                                    # PyMuPDF ≥1.24 新名；旧包回落 `fitz`
    import pymupdf as fitz
except ImportError:                     # pragma: no cover
    import fitz  # type: ignore

__all__ = [
    "ALLOWED_DPI",
    "DEFAULT_DPI",
    "DEFAULT_SIZE_LIMIT_BYTES",
    "PROGRESS_SCHEMA",
    "PROGRESS_SCHEMA_V1",
    "progress_path",
    "render_pdf_to_pdf",
    "read_progress",
]

#: dpi 白名单（Kevin 2026-10-20：**只三档**，不是任意整数）。顺序即 UI 档位顺序。
ALLOWED_DPI = (300, 600, 1200)
#: 默认档（1200：清晰度最高、体积反而最小，见模块 docstring 实测表）。
DEFAULT_DPI = 1200
#: 体积告警阈值（15 GiB）：851 页 × ~13 MB ≈ 11 GB，留余量；超了先报警而不是撑爆盘。
DEFAULT_SIZE_LIMIT_BYTES = 15 * 1024 ** 3
#: 进度文件 schema（v2：页级 dpi 登记表 `units`；加法字段随时加，不改既有键）。
PROGRESS_SCHEMA = "feicui.highres.progress.v2"
#: 旧 schema（v1：单一 dpi + 本次区间 `done`）—— **只读兼容**，写完一律升 v2。
PROGRESS_SCHEMA_V1 = "feicui.highres.progress.v1"


def progress_path(out_pdf) -> Path:
    """`<out>.progress.json`（**逐字**：输出 PDF 全路径后面直接接 `.progress.json`）。"""
    return Path(str(out_pdf) + ".progress.json")


def read_progress(out_pdf) -> dict:
    """读进度（无文件 / 坏 JSON ⇒ 空 dict，**不抛**）。"""
    p = progress_path(out_pdf)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data: dict) -> None:
    """原子写（同目录 tmp → replace）：避免取消/断电留下半截 JSON 让续跑误判。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _fail(reason: str, **kw) -> dict:
    out = {"ok": False, "reason": reason}
    out.update(kw)
    return out


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _page_cache_dir(out_pdf: Path, page_bytes_dir) -> tuple[Path, bool]:
    """⇒ `(页缓存目录, 是否本模块自建)`。显式给了 `page_bytes_dir` ⇒ 不自建（不删）。"""
    if page_bytes_dir:
        return Path(page_bytes_dir), False
    return out_pdf.parent / f".pages-{out_pdf.stem}", True


def _render_png(page, dpi: int) -> tuple[bytes, int, int]:
    """渲一页 ⇒ `(png_bytes, w_px, h_px)`。RGB 8bit，无 alpha（印谱是白底，alpha 只会增熵）。"""
    pix = page.get_pixmap(dpi=int(dpi), alpha=False, colorspace=fitz.csRGB)
    if pix.n != 3:                                   # 兜底：理论上 csRGB+alpha=False 恒为 3
        pix = page.get_pixmap(dpi=int(dpi), alpha=False)
    return pix.tobytes("png"), pix.width, pix.height


# ── 进度：读 + v1→v2 迁移 ────────────────────────────────────────────────────
def _load_units(prog: dict, total_pages: int) -> dict[int, dict]:
    """进度 ⇒ `{页号: unit}`（**兼容 v1**：`done` 各项以 `prog.dpi` 迁成 units）。

    v1 的 `done` 只记「本次区间做过的页」，`dpi` 是整段单一档 ⇒ 迁移即按页补 `dpi`。
    位图是否真的还取得到，留给调用方用 `_bitmap_how` 逐页探（D 优先级）；取不到的页
    会被判成 `render`，等于「迁移了登记但重渲」，不会误跳。
    """
    schema = str(prog.get("schema") or "")
    if schema == PROGRESS_SCHEMA:
        raw = prog.get("units") or {}
        base_dpi = 0
    elif schema == PROGRESS_SCHEMA_V1:
        raw = prog.get("done") or {}
        try:
            base_dpi = int(prog.get("dpi") or 0)
        except Exception:
            base_dpi = 0
    else:
        return {}
    if not isinstance(raw, dict):
        return {}
    units: dict[int, dict] = {}
    for k, rec in raw.items():
        try:
            pno = int(k)
        except Exception:
            continue
        if not (1 <= pno <= int(total_pages)):
            continue
        rec = rec if isinstance(rec, dict) else {}
        try:
            unit_dpi = int(rec.get("dpi") or base_dpi or 0)
        except Exception:
            unit_dpi = 0
        if unit_dpi <= 0:
            continue
        units[pno] = {
            "dpi": unit_dpi,
            "px": list(rec.get("px") or []),
            "png": str(rec.get("png") or ""),
            "png_bytes": int(rec.get("png_bytes") or 0),
            "pt": list(rec.get("pt") or []),
            "at": str(rec.get("at") or ""),
        }
    return units


# ── 位图可得性：① 页缓存 → ② 旧 out_pdf → ③ None（需重渲）───────────────────
def _open_existing(path: Path):
    """打开已存在的 PDF（不存在 / 0 字节 / 打不开 ⇒ None，不抛）。"""
    try:
        if path.is_file() and path.stat().st_size > 0:
            return fitz.open(path)
    except Exception:
        pass
    return None


def _out_page_map(out_doc, prog: dict, total_pages: int) -> dict[int, int] | None:
    """源页号 ⇒ 旧 `out_doc` 里的页索引。

    * 旧 PDF 已是全页数 ⇒ 恒等映射；
    * 旧 PDF 是 v1 的 **range-only**（页数 = 源页数之外的页段）⇒ 用进度里的 `pages` 页清单
      建映射（**绝不按下标硬套**，否则会把第 4 页的位图嵌到第 1 页）；
    * 都对不上 ⇒ None（不许从旧 PDF 恢复）。
    """
    if out_doc is None:
        return None
    n = int(out_doc.page_count)
    if n == int(total_pages):
        return {p: p - 1 for p in range(1, int(total_pages) + 1)}
    legacy = prog.get("pages")
    if isinstance(legacy, list) and len(legacy) == n:
        try:
            return {int(p): i for i, p in enumerate(legacy)}
        except Exception:
            return None
    return None


def _out_page_image(out_doc, out_map, pno: int, unit: dict):
    """旧 PDF 同页最大位图的 `(xref, w, h)`；页内无图 ⇒ None。"""
    if out_doc is None or out_map is None:
        return None
    idx = out_map.get(pno)
    if idx is None or idx < 0 or idx >= int(out_doc.page_count):
        return None
    try:
        imgs = out_doc[idx].get_images(full=True)
    except Exception:
        return None
    best = None
    for im in imgs or []:
        try:
            xref, w, h = int(im[0]), int(im[2]), int(im[3])
        except Exception:
            continue
        if best is None or w * h > best[0]:
            best = (w * h, xref, w, h)
    if best is None:
        return None
    return best[1], best[2], best[3]


def _out_has_bitmap(out_doc, out_map, pno: int, unit: dict) -> bool:
    """旧 PDF 同页位图是否存在**且像素与登记表一致**（D② 的校验门槛）。"""
    hit = _out_page_image(out_doc, out_map, pno, unit)
    if hit is None:
        return False
    _xref, w, h = hit
    px = (unit or {}).get("px") or []
    if len(px) == 2:
        try:
            if [int(px[0]), int(px[1])] != [int(w), int(h)]:
                return False
        except Exception:
            return False
    return True


def _png_px(path: Path):
    """PNG **真实**像素宽高 `(w, h)`（`fitz.open` 读回图像对象；读不出 ⇒ None）。

    缓存可能被外部替换 / 截断 / 换成别的页 ⇒ **不许只看文件存在就信**（否则错图会被当整页嵌）。
    """
    doc = None
    try:
        doc = fitz.open(str(path))
        if int(getattr(doc, "page_count", 0) or 0) < 1:
            return None
        # 图像文档：`get_image_info` 给的是**真实像素**（page.rect 是按 96dpi 折算的 pt，
        # 拿它当像素会小 25%，故不能用 rect）
        for inf in doc[0].get_image_info(xrefs=True) or []:
            w, h = int(inf.get("width") or 0), int(inf.get("height") or 0)
            if w > 0 and h > 0:
                return w, h
        pix = fitz.Pixmap(str(path))                 # 兜底：直接解图像
        return int(pix.width), int(pix.height)
    except Exception:
        return None
    finally:
        try:
            if doc is not None:
                doc.close()
        except Exception:
            pass


def _cache_png(unit, cache_dir: Path):
    """页缓存可用 ⇒ 返回 `Path`；不可用（无名 / 空文件 / **像素与登记表不符**）⇒ None。

    像素校验口径：`unit["px"]` 必须齐备，且与 `fitz.open(png)` 读回的真实宽高**逐值相等**。
    """
    if not unit:
        return None
    name = str(unit.get("png") or "")
    if not name:
        return None
    px = list(unit.get("px") or [])
    if len(px) != 2:
        return None
    try:
        want = (int(px[0]), int(px[1]))
    except Exception:
        return None
    f = cache_dir / name
    try:
        if not f.is_file() or f.stat().st_size <= 0:
            return None
    except Exception:
        return None
    got = _png_px(f)
    if got is None or (int(got[0]), int(got[1])) != want:
        return None                                  # 错尺寸 ⇒ 当不可用（走下一级 / 重渲）
    return f


def _bitmap_how(pno: int, unit, cache_dir: Path, out_doc, out_map) -> str | None:
    """⇒ `"cache"` / `"out"` / `None`（都没有 ⇒ 该页必须重渲）。缓存命中须过像素校验。"""
    if not unit:
        return None
    if _cache_png(unit, cache_dir) is not None:
        return "cache"
    if _out_has_bitmap(out_doc, out_map, pno, unit):
        return "out"
    return None


def _bitmap_bytes(pno: int, unit: dict, cache_dir: Path, out_doc, out_map):
    """取位图字节（缓存优先，其次旧 PDF）；取不到 ⇒ None。与 `_bitmap_how` 同一套校验。"""
    f = _cache_png(unit, cache_dir)
    if f is not None:
        try:
            return f.read_bytes()
        except Exception:
            pass
    hit = _out_page_image(out_doc, out_map, pno, unit)
    if hit is None:
        return None
    xref, _w, _h = hit
    try:
        return out_doc.extract_image(xref).get("image")
    except Exception:
        return None


#: 落盘复核的页尺寸容差（pt）：组装是「按源 rect 新建页」，正常应为 0 误差
_RECT_TOL_PT = 0.01


def _verify_saved_pdf(pdf_path, src_doc, total_pages: int) -> dict | None:
    """**落盘后**把 `.part` 重新打开真校验：页数 + 逐页 `rect`（容差 ≤0.01pt）。

    合格 ⇒ `None`；不合格 ⇒ `{"expected_pages", "actual_pages", "page"}`
    （`page` = 首个尺寸不符页，1-based；页数不符 / 打不开 ⇒ 0）。纯读，不改文件。
    """
    doc = None
    try:
        doc = fitz.open(str(pdf_path))
        actual = int(doc.page_count)
        if actual != int(total_pages):
            return {"expected_pages": int(total_pages), "actual_pages": actual, "page": 0}
        for i in range(actual):
            got, want = doc[i].rect, src_doc[i].rect
            if (abs(float(got.width) - float(want.width)) > _RECT_TOL_PT
                    or abs(float(got.height) - float(want.height)) > _RECT_TOL_PT):
                return {"expected_pages": int(total_pages), "actual_pages": actual, "page": i + 1}
        return None
    except Exception:
        return {"expected_pages": int(total_pages), "actual_pages": 0, "page": 0}
    finally:
        try:
            if doc is not None:
                doc.close()
        except Exception:
            pass


def _verify_out(out_doc, out_map, roles: dict, units: dict, total_pages: int) -> bool:
    """输出 PDF 是否「已是最新」：页数对 + 每张高清页位图像素对（省掉整本重建）。"""
    if out_doc is None or int(out_doc.page_count) != int(total_pages):
        return False
    for pno, role in roles.items():
        if role == "highres" and not _out_has_bitmap(out_doc, out_map, pno, units[pno]):
            return False
    return True


def _cancelled(cancel_event) -> bool:
    try:
        return bool(cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)())
    except Exception:
        return False


def render_pdf_to_pdf(src_pdf, out_pdf, dpi: int = DEFAULT_DPI, page_from: int = 1,
                      page_to: int | None = None, page_bytes_dir=None,
                      progress_cb=None, cancel_event=None,
                      size_limit_bytes: int = DEFAULT_SIZE_LIMIT_BYTES) -> dict:
    """源 PDF ⇒ **全页**高清 PDF（选定页段渲高清位图 · 其余页原样复制 · 断点续跑 · 可取消）。

    参数
    ----
    src_pdf : 源 PDF 路径（`output/1_Original_PDF/<书名>.pdf`）
    out_pdf : 目标 PDF 路径（`output/2_HighRes_PDF/<目录键>/<书名>-HighRes.pdf`），**恒全页**
    dpi     : **只接受 300 / 600 / 1200**（默认 1200）；非法 ⇒ `BAD_DPI`，不渲一页
    page_from / page_to : **1-based 闭区间**（`page_to=None` ⇒ 到末页）；范围内渲高清，
                          范围外原样保留页码
    page_bytes_dir : 逐页 PNG 缓存目录（给了 ⇒ **保留**，供 tab2 切图直接复用；
                     不给 ⇒ 自建隐藏目录 `<out 同目录>/.pages-<书名>/`，成功后删除）
    progress_cb : `callable(dict)`，每渲完一页回调
                  `{page, pages_total, pages_done, bytes, png_bytes, reused,
                    rendered, skipped, passthrough, pdf_pages_total, msg}`（异常被吞）
    cancel_event: `threading.Event`；`is_set()` ⇒ 停（当前页渲完即停，不写半页、不动 out_pdf）
    size_limit_bytes : 累计**高清 PNG** 字节上限（超过 ⇒ `SIZE_LIMIT`；passthrough 不计）

    返回：见模块 docstring「返回」。**永不抛。**
    """
    t_start = time.time()
    # ── 1. 参数校验（全部前置：别渲了 300 页才发现 dpi 非法）──────────────────
    try:
        dpi = int(dpi)
    except Exception:
        return _fail("BAD_DPI", dpi=dpi, allowed=list(ALLOWED_DPI))
    if dpi not in ALLOWED_DPI:
        return _fail("BAD_DPI", dpi=dpi, allowed=list(ALLOWED_DPI),
                     msg=f"dpi 只支持 {list(ALLOWED_DPI)}")
    src = Path(src_pdf)
    if not src.is_file():
        return _fail("SRC_MISSING", src=str(src), msg=f"源 PDF 不存在：{src}")
    out = Path(out_pdf)
    try:
        page_from = int(page_from or 1)
    except Exception:
        return _fail("BAD_RANGE", msg=f"page_from 必须是整数：{page_from!r}")
    try:
        if page_from < 1:
            return _fail("BAD_RANGE", msg="page_from 从 1 开始")
        page_to_i = None if page_to in (None, "") else int(page_to)
    except Exception:
        return _fail("BAD_RANGE", msg=f"page_to 必须是整数：{page_to!r}")
    if page_to_i is not None and page_to_i < page_from:
        return _fail("BAD_RANGE", msg=f"page_to({page_to_i}) < page_from({page_from})")

    cache_dir, cache_owned = _page_cache_dir(out, page_bytes_dir)
    prog_file = progress_path(out)

    try:
        doc = fitz.open(src)
    except Exception as exc:
        return _fail("ERROR", msg=f"打不开源 PDF：{exc.__class__.__name__}: {exc}", src=str(src))
    out_doc = None
    try:
        total_pages = int(doc.page_count)
        last = total_pages if page_to_i is None else min(page_to_i, total_pages)
        if page_from > total_pages:
            return _fail("BAD_RANGE", msg=f"page_from({page_from}) 超出总页数({total_pages})",
                         pages_total=total_pages)
        want = list(range(page_from, last + 1))
        want_set = set(want)

        # ── 2. 进度：同 src + 同 out 即可续（换档 / 换区间**不丢**已做工作）──────
        prog = read_progress(out)
        if not (str(prog.get("src") or "") == str(src) and str(prog.get("out") or "") == str(out)):
            prog = {}                                   # 换书 / 换落点 ⇒ 登记表作废
        units = _load_units(prog, total_pages)
        out_doc = _open_existing(out)
        out_map = _out_page_map(out_doc, prog, total_pages)

        # ── 3. 页角色三分（B）─────────────────────────────────────────────────────
        roles: dict[int, str] = {}
        to_render: list[int] = []
        skipped = 0
        passthrough = 0
        for pno in range(1, total_pages + 1):
            unit = units.get(pno)
            how = _bitmap_how(pno, unit, cache_dir, out_doc, out_map)
            if pno in want_set:
                if how and unit is not None and int(unit.get("dpi") or 0) >= dpi:
                    roles[pno] = "highres"              # 已达标 ⇒ 跳过渲染
                    skipped += 1
                else:
                    roles[pno] = "render"               # 无位图 或 档位更低 ⇒ 渲/升级
                    to_render.append(pno)
            else:
                if how:
                    roles[pno] = "highres"              # 曾高清化 ⇒ 保持高清，不降级
                    skipped += 1
                else:
                    roles[pno] = "passthrough"          # 从未高清化 ⇒ 原样复制页对象
                    passthrough += 1

        cache_dir.mkdir(parents=True, exist_ok=True)
        bytes_total = sum(int((u or {}).get("png_bytes") or 0) for u in units.values())
        run = {"dpi": dpi, "want": list(want), "rendered": 0, "skipped": skipped,
               "passthrough": passthrough, "at": _now()}

        def _state(**extra) -> dict:
            data = {"schema": PROGRESS_SCHEMA, "src": str(src), "out": str(out),
                    "pages_total": total_pages,
                    "units": {str(k): v for k, v in sorted(units.items())},
                    "run": dict(run, skipped=skipped, passthrough=passthrough),
                    "bytes": bytes_total, "updated_at": _now()}
            data.update(extra)
            return data

        pages_meta: list[dict] = []
        rendered = 0

        def _ok(pdf_pages_total: int, note: str, **extra) -> dict:
            res = {"ok": True, "out": str(out),
                   "bytes": out.stat().st_size if out.is_file() else 0,
                   "pages_done": len(want),     # 成功返回时 want 内每页都已达标（渲完或复用）
                   "pages_total": len(want), "pages": pages_meta, "dpi": dpi,
                   "elapsed_s": round(time.time() - t_start, 2),
                   # 续跑口径：只数「因已达标而跳过」的页；passthrough 是从未处理过的，不算续跑
                   "resumed_from": skipped,
                   "rendered_pages": rendered, "skipped_pages": skipped,
                   "passthrough_pages": passthrough, "pdf_pages_total": int(pdf_pages_total),
                   "units_total": len(units),
                   "units_best_dpi": max([int(u["dpi"]) for u in units.values()] or [0]),
                   "page_bytes_dir": str(cache_dir) if not cache_owned else None,
                   "page_png_bytes": bytes_total, "note": note}
            res.update(extra)
            return res

        # ── 4. 全部页已达标 ⇒ 先**校验** out_pdf（合格就不重建，省掉整本组装）──
        if not to_render:
            if _verify_out(out_doc, out_map, roles, units, total_pages):
                _write_json(prog_file, _state(finished_at=_now(), status="done",
                                              out_bytes=(out.stat().st_size
                                                         if out.is_file() else 0)))
                return _ok(total_pages,
                           f"输出已是最新（全 {total_pages} 页 · {skipped} 页已达标），未重渲")

        # ── 5. 逐页渲（只渲 render 页）⇒ PNG 落缓存 ⇒ 记登记表 ───────────────────
        for pno in to_render:
            if _cancelled(cancel_event):
                _write_json(prog_file, _state())
                return _fail("CANCELLED",
                             pages_done=len(want) - len(to_render) + rendered,
                             pages_total=len(want), bytes=bytes_total,
                             page_bytes_dir=str(cache_dir) if not cache_owned else None,
                             out=str(out), dpi=dpi,
                             rendered_pages=rendered, skipped_pages=skipped,
                             passthrough_pages=passthrough, pdf_pages_total=total_pages,
                             elapsed_s=round(time.time() - t_start, 2),
                             msg=f"已取消（本次已渲 {rendered}/{len(to_render)} 页，进度保留可续跑）")
            page = doc[pno - 1]
            png, w_px, h_px = _render_png(page, dpi)
            png_file = cache_dir / f"P{pno:04d}.png"
            png_file.write_bytes(png)
            unit = {"dpi": dpi, "px": [w_px, h_px], "png": png_file.name,
                    "png_bytes": len(png),
                    "pt": [round(float(page.rect.width), 3), round(float(page.rect.height), 3)],
                    "at": _now()}
            units[pno] = unit
            rendered += 1
            run["rendered"] = rendered
            bytes_total += len(png)
            _write_json(prog_file, _state())
            pages_meta.append({"page": pno, "role": "render", "dpi": dpi,
                               "px": [w_px, h_px], "png_bytes": len(png),
                               "png": png_file.name, "reused": False})
            if progress_cb is not None:
                try:
                    progress_cb({"page": pno, "pages_total": len(want),
                                 "pages_done": len(want) - len(to_render) + rendered,
                                 "bytes": bytes_total, "png_bytes": len(png), "reused": False,
                                 "rendered": rendered, "skipped": skipped,
                                 "passthrough": passthrough, "pdf_pages_total": total_pages,
                                 "msg": f"第 {pno} 页 {w_px}×{h_px}"})
                except Exception:
                    pass
            # 体积告警：**渲完这页就停**（进度留着，用户可换盘/清空间后续跑）
            if size_limit_bytes and bytes_total > int(size_limit_bytes):
                _write_json(prog_file, _state())
                return _fail("SIZE_LIMIT", bytes=bytes_total, limit_bytes=int(size_limit_bytes),
                             pages_done=len(want) - len(to_render) + rendered,
                             pages_total=len(want), out=str(out), dpi=dpi,
                             page_bytes_dir=str(cache_dir) if not cache_owned else None,
                             rendered_pages=rendered, skipped_pages=skipped,
                             passthrough_pages=passthrough, pdf_pages_total=total_pages,
                             elapsed_s=round(time.time() - t_start, 2),
                             msg=(f"体积已超阈值（{bytes_total/1024**3:.2f} GiB > "
                                  f"{int(size_limit_bytes)/1024**3:.2f} GiB），已停在第 {pno} 页；"
                                  f"进度与页缓存已保留，可续跑"))

        for pno in want:
            role = roles[pno]
            if role == "highres":
                u = units[pno]
                pages_meta.append({"page": pno, "role": "highres", "dpi": int(u["dpi"]),
                                   "px": list(u.get("px") or []),
                                   "png_bytes": int(u.get("png_bytes") or 0),
                                   "png": u.get("png") or "", "reused": True})

        # ── 6. 组装**全页** PDF：范围内嵌高清位图 / 范围外原样复制页对象（A、B）──
        out.parent.mkdir(parents=True, exist_ok=True)
        built = fitz.open()
        tmp_out = out.with_name(out.name + ".part")
        try:
            for pno in range(1, total_pages + 1):
                if roles[pno] == "passthrough":
                    built.insert_pdf(doc, from_page=pno - 1, to_page=pno - 1)
                    continue
                stream = _bitmap_bytes(pno, units[pno], cache_dir, out_doc, out_map)
                if not stream:
                    raise RuntimeError(f"第 {pno} 页位图取不到（缓存与旧 PDF 均无）")
                rect = doc[pno - 1].rect                 # pt 尺寸取**源页** ⇒ 同比例尺
                np_page = built.new_page(width=float(rect.width), height=float(rect.height))
                np_page.insert_image(np_page.rect, stream=stream)
                del stream
            # 内存页数断言是死分支（每轮必定 new_page / insert_pdf）⇒ 改为**落盘后真复核**
            built.save(str(tmp_out), deflate=True)   # deflate=True：未压缩流压掉；图像流已是 Flate
            built.close()
        finally:
            try:
                built.close()
            except Exception:
                pass
        bad = _verify_saved_pdf(tmp_out, doc, total_pages)
        if bad:
            try:
                tmp_out.unlink()                     # 失败不留半截 / 不留 .part
            except Exception:
                pass
            return _fail("PAGE_COUNT_MISMATCH",
                         expected_pages=int(bad.get("expected_pages") or total_pages),
                         actual_pages=int(bad.get("actual_pages") or 0),
                         page=int(bad.get("page") or 0),
                         src_pages=int(doc.page_count),        # 旧键保留（兼容）
                         built_pages=int(bad.get("actual_pages") or 0),
                         out=str(out), dpi=dpi,
                         rendered_pages=rendered, skipped_pages=skipped,
                         passthrough_pages=passthrough,
                         elapsed_s=round(time.time() - t_start, 2),
                         msg=(f"落盘复核失败：期望 {total_pages} 页 / 源页尺寸一致，"
                              f"实得 {bad.get('actual_pages')} 页"
                              f"（首个不符页 {bad.get('page') or '-'}），"
                              f"已删 .part（out_pdf 保持上一版不变）"))
        tmp_out.replace(out)

        out_bytes = out.stat().st_size
        _write_json(prog_file, _state(finished_at=_now(), out_bytes=out_bytes, status="done"))
        # 自建缓存目录且不是给 tab2 复用的 ⇒ 清掉（不给用户留几个 GB 的隐藏目录）
        if cache_owned:
            try:
                for f in cache_dir.glob("P*.png"):
                    f.unlink()
                cache_dir.rmdir()
            except Exception:
                pass
        if rendered:
            note = (f"高清化完成：渲 {rendered} 页 · 跳过 {skipped} 页（已达标）· "
                    f"原样保留 {passthrough} 页 · 输出 {total_pages} 页")
        else:
            note = (f"未重渲（渲 0 页 · 跳过 {skipped} 页 · 原样保留 {passthrough} 页），"
                    f"已按全页重建输出 {total_pages} 页")
        return _ok(total_pages, note)
    except Exception as exc:                       # 兜底：桥不许断
        return _fail("ERROR", msg=f"{exc.__class__.__name__}: {exc}", src=str(src), out=str(out),
                     pages_done=len(locals().get("units") or {}),
                     elapsed_s=round(time.time() - t_start, 2))
    finally:
        for d in (doc, out_doc):
            try:
                if d is not None:
                    d.close()
            except Exception:
                pass
