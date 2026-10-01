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

通信协议（stdin / stdout，**一行一个 JSON**）：
  请求  `{"cmd":"process_chunk", "task_id", "pdf_path", "book_key", "template", "pages":[…],
          "faces_dir", "rel_root", "render_dpi"?}` / `{"cmd":"ping"}` / `{"cmd":"shutdown"}`
  应答  `{"type":"ready", …}` / `{"type":"page", "task_id", "page", "ok", …}` /
        `{"type":"chunk_done", "task_id", …}` / `{"type":"pong", …}` / `{"type":"bye"}`
"""
from __future__ import annotations

import hashlib
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

DOC_PREPROCESS = str(os.environ.get("FEICUI_DOC_PREPROCESS", "1")).lower() not in {"0", "false", "no", "off"}
CPU_THREADS = int(os.environ.get("FEICUI_CPU_THREADS", "2"))  # 派单口径：不超过 2
FACES_DIR = Path(os.environ.get("FEICUI_FACES_DIR") or (ROOT / "output" / "faces")).resolve()
REL_ROOT = Path(os.environ.get("FEICUI_ROOT") or ROOT).resolve()
_OCR = None


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


# --------------------------------------------------------------------------- 单页处理
def process_page(doc, page_no: int, template: dict, book_key: str) -> dict:
    """处理**一页**（`page_no` 为 1-based 页号，↔ `stamps.page`）。编排同 `processor.process_page`。

    返回 `{detected, ocr_empty, items:[{idx,text,img_path,img_sha256,img_bytes,x1..y2}]}`。
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

        img_path = out_dir / f"p{page_no:04d}_{stamp_idx:02d}.webp"
        info = write_image_idempotent(img_path, encode_webp(stamp_crop))

        items.append(
            {
                "idx": stamp_idx,
                "text": stamp_text,
                "img_path": rel_path(img_path),
                "img_sha256": info["sha256"],
                "img_bytes": info["bytes"],
                "img_written": info["written"],
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
    doc = pymupdf.open(req["pdf_path"])
    try:
        for page_no in req["pages"]:
            p0 = time.time()
            try:
                out = process_page(doc, int(page_no), req["template"], req["book_key"])
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
