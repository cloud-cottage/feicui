import pymupdf
import cv2
import numpy as np
import json
import os
import sqlite3
from paddleocr import PaddleOCR

import re

def _sanitize_filename(name):
    """清理文件名中的非法字符"""
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name if name else "unknown"

# 延迟初始化 OCR，仅在批量解析时加载模型
_ocr_instance = None

def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = PaddleOCR(use_angle_cls=False, lang="ch")
    return _ocr_instance

def init_db():
    conn = sqlite3.connect("yinpu.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stamps (
        id INTEGER PRIMARY KEY,
        pdf_name TEXT,
        page INTEGER,
        idx INTEGER,
        text TEXT,
        img_path TEXT,
        x1 REAL, y1 REAL, x2 REAL, y2 REAL
    )''')
    conn.commit()
    conn.close()

def load_templates():
    os.makedirs("config", exist_ok=True)
    template_path = "config/templates.json"
    if not os.path.exists(template_path):
        return {}
    with open(template_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_template(pdf_name, template):
    tmpl = load_templates()
    tmpl[pdf_name] = template
    with open("config/templates.json", "w", encoding="utf-8") as f:
        json.dump(tmpl, f, ensure_ascii=False, indent=2)

# ============================================================
# 渲染分辨率：为最大化保留 PDF 细节，统一用较高 DPI 渲染页面。
# BASE_DPI 是模板阈值(如 min_area、文字密度)标定时的基准分辨率(2x=144dpi)，
# 提高渲染分辨率后所有像素级阈值按面积比例(线尺寸平方)等比换算。
# ============================================================
RENDER_DPI = 400.0
BASE_DPI = 144.0  # 旧版模板用 2x(=144dpi) 渲染标定
AREA_SCALE = (RENDER_DPI / BASE_DPI) ** 2


def render_page(page: "pymupdf.Page") -> np.ndarray:
    """按高分辨率渲染 PDF 页面，返回 BGR 图像。"""
    scale = RENDER_DPI / 72.0
    mat = pymupdf.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img


def _pad_bbox(x1, y1, x2, y2, pad_x, pad_y, W, H):
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(W, x2 + pad_x)
    y2 = min(H, y2 + pad_y)
    return x1, y1, x2, y2


def detect_stamp_regions(page_img: np.ndarray, hsv_low, hsv_high, min_area, pad_ratio=0.15):
    """
    检测红色印章区域，bbox 外扩 pad_ratio 确保红色内容完全在框内。
    min_area 为按当前渲染分辨率换算后的像素阈值。
    """
    hsv = cv2.cvtColor(page_img, cv2.COLOR_BGR2HSV)
    mask_red = cv2.inRange(hsv, np.array(hsv_low), np.array(hsv_high))
    kernel = np.ones((3, 3), np.uint8)
    mask_red = cv2.morphologyEx(mask_red, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = page_img.shape[:2]
    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        ratio = w / h
        if 0.6 < ratio < 1.6:
            pad_x = int(w * pad_ratio)
            pad_y = int(h * pad_ratio)
            x1, y1, x2, y2 = _pad_bbox(x, y, x + w, y + h, pad_x, pad_y, W, H)
            candidates.append({"bbox": (x1, y1, x2, y2), "area": area, "aspect": ratio})
    return candidates


def _area_bbox_ratio(bbox):
    x1, y1, x2, y2 = bbox
    return float(max((x2 - x1) * (y2 - y1), 1))


def detect_edge_inscriptions(page_img: np.ndarray, ref_stamp_area: float, ratio_lo=2.0,
                             ratio_hi=10.0, dark_thresh=80, dark_ratio_min=0.35):
    """
    检测边款：以黑色为主、面积约为印面(2~10)倍的深色色块。
    - 排除白底黑字的释文（深色占比低）与整页黑字（远大于 10 倍印面）。
    返回结构化候选列表。
    """
    if ref_stamp_area <= 0:
        return []
    gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)
    _, dark_mask = cv2.threshold(gray, dark_thresh, 255, cv2.THRESH_BINARY_INV)
    k = 5
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_CLOSE, np.ones((max(k, 3), max(k, 3)), np.uint8))
    dark_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = page_img.shape[:2]
    candidates = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = cv2.contourArea(cnt)
        # 面积约束：约为印面的 2~10 倍，可排除整页/整段大块
        if area < ref_stamp_area * ratio_lo or area > ref_stamp_area * ratio_hi:
            continue
        crop = dark_mask[y:y + h, x:x + w]
        dark_ratio = float(cv2.countNonZero(crop)) / max(w * h, 1)
        if dark_ratio < dark_ratio_min:
            continue
        ratio = w / h
        if 0.2 < ratio < 5.0:
            candidates.append({
                "bbox": (x, y, x + w, y + h),
                "area": area,
                "aspect": ratio,
                "dark_ratio": dark_ratio,
            })
    return candidates


# ------------------------------------------------------------
# 释文自动识别
# ------------------------------------------------------------
LEFT, RIGHT, UP, DOWN = "left", "right", "up", "down"


def _black_text_mask(gray, exclude_mask=None, dark_thresh=150, close_k=5):
    """白底黑字黑字像素 mask（深色像素），可抠掉已确认区域。"""
    _, bm = cv2.threshold(gray, dark_thresh, 255, cv2.THRESH_BINARY_INV)
    if exclude_mask is not None and exclude_mask.any():
        bm[exclude_mask > 0] = 0
    bm = cv2.morphologyEx(bm, cv2.MORPH_CLOSE, np.ones((close_k, close_k), np.uint8))
    return bm


def _band_text_region(bm, stamp_bbox, side, H, W, span_factor=1.3, ink_min=250):
    """
    在印面某一侧紧邻的受限搜索框内，把文字聚合为一个释文块。
    搜索框为印面外扩 span，因此释文 box 天然贴近印面、不会误含远处正文。
    返回 {"bbox": (x1,y1,x2,y2), "ink"} 或 None。
    """
    sx1, sy1, sx2, sy2 = stamp_bbox
    sw, sh = sx2 - sx1, sy2 - sy1
    span = int(max(sw, sh) * span_factor)

    if side in (LEFT, RIGHT):
        r0x = max(0, sx1 - span) if side == LEFT else sx2
        r1x = sx1 if side == LEFT else min(W, sx2 + span)
        r0y, r1y = max(0, sy1 - span), min(H, sy2 + span)
    else:
        r0y = max(0, sy1 - span) if side == UP else sy2
        r1y = sy1 if side == UP else min(H, sy2 + span)
        r0x, r1x = max(0, sx1 - span), min(W, sx2 + span)
    if r1x <= r0x or r1y <= r0y:
        return None

    mask = bm[r0y:r1y, r0x:r1x]
    ink = int(cv2.countNonZero(mask))
    if ink < ink_min:
        return None
    rows = np.where(mask.sum(axis=1) > 0)[0]
    cols = np.where(mask.sum(axis=0) > 0)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    bbox = (r0x + cols[0], r0y + rows[0], r0x + cols[-1] + 1, r0y + rows[-1] + 1)
    return {"bbox": bbox, "ink": ink}


def _rect_gap(a, b):
    """两矩形之间的最近距离（重叠为 0）。"""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = max(0, max(bx1 - ax2, ax1 - bx2))
    dy = max(0, max(by1 - ay2, ay1 - by2))
    return float((dx * dx + dy * dy) ** 0.5)


def match_shishi_blocks(page_img, stamp_bboxes, exclude_mask=None):
    """
    自动为每个印章匹配释文文字块。
    释文应是"白底黑字"且紧邻印面（空间距离小）的紧凑文字段；
    与印面相距过远或尺寸过大的区域视为正文，判定为无释文(None)，
    从而避免把无释文的书（如部分印谱）里的正文误认为释文。
    返回 {stamp_index: bbox 或 None}。
    """
    if not stamp_bboxes:
        return {}
    gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape[:2]
    bm = _black_text_mask(gray, exclude_mask=exclude_mask)

    result = {}
    for idx, sb in enumerate(stamp_bboxes):
        sw, sh = sb[2] - sb[0], sb[3] - sb[1]
        m = max(sw, sh)
        best = None
        best_score = None
        for side in (LEFT, RIGHT, UP, DOWN):
            r = _band_text_region(bm, sb, side, H, W)
            if r is None:
                continue
            bw = r["bbox"][2] - r["bbox"][0]
            bh = r["bbox"][3] - r["bbox"][1]
            # 尺寸相称：释文不该远大于印面（防整段正文）
            if bw > sw * 5 or bh > sh * 5:
                continue
            gap = _rect_gap(r["bbox"], sb)
            # 紧邻：释文须贴近印面，太远视为正文
            if gap > m:
                continue
            # 越近越好、文字量适中者优先
            size_ok = (sw * 0.25 <= bw <= sw * 3) or (sh * 0.25 <= bh <= sh * 3)
            score = (round(-gap), r["ink"] if size_ok else -1)
            if best is None or score > best_score:
                best = r
                best_score = score
        result[idx] = None if best is None else best["bbox"]
    return result

def calc_text_density(crop_img):
    if crop_img.size == 0:
        return 0
    gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
    _, bin_img = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)
    total = bin_img.shape[0] * bin_img.shape[1]
    text_pixels = np.count_nonzero(bin_img)
    return text_pixels / total

def ocr_text(crop_img):
    ocr = _get_ocr()
    res = ocr.predict(crop_img)
    texts = []
    if res:
        for item in res:
            # 新 API: OCRResult 对象，rec_texts 是识别出的文字列表
            rec_texts = getattr(item, "rec_texts", None)
            if rec_texts is None:
                # PaddleOCR 3.x: OCRResult 未把字段挂成属性，字段位于 .json["res"]
                try:
                    rec_texts = (item.json.get("res") or {}).get("rec_texts")
                except Exception:
                    rec_texts = None
            if rec_texts:
                if isinstance(rec_texts, list):
                    texts.extend(rec_texts)
                else:
                    texts.append(str(rec_texts))
    return "".join(texts)

def process_page(doc, page_idx, pdf_name, template):
    """
    处理单页：检测印章 + 边款，分别裁剪保存。
    输出目录结构：
      output/pairs/p{页码}_{序号}/stamp.png   — 印面
      output/pairs/p{页码}_{序号}/edge.png    — 边款（如有）
    """
    page = doc[page_idx]
    img = render_page(page)
    H, W = img.shape[:2]

    hsv_low = template["hsv_low"]
    hsv_high = template["hsv_high"]
    min_area = template["min_area"] * AREA_SCALE  # 按渲染分辨率等比换算
    pad_ratio = template.get("pad_ratio", 0.15)

    # 检测印章
    stamp_candidates = detect_stamp_regions(img, hsv_low, hsv_high, min_area, pad_ratio)
    stamp_candidates.sort(key=lambda c: c["bbox"][0])  # 从左到右

    # 检测边款（面积约为印面的 2~10 倍，黑色为主）
    edge_candidates = []
    edge_enabled = template.get("edge_enabled", True)
    if edge_enabled and stamp_candidates:
        avg_stamp_area = float(np.mean([c["area"] for c in stamp_candidates]))
        edge_candidates = detect_edge_inscriptions(img, avg_stamp_area)
        edge_candidates.sort(key=lambda c: c["bbox"][1])  # 从上到下

    # 释文自动匹配：排除 印章 + 边款 区域后，在旁近识别白底黑字文字块
    exclude_mask = np.zeros((H, W), np.uint8)
    for c in stamp_candidates:
        x1, y1, x2, y2 = [int(v) for v in c["bbox"]]
        exclude_mask[max(0, y1):y2, max(0, x1):x2] = 255
    for e in edge_candidates:
        x1, y1, x2, y2 = [int(v) for v in e["bbox"]]
        exclude_mask[max(0, y1):y2, max(0, x1):x2] = 255
    shishi_map = match_shishi_blocks(img, [c["bbox"] for c in stamp_candidates],
                                     exclude_mask=exclude_mask)

    book_name = os.path.splitext(pdf_name)[0]
    out_dir = os.path.join("output", book_name)
    os.makedirs(out_dir, exist_ok=True)

    results = []

    rel_dx, rel_dy, rel_w, rel_h = template["text_offset"]
    density_min = template["density_min"]
    density_max = template["density_max"]

    for stamp_idx, stamp in enumerate(stamp_candidates):
        sx1, sy1, sx2, sy2 = [int(v) for v in stamp["bbox"]]
        sx1, sy1 = max(0, sx1), max(0, sy1)
        sx2, sy2 = min(W, sx2), min(H, sy2)
        stamp_crop = img[sy1:sy2, sx1:sx2]  # 高分辨率裁剪，保留 PDF 细节

        # 查找对应的边款（最接近的深色块）
        edge_crop = None
        edge_bbox = None
        if edge_candidates:
            stamp_cx = (sx1 + sx2) / 2
            stamp_cy = (sy1 + sy2) / 2
            best_edge = None
            best_dist = float("inf")
            for ec in edge_candidates:
                ex1, ey1, ex2, ey2 = ec["bbox"]
                ecx = (ex1 + ex2) / 2
                ecy = (ey1 + ey2) / 2
                dist = ((stamp_cx - ecx) ** 2 + (stamp_cy - ecy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_edge = ec
            if best_edge:
                ex1, ey1, ex2, ey2 = [int(v) for v in best_edge["bbox"]]
                ex1, ey1 = max(0, ex1), max(0, ey1)
                ex2, ey2 = min(W, ex2), min(H, ey2)
                edge_crop = img[ey1:ey2, ex1:ex2]
                edge_bbox = (ex1, ey1, ex2, ey2)

        # 释文区域：优先用自动识别到的文字块
        text_bbox = shishi_map.get(stamp_idx)
        if text_bbox is not None:
            tx1, ty1, tx2_, ty2_ = [int(v) for v in text_bbox]
            tx1, ty1 = max(0, tx1), max(0, ty1)
            tx2_, ty2_ = min(W, tx2_), min(H, ty2_)
        else:  # 兜底：使用模板固定偏移
            tx1 = int(sx1 + rel_dx)
            ty1 = int(sy1 + rel_dy)
            tx2_ = int(tx1 + rel_w)
            ty2_ = int(ty1 + rel_h)
            tx1, ty1 = max(0, tx1), max(0, ty1)
            tx2_, ty2_ = min(W, tx2_), min(H, ty2_)

        text_crop = img[ty1:ty2_, tx1:tx2_]
        density = calc_text_density(text_crop)

        stamp_text = ""
        if density_min < density < density_max:
            stamp_text = ocr_text(text_crop)

        page_label = page_idx + 1
        if stamp_text.strip():
            base_name = _sanitize_filename(stamp_text.strip())
        else:
            base_name = f"p{page_label}_{stamp_idx}"

        stamp_path = os.path.join(out_dir, f"{base_name}.webp")
        cv2.imwrite(stamp_path, stamp_crop, [cv2.IMWRITE_WEBP_QUALITY, 95])

        edge_path = None
        if edge_crop is not None:
            edge_path = os.path.join(out_dir, f"{base_name}_边款.webp")
            cv2.imwrite(edge_path, edge_crop, [cv2.IMWRITE_WEBP_QUALITY, 95])

        results.append({
            "pdf": pdf_name,
            "book": book_name,
            "page": page_label,
            "idx": stamp_idx,
            "text": stamp_text,
            "base_name": base_name,
            "stamp_path": stamp_path,
            "edge_path": edge_path,
            "stamp_bbox": (sx1, sy1, sx2, sy2),
            "edge_bbox": edge_bbox,
            "text_bbox": (tx1, ty1, tx2_, ty2_) if text_bbox is not None else None,
        })

    return results

def process_pdf(pdf_path, template, progress_callback=None, start_page=None, end_page=None):
    init_db()
    pdf_name = os.path.basename(pdf_path)
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)

    p_start = (start_page - 1) if start_page else 0
    p_end = (end_page - 1) if end_page else (total_pages - 1)
    p_start = max(0, p_start)
    p_end = min(total_pages - 1, p_end)

    all_results = []
    pages_to_process = p_end - p_start + 1

    for i, pg in enumerate(range(p_start, p_end + 1)):
        results = process_page(doc, pg, pdf_name, template)
        all_results.extend(results)

        conn = sqlite3.connect("yinpu.db")
        c = conn.cursor()
        for r in results:
            x1, y1, x2, y2 = r["stamp_bbox"]
            c.execute(
                "INSERT INTO stamps (pdf_name,page,idx,text,img_path,x1,y1,x2,y2) VALUES (?,?,?,?,?,?,?,?,?)",
                (r["pdf"], r["page"], r["idx"], r["text"], r["stamp_path"], x1, y1, x2, y2)
            )
        conn.commit()
        conn.close()

        if progress_callback:
            progress_callback((i + 1) / pages_to_process)

    doc.close()
    return all_results

def visualize_page(pdf_path, page_idx, template, scale=1.5):
    """
    渲染 PDF 页面并在检测结果上画框，用于可视化预览。
    🔴 红色框 = 印章区域（含 padding 外扩）
    🔵 蓝色框 = 释文框（自动识别的文字块）
     绿色框 = 边款（黑色为主色块，约印面 2~10 倍）
    返回 (annotated_image_bgr, stamp_candidates, edge_candidates)
    """
    doc = pymupdf.open(pdf_path)
    page = doc[page_idx]
    mat = pymupdf.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    doc.close()

    H, W = img.shape[:2]
    hsv_low = template["hsv_low"]
    hsv_high = template["hsv_high"]
    # 预览使用自身渲染倍率做基准：scale 相对 BASE 的比例换算 min_area
    min_area = template["min_area"] * ((scale * 72.0 / BASE_DPI) ** 2)
    pad_ratio = template.get("pad_ratio", 0.15)

    stamp_candidates = detect_stamp_regions(img, hsv_low, hsv_high, int(min_area), pad_ratio)

    edge_enabled = template.get("edge_enabled", True)
    edge_candidates = []
    if edge_enabled and stamp_candidates:
        avg_stamp_area = float(np.mean([c["area"] for c in stamp_candidates]))
        edge_candidates = detect_edge_inscriptions(img, avg_stamp_area)

    # 释文自动匹配
    exclude_mask = np.zeros((H, W), np.uint8)
    for c in stamp_candidates:
        x1, y1, x2, y2 = [int(v) for v in c["bbox"]]
        exclude_mask[max(0, y1):y2, max(0, x1):x2] = 255
    for e in edge_candidates:
        x1, y1, x2, y2 = [int(v) for v in e["bbox"]]
        exclude_mask[max(0, y1):y2, max(0, x1):x2] = 255
    shishi_map = match_shishi_blocks(img, [c["bbox"] for c in stamp_candidates],
                                     exclude_mask=exclude_mask)

    rel_dx, rel_dy, rel_w, rel_h = template["text_offset"]

    for idx, stamp in enumerate(stamp_candidates):
        sx1, sy1, sx2, sy2 = stamp["bbox"]
        cv2.rectangle(img, (sx1, sy1), (sx2, sy2), (0, 0, 255), 2)

        # 释文框：优先自动识别
        text_bbox = shishi_map.get(idx)
        if text_bbox is not None:
            tx1, ty1, tx2_, ty2_ = [int(v) for v in text_bbox]
        else:
            tx1 = int(sx1 + rel_dx)
            ty1 = int(sy1 + rel_dy)
            tx2_ = int(tx1 + rel_w)
            ty2_ = int(ty1 + rel_h)
        tx1, ty1 = max(0, tx1), max(0, ty1)
        tx2_, ty2_ = min(W, tx2_), min(H, ty2_)
        cv2.rectangle(img, (tx1, ty1), (tx2_, ty2_), (255, 0, 0), 2)

    for edge in edge_candidates:
        ex1, ey1, ex2, ey2 = edge["bbox"]
        cv2.rectangle(img, (ex1, ey1), (ex2, ey2), (0, 200, 0), 2)

    return img, stamp_candidates, edge_candidates
