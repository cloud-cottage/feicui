#!/usr/bin/env python
"""feicui 解析 worker（**子进程**，由 `app/pool.py` 池管理）——Kong / 阶段 1b-i。

**解释器纪律（规范 v1.2 §6.5 解释器矩阵）**：本脚本**必须**由 `feicui/venv/bin/python` 运行
（OCR 栈在该 venv 内）；接口层 `server/.venv` **不得**出现 OCR 栈 / PyMuPDF。
`cwd` **必须**是 `feicui/` 根目录（`processor.py` 与 `config/` 都是相对路径取的）。

**它与池的分工（规范 §4.3）**：
  * 本进程**只做计算与影像落盘**（渲染 / 检测 / 释文块匹配 / OCR / 写 `.webp`），**绝不碰 DB**；
  * 唯一写库者＝池进程（单写者，§4.3「WAL 单写者 ⇒ 必须串行化写」）；
  * 落盘顺序＝**先写影像（+fsync）→ 再由池提交 DB 行**（§4.3：崩溃窗口允许孤儿影像、不允许孤儿 DB 行）。

**与 `processor.py` 的关系（§1.2 I-1：解析仍是同一份实现）**：
所有**像素级**处理一律直接调用 `processor.py` 的既有函数（`render_page` / `detect_stamp_regions` /
`detect_edge_inscriptions` / `match_shishi_blocks` / `calc_text_density` / `AREA_SCALE`），
一个字都没改、也没复制算法。本脚本只重写两处**编排**差异（这两处不能沿用 `process_page`）：
  1. 影像命名：照 §4.1 D-4② 落 `faces/<book_key>/p<页4位>_<idx2位>.webp`（`process_page` 用「OCR 文本或
     `p<页>_<序号>`」命名，**同名重跑会换路径**，不满足 §4.2.2 的稳定命名，故不能沿用）；
  2. OCR 调用：`process_page` 走 `processor._get_ocr()` 的**全局单例**（§5.2 明确要求改为「每 worker 一实例」），
     且需支持 doc 预处理开关与 `cpu_threads` 上限——故 worker 自建实例（进程内单例）。
  * 释文文本抽取逻辑与 `processor.ocr_text` **逐行同构**（含 PaddleOCR 3.x 的 `.json["res"]["rec_texts"]` 兜底）。
  * **边款**：仍照样检测（其结果参与 `exclude_mask`，会改变释文块匹配 ⇒ 不检测就不是同一份解析），
    但 1b-i **不落边款影像**（faces 交付影像口径只定义印面；见 `REPORT_1b-i.md` 未完成项）。

**影像命名 ＋ 颜色校正（2026-10-11 新增；口径真源 `docs/image-naming-draft-v0.1.md`
＋ `docs/image-color-tiff-draft-v0.1.md`）**：每枚裁图经 **V3 校正**
（`colorcal.correct_image_v3`）后写 `output/books/<目录键>/P<页>-C<列>-R<行>.tiff`（RGB 8-bit ＋
Deflate）；`(C,R)` 用 `naming.assign_cr` 算、目录键用 `naming.dir_key_for`。

**原始切片 `-O`（2026-10-11 新增；口径真源 `docs/image-original-crop-draft-v0.1.md` §2）**：
每次裁切**额外**写同目录 `P<页>-C<列>-R<行>-O.tiff` ＝ **未做颜色处理的原片**
（同一 400 dpi 渲染、同一 bbox、同容器）；命名由 `naming.name_for_original` 派生、
**幂等按解码像素判**（`write_tiff_idempotent_pixels`）；**返回值不新增字段**。
**webp 退场（Kevin 2026-10-11 裁定「本地文件一律不再保存 webp」）**：本 worker **不再新写任何 webp**
—— 旧 `output/faces/<book_key>/p<页4位>_<序2位>.webp` **不再写**、新命名目录里的同名 `.webp` 也**不再写**；
该行影像的产物 ＝ **TIFF ×2**（校正件 `P…-C…-R….tiff` ＋ 原始切片 `P…-C…-R…-O.tiff`）。
返回值的 `img_path` **仍是旧 webp 相对路径**（该列口径一字不改，
E6 的兼容回退靠它），`col`/`row`/`img_path_tiff` 照旧返回给池侧写库（**worker 仍不写库**）。
两块地基按文件路径加载（`feicui/app.py` 会遮蔽 `server/app` 包名）。

通信协议（stdin / stdout，**一行一个 JSON**）：
  请求  `{"cmd":"process_chunk", "task_id", "pdf_path", "book_key", "template", "pages":[…],
          "faces_dir", "rel_root", "render_dpi"?}` / `{"cmd":"ping"}` / `{"cmd":"shutdown"}`
  应答  `{"type":"ready", …}` / `{"type":"page", "task_id", "page", "ok", …}` /
        `{"type":"chunk_done", "task_id", …}` / `{"type":"pong", …}` / `{"type":"bye"}`
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------- 启动纪律
ROOT = Path(os.environ.get("FEICUI_ROOT") or os.getcwd()).resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # processor 的相对路径（output/…、config/…）全部以 feicui/ 为 cwd

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
import processor  # noqa: E402  —— 同一份解析实现（§1.2 I-1）
from PIL import Image  # noqa: E402  —— 新增双份的 TIFF（RGB 8-bit ＋ Deflate）落盘

DOC_PREPROCESS = str(os.environ.get("FEICUI_DOC_PREPROCESS", "1")).lower() not in {"0", "false", "no", "off"}
CPU_THREADS = int(os.environ.get("FEICUI_CPU_THREADS", "2"))  # 派单口径：不超过 2
FACES_DIR = Path(os.environ.get("FEICUI_FACES_DIR") or (ROOT / "output" / "faces")).resolve()
REL_ROOT = Path(os.environ.get("FEICUI_ROOT") or ROOT).resolve()
# 新增双份（P-C-R 命名目录）落点根：`output/books/<目录键>/`（口径真源 docs/image-naming-draft-v0.1.md）
BOOKS_DIR = Path(os.environ.get("FEICUI_BOOKS_DIR") or (ROOT / "output" / "books")).resolve()
_OCR = None


# --------------------------------------------------------------------------- 命名 / 颜色校正地基
# ★ `feicui/app.py`（Streamlit 应用）会**遮蔽** `server/app` 的包名 ⇒ 一律**按文件路径**加载这两块
#   地基（见技能 feicui-ingest「硬约束」/ docs 同名提示），不触发 `import app`、不拉起接口层依赖。
def _load_by_path(mod_name: str, rel: str):
    spec = importlib.util.spec_from_file_location(mod_name, str(ROOT / rel))
    assert spec is not None and spec.loader is not None, f"无法加载 {rel}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


naming = _load_by_path("feicui_naming", "server/app/naming.py")       # assign_cr / name_for / dir_key_for
colorcal = _load_by_path("feicui_colorcal", "server/app/colorcal.py")  # correct_image_v3（默认口径）

try:  # 目录键表（加法文件 config/book_dir_keys.json）；缺失时不让 worker 起不来，回落规范化书名
    DIR_KEYS = naming.load_dir_keys()
except Exception as _exc:  # pragma: no cover
    print(f"[worker] 目录键表加载失败，回落规范化书名：{_exc!r}", file=sys.stderr, flush=True)
    DIR_KEYS = {"books": {}}


def log(msg: str) -> None:
    """诊断信息一律走 **stderr**（stdout 是协议通道，绝不可混入非 JSON 行）。"""
    print(f"[worker {os.getpid()}] {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- OCR（进程内单例）
def get_ocr(name: str = "default"):
    """**每 worker 一实例**（§5.2：全局单例在多进程下不成立）；启动即预热。

    * `name="doc_on"`：与 `processor._get_ocr()` **同参**（`use_angle_cls=False, lang="ch"`，
      doc 预处理**保持 PaddleOCR 默认＝开**）⇒ **默认行为＝现状行为**（不得静默改默认）；
    * `name="doc_off"`：额外显式关 doc 预处理（spike 实测 1.78×），**会改变识别文本**
      ⇒ 仅在 `FEICUI_DOC_PREPROCESS=0` 时使用（精度未定论，见 `REPORT_1b-i.md`）。
    * 两种形态都带 `cpu_threads<=2`（派单口径 w=4 × ct≤2，防线程超订）。
    """
    global _OCR
    if _OCR is None:
        kwargs = dict(use_angle_cls=False, lang="ch", cpu_threads=CPU_THREADS)
        if name == "doc_off":
            kwargs.update(use_doc_orientation_classify=False, use_doc_unwarping=False)
        _OCR = processor.PaddleOCR(**kwargs)
    return _OCR


def ocr_text(crop) -> str:
    """与 `processor.ocr_text` 同构的抽取逻辑（差异只在「实例来自本模块」与 predict 的 doc 开关）。"""
    ocr = get_ocr("doc_off" if not DOC_PREPROCESS else "doc_on")
    if DOC_PREPROCESS:
        res = ocr.predict(crop)  # 现状行为：不传额外开关
    else:
        # 实测口径（spike）)：predict 阶段传入任一 False ⇒ 整段 doc 预处理关闭
        res = ocr.predict(crop, use_doc_orientation_classify=False, use_doc_unwarping=False)
    texts = []
    if res:
        for item in res:
            rec_texts = getattr(item, "rec_texts", None)
            if rec_texts is None:
                try:  # PaddleOCR 3.x：字段挂在 .json["res"] 下
                    rec_texts = (item.json.get("res") or {}).get("rec_texts")
                except Exception:
                    rec_texts = None
            if rec_texts:
                if isinstance(rec_texts, list):
                    texts.extend(rec_texts)
                else:
                    texts.append(str(rec_texts))
    return "".join(texts)


# --------------------------------------------------------------------------- 影像（幂等写）
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_image_idempotent(path: Path, data: bytes) -> dict:
    """影像级幂等（§2.4：内容 `sha256` 相同 ⇒ **不重写、不另存**）。

    内容一致 ⇒ 直接复用（`written=false`）；否则**临时文件 + fsync + 原子替换**
    （§4.3：先影像后 DB 行；崩溃只可能留孤儿影像，由重跑覆盖、不产生重复）。
    """
    digest = hashlib.sha256(data).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        if _sha256_file(path) == digest:
            return {"sha256": digest, "bytes": len(data), "written": False, "reused": True}
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return {"sha256": digest, "bytes": len(data), "written": True, "reused": False}


def encode_webp(crop) -> bytes:
    """WebP 编码（cv2，q95）——**本函数已不在印面解析线使用**（webp 退场：`process_page` 只出 TIFF）。

    **保留不删**：`server/app/square_runner.py`（E7 工具端点 `square-crop`）**逐字复用**它作为
    工具响应的 WebP 编码口径（见该文件 §12「复用 `worker.feicui_worker.encode_webp`」），
    删掉会把工具端点打断。本单对它的默认行为**一字未动**。
    """
    ok, buf = cv2.imencode(".webp", crop, [int(cv2.IMWRITE_WEBP_QUALITY), 95])
    if not ok:
        raise RuntimeError("webp 编码失败")
    return bytes(buf.tobytes())


def rel_path(path: Path) -> str:
    """DB 里存的 `img_path`：相对 `feicui/`（§4.2.1），**不写绝对路径**。"""
    try:
        return os.path.relpath(path.resolve(), REL_ROOT)
    except ValueError:
        return str(path)


# ★ O 件编码（Kevin 2026-10-11 裁定「O 件用 TIFF 编码」＋ Zang 实测裁决）：
#   **Deflate ＋ Predictor=2（水平差分）**。实测：deflate 均 391.9 KB → +Predictor 均 289.7 KB
#   ＝ 73.9%（省 26.1%）；lzw 反 137.5%；**三种编码解码像素与原片逐像素相等均成立**。
#   ⇒ O 件一律以此编码写出（旧编码 O 件由幂等判据「解码像素相等 ∧ 容器合要求」自动升级重写）。
#   ★ 校正件 `P-C-R.tiff` 的编码与字节**一字不动**（`encode_tiff` 默认 `predictor=None` ⇒ 逐字节不变）。
O_TIFF_PREDICTOR = 2
TIFF_TAG_PREDICTOR = 317
TIFF_TAG_COMPRESSION = 259


def encode_tiff(rgb, predictor: int | None = None) -> bytes:
    """RGB 8-bit ＋ Deflate（无损）TIFF 字节 —— 家法容器（与印章线 / xiai 影像库同）。

    `rgb` 须为 `(H, W, 3)` 0–255 RGB（`uint8`；**不是 BGR**）。
    `predictor=None`（**校正件路径**）⇒ 逐字节与既往一致（红线①）；`predictor=O_TIFF_PREDICTOR`
    （**O 件路径**）⇒ 追加 `tiffinfo={317: 2}`（Deflate ＋ 水平差分 Predictor）。
    """
    buf = io.BytesIO()
    arr = np.ascontiguousarray(rgb)
    if predictor:
        Image.fromarray(arr).save(
            buf, format="TIFF", compression="tiff_deflate",
            tiffinfo={TIFF_TAG_PREDICTOR: int(predictor)})
    else:
        Image.fromarray(arr).save(buf, format="TIFF", compression="tiff_deflate")
    return buf.getvalue()


def write_tiff_idempotent_pixels(path: Path, rgb, predictor: int | None = None) -> dict:
    """**按解码像素**幂等写 TIFF（口径件 `docs/image-original-crop-draft-v0.1.md` §2「幂等」）。

    判据 **不得按文件 sha256**（Pillow `tiff_deflate` 在大图上逐字节非确定）：
    已存在且**解码像素逐像素相等** **且**（`predictor is None` 或 **容器合要求**：
    `Compression=8` ∧ `Predictor==predictor`）⇒ **不重写、不动字节**；否则写入。
    `predictor=None`（**校正件路径**）⇒ 只按解码像素判、不查 / 不改编码 ⇒ 校正件字节一字不动。
    `predictor=O_TIFF_PREDICTOR`（**O 件路径**）⇒ 旧编码 O 件被自动升级重写为新编码。
    返回 `{"written": bool, "bytes": int}`。
    """
    if path.is_file():
        try:
            with Image.open(path) as im:
                ondisk = np.asarray(im)
                tag_pred = im.tag_v2.get(TIFF_TAG_PREDICTOR)
                tag_comp = im.tag_v2.get(TIFF_TAG_COMPRESSION)
            container_ok = (
                predictor is None
                or (tag_pred == predictor and tag_comp == 8)
            )
            if container_ok and np.array_equal(ondisk, rgb):
                return {"written": False, "bytes": path.stat().st_size}
        except Exception:
            pass  # 解不开 / 像素不一致 ⇒ 落到下面覆盖写（不静默）
    data = encode_tiff(rgb, predictor)
    write_image_idempotent(path, data)   # 复用「临时文件 + fsync + 原子替换」（先影像后 DB 行）
    return {"written": True, "bytes": len(data)}


# --------------------------------------------------------------------------- 单页处理
def process_page(doc, page_no: int, template: dict, book_key: str, pdf_name: str | None = None) -> dict:
    """处理**一页**（`page_no` 为 1-based 页号，↔ `stamps.page`）。编排同 `processor.process_page`。

    返回 `{detected, ocr_empty, items:[{idx,text,img_path,img_sha256,img_bytes,
    col,row,img_path_tiff,x1..y2}]}`。

    **影像（2026-10-11 webp 退场后）**：每枚裁图经 **V3 校正**（`colorcal.correct_image_v3`）后写
    `output/books/<目录键>/P<页>-C<列>-R<行>.tiff`（RGB 8-bit ＋ Deflate）——**校正件**；
    **并额外**写同目录 `P<页>-C<列>-R<行>-O.tiff` ＝ **原始切片**（400 dpi 渲染后按同一 bbox
    原样裁出、**不做任何颜色处理**的原片；口径真源 `docs/image-original-crop-draft-v0.1.md` §2）。
    **不再写任何 webp**（旧 `faces/<book_key>/pNNNN_II.webp` 与命名目录同名 `.webp` 均不再写）。
    `(C,R)` 由 `naming.assign_cr` 算、目录键由 `naming.dir_key_for`（未登记回落规范化书名）。
    **worker 只落盘、不写库**——`col`/`row`/`img_path_tiff` 随返回值交给池侧写库；
    **返回值不因 O 而新增字段**（O 路径由命名规则派生）。
    """
    page = doc[page_no - 1]
    img = processor.render_page(page)
    H, W = img.shape[:2]

    hsv_low = template["hsv_low"]
    hsv_high = template["hsv_high"]
    min_area = template["min_area"] * processor.AREA_SCALE
    pad_ratio = template.get("pad_ratio", 0.15)

    stamp_candidates = processor.detect_stamp_regions(img, hsv_low, hsv_high, min_area, pad_ratio)
    stamp_candidates.sort(key=lambda c: c["bbox"][0])  # 从左到右（idx 顺序口径）

    # 影像命名 P-C-R（口径真源 `docs/image-naming-draft-v0.1.md`）：列/行由页内 bbox 推导，
    # 与 `stamp_idx` 同序；页内 (C,R) 唯一（构造上恒真，撞名机械判负）。
    cr = naming.assign_cr([c["bbox"] for c in stamp_candidates])
    naming.assert_page_unique(cr)
    # 目录键：ISBN 优先、无 ISBN 落中文书名、未登记回落规范化书名（标 fallback_unregistered）
    dir_key = naming.dir_key_for(pdf_name, DIR_KEYS) if pdf_name else book_key
    books_out = BOOKS_DIR / dir_key

    # 边款参与 exclude_mask ⇒ 影响释文块匹配 ⇒ 必须照样检测（1b-i 不落边款影像）
    edge_candidates = []
    if template.get("edge_enabled", True) and stamp_candidates:
        avg_stamp_area = float(np.mean([c["area"] for c in stamp_candidates]))
        edge_candidates = processor.detect_edge_inscriptions(img, avg_stamp_area)

    exclude_mask = np.zeros((H, W), np.uint8)
    for c in stamp_candidates:
        x1, y1, x2, y2 = [int(v) for v in c["bbox"]]
        exclude_mask[max(0, y1):y2, max(0, x1):x2] = 255
    for e in edge_candidates:
        x1, y1, x2, y2 = [int(v) for v in e["bbox"]]
        exclude_mask[max(0, y1):y2, max(0, x1):x2] = 255
    shishi_map = processor.match_shishi_blocks(
        img, [c["bbox"] for c in stamp_candidates], exclude_mask=exclude_mask
    )

    out_dir = FACES_DIR / book_key
    rel_dx, rel_dy, rel_w, rel_h = template["text_offset"]
    density_min = template["density_min"]
    density_max = template["density_max"]

    items: list[dict] = []
    ocr_empty = 0
    for stamp_idx, stamp in enumerate(stamp_candidates):
        sx1, sy1, sx2, sy2 = [int(v) for v in stamp["bbox"]]
        sx1, sy1 = max(0, sx1), max(0, sy1)
        sx2, sy2 = min(W, sx2), min(H, sy2)
        stamp_crop = img[sy1:sy2, sx1:sx2]

        text_bbox = shishi_map.get(stamp_idx)
        if text_bbox is not None:
            tx1, ty1, tx2_, ty2_ = [int(v) for v in text_bbox]
            tx1, ty1 = max(0, tx1), max(0, ty1)
            tx2_, ty2_ = min(W, tx2_), min(H, ty2_)
        else:  # 兜底：模板固定偏移（与 process_page 同）
            tx1 = int(sx1 + rel_dx)
            ty1 = int(sy1 + rel_dy)
            tx2_ = int(tx1 + rel_w)
            ty2_ = int(ty1 + rel_h)
            tx1, ty1 = max(0, tx1), max(0, ty1)
            tx2_, ty2_ = min(W, tx2_), min(H, ty2_)

        text_crop = img[ty1:ty2_, tx1:tx2_]
        density = processor.calc_text_density(text_crop)

        stamp_text = ""
        if density_min < density < density_max:
            stamp_text = ocr_text(text_crop)
            if not stamp_text.strip():
                ocr_empty += 1

        # ---- 影像产物：**只出 TIFF**（`output/books/<目录键>/P<页>-C<列>-R<行>.tiff`，V3 校正后）。
        #      **webp 退场**（Kevin 2026-10-11 裁定「本地文件一律不再保存 webp」）：本函数**不再新写任何
        #      webp** —— ① 旧路径 `output/faces/<book_key>/pNNNN_II.webp` 不再写（下面只算路径、不写盘）；
        #      ② 新命名目录里也不再写同名 `.webp`。
        #      返回值口径：`img_path` 仍回**旧 webp 相对路径**（该列口径一字不改、既有行的值不受影响）；
        #      新行的影像真身在 `img_path_tiff`（E6 首选它）。`img_sha256`/`img_bytes` 取**实际落盘的 TIFF**。
        img_path = out_dir / f"p{page_no:04d}_{stamp_idx:02d}.webp"   # 仅供返回值（**不落盘**）
        c, r = cr[stamp_idx]
        # 原片（RGB）—— 原始切片 O 与 V3 校正件**同一像素、同一几何**（同 bbox / 同渲染倍率）
        stamp_rgb = np.ascontiguousarray(cv2.cvtColor(stamp_crop, cv2.COLOR_BGR2RGB))
        corrected, _cc = colorcal.correct_image_v3(stamp_rgb)             # V3 默认口径
        tiff_path = books_out / naming.name_for(page_no, c, r)            # 默认 ext=".tiff"
        info = write_image_idempotent(tiff_path, encode_tiff(corrected))
        # ★ 原始切片 `-O`（2026-10-11 新增；口径件 `docs/image-original-crop-draft-v0.1.md`）：
        #   **未做颜色处理的原片**，落同目录 `P<页>-C<列>-R<行>-O.tiff`（TIFF RGB 8-bit ＋ Deflate）；
        #   幂等**按解码像素**判（不得按文件 sha256）。**返回值口径不变**（O 路径由命名派生、不新增字段）。
        orig_path = books_out / naming.name_for_original(page_no, c, r)
        write_tiff_idempotent_pixels(orig_path, stamp_rgb, predictor=O_TIFF_PREDICTOR)

        items.append(
            {
                "idx": stamp_idx,
                "text": stamp_text,
                "img_path": rel_path(img_path),
                "img_sha256": info["sha256"],
                "img_bytes": info["bytes"],
                "img_written": info["written"],
                "col": c,
                "row": r,
                "img_path_tiff": rel_path(tiff_path),
                "x1": sx1,
                "y1": sy1,
                "x2": sx2,
                "y2": sy2,
            }
        )

    return {"detected": len(stamp_candidates), "ocr_empty": ocr_empty, "items": items}


# --------------------------------------------------------------------------- 协议主循环
def reply(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_chunk(req: dict) -> None:
    task_id = req["task_id"]
    t0 = time.time()
    # `pdf_name` ＝ PDF 文件名（与 `config/templates.json` / `book_dir_keys.json` 同源，逐字含扩展名）
    pdf_name = os.path.basename(str(req["pdf_path"]).rstrip("/"))
    doc = pymupdf.open(req["pdf_path"])
    try:
        for page_no in req["pages"]:
            p0 = time.time()
            try:
                out = process_page(doc, int(page_no), req["template"], req["book_key"], pdf_name)
                reply(
                    {
                        "type": "page",
                        "task_id": task_id,
                        "page": int(page_no),
                        "ok": True,
                        "detected": out["detected"],
                        "ocr_empty": out["ocr_empty"],
                        "items": out["items"],
                        "elapsed_ms": int((time.time() - p0) * 1000),
                    }
                )
            except Exception as exc:  # 页级失败不影响其余页（池侧记 FAILED → 可续跑）
                log(f"page {page_no} 失败：{exc!r}")
                reply(
                    {
                        "type": "page",
                        "task_id": task_id,
                        "page": int(page_no),
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_ms": int((time.time() - p0) * 1000),
                    }
                )
    finally:
        doc.close()
    reply({"type": "chunk_done", "task_id": task_id, "pages": req["pages"], "elapsed_ms": int((time.time() - t0) * 1000)})


def ready_banner() -> dict:
    import paddleocr

    get_ocr("doc_off" if not DOC_PREPROCESS else "doc_on")  # 启动即预热（§5.2）
    return {
        "type": "ready",
        "pid": os.getpid(),
        "python": sys.version.split()[0],
        "exe": sys.executable,
        "cwd": os.getcwd(),
        "pymupdf": pymupdf.__doc__.strip().split()[1] if pymupdf.__doc__ else "?",
        "paddleocr": getattr(paddleocr, "__version__", "?"),
        "doc_preprocess": DOC_PREPROCESS,
        "cpu_threads": CPU_THREADS,
        "faces_dir": str(FACES_DIR),
        "books_dir": str(BOOKS_DIR),
    }


def main() -> int:
    reply(ready_banner())
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as exc:
            log(f"非法请求行：{exc!r}")
            continue
        cmd = req.get("cmd")
        if cmd == "process_chunk":
            handle_chunk(req)
        elif cmd == "ping":
            reply({"type": "pong", "pid": os.getpid(), "faces_dir": str(FACES_DIR)})
        elif cmd == "shutdown":
            reply({"type": "bye", "pid": os.getpid()})
            return 0
        else:
            log(f"未知命令：{cmd!r}")
    log("stdin 关闭 ⇒ 退出（池已死）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
