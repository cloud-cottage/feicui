import streamlit as st
import os
import json
import pymupdf
from processor import process_pdf, load_templates, save_template, visualize_page
from PIL import Image
import numpy as np

st.set_page_config(page_title="印谱本地解析工具", layout="wide")
st.title("印谱PDF提取工具｜本地离线版")

# 初始化 session state
if "preview_result" not in st.session_state:
    st.session_state.preview_result = None
if "preview_page" not in st.session_state:
    st.session_state.preview_page = -1
if "thumb_page" not in st.session_state:
    st.session_state.thumb_page = 0
# 文件浏览器状态
if "fd_dir" not in st.session_state:
    st.session_state.fd_dir = os.path.expanduser("~")
if "manual_path" not in st.session_state:
    st.session_state.manual_path = ""

THUMBS_PER_PAGE = 10
THUMB_SCALE = 0.5

tab1, tab2, tab3 = st.tabs(["📄 PDF上传与版式标定", "⚡ 批量解析", "🖼️ 结果浏览"])

# ==================== Tab1: 可视化版式标定 ====================
with tab1:
    source_mode = st.radio("PDF来源", ["📁 本地文件路径（推荐，无大小限制）", "📤 上传PDF文件"], horizontal=True)

    pdf_path = None
    pdf_basename = None

    if source_mode.startswith("📁"):
        # ---------- 可点选的文件浏览器 ----------
        st.markdown("#### 🖱️ 点选文件")
        st.caption("用鼠标点选文件夹进入目录、点选 PDF 文件即可选中；也可在下方路径框手动输入")

        cur_dir = st.session_state.fd_dir
        st.markdown(f"**当前位置**：`{cur_dir}`")

        parent = os.path.dirname(cur_dir)
        c_up, c_path = st.columns([2, 6])
        with c_up:
            if parent and parent != cur_dir:
                if st.button("⬆️ 上级目录", key="fd_up", use_container_width=True):
                    st.session_state.fd_dir = parent
                    st.rerun()
        with c_path:
            home = os.path.expanduser("~")
            if st.button("🏠 主目录", key="fd_home", use_container_width=True):
                st.session_state.fd_dir = home
                st.rerun()

        dirs, pdfs = [], []
        try:
            for entry in sorted(os.listdir(cur_dir)):
                if entry.startswith("."):
                    continue
                full = os.path.join(cur_dir, entry)
                if os.path.isdir(full):
                    dirs.append(entry)
                elif entry.lower().endswith(".pdf"):
                    pdfs.append(entry)
        except Exception as e:
            st.error(f"❌ 无法访问目录：{cur_dir}（{e}）")

        if dirs:
            st.markdown("**📁 文件夹**")
            dcols = st.columns(min(4, len(dirs)))
            for i, d in enumerate(dirs):
                with dcols[i % 4]:
                    if st.button(f"📁 {d}", key=f"fdd_{i}_{d}", use_container_width=True):
                        st.session_state.fd_dir = os.path.join(cur_dir, d)
                        st.rerun()
        else:
            st.info("（当前目录无子文件夹）")

        if pdfs:
            st.markdown("**📄 PDF 文件（点击选中）**")
            for f in pdfs:
                if st.button(f"📄 {f}", key=f"fdf_{f}", use_container_width=True):
                    st.session_state.manual_path = os.path.join(cur_dir, f)
                    st.rerun()
        else:
            st.info("（当前目录无 PDF 文件）")

        st.markdown("---")

        local_path = st.text_input(
            "本地PDF文件路径（已选文件将自动填入）",
            key="manual_path",
            placeholder="/Users/kevin/Documents/印谱.pdf",
            help="可在上方点选文件自动填充，也可直接输入本地PDF文件的完整路径"
        )
        if local_path and os.path.isfile(local_path):
            pdf_path = local_path
            pdf_basename = os.path.basename(local_path)
            doc = pymupdf.open(pdf_path)
            total_pages = len(doc)
            doc.close()
            st.success(f"✅ 已加载：{pdf_basename}（共 {total_pages} 页）")
        elif local_path:
            st.error(f"❌ 文件不存在：{local_path}")
    else:
        uploaded_file = st.file_uploader("上传印谱PDF", type=["pdf"])
        tmp_pdf_path = "tmp.pdf"
        if uploaded_file:
            with open(tmp_pdf_path, "wb") as f:
                f.write(uploaded_file.read())
            pdf_path = tmp_pdf_path
            pdf_basename = uploaded_file.name
            doc = pymupdf.open(pdf_path)
            total_pages = len(doc)
            doc.close()
            st.success(f"✅ 已加载：{pdf_basename}（共 {total_pages} 页）")

    if pdf_path:

        # ============================
        # 📑 缩略图浏览
        # ============================
        st.markdown("### 📑 浏览全部页面，选择正文范围")
        st.caption("查看缩略图确认正文起始位置，然后点击选择起始页和结束页")

        total_thumb_pages = (total_pages + THUMBS_PER_PAGE - 1) // THUMBS_PER_PAGE
        current_thumb_page = st.session_state.thumb_page

        nav_col1, nav_col2, nav_col3 = st.columns([1, 3, 1])
        with nav_col1:
            if st.button("⬅️ 上一页", disabled=(current_thumb_page <= 0)):
                st.session_state.thumb_page -= 1
                st.rerun()
        with nav_col2:
            st.info(f"📄 第 {current_thumb_page * THUMBS_PER_PAGE + 1}~{min((current_thumb_page + 1) * THUMBS_PER_PAGE, total_pages)} 页 / 共 {total_pages} 页")
        with nav_col3:
            if st.button("下一页 ➡️", disabled=(current_thumb_page >= total_thumb_pages - 1)):
                st.session_state.thumb_page += 1
                st.rerun()

        start_idx = current_thumb_page * THUMBS_PER_PAGE
        end_idx = min(start_idx + THUMBS_PER_PAGE, total_pages)

        doc = pymupdf.open(pdf_path)
        thumb_cols = st.columns(5)
        for i in range(start_idx, end_idx):
            page = doc[i]
            mat = pymupdf.Matrix(THUMB_SCALE, THUMB_SCALE)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            col_idx = (i - start_idx) % 5
            with thumb_cols[col_idx]:
                st.image(img_data, caption=f"第 {i + 1} 页", use_container_width=True)
        doc.close()

        nav_col_b1, nav_col_b2, nav_col_b3 = st.columns([1, 3, 1])
        with nav_col_b1:
            if st.button("⬅️ 上一页", key="nav_prev_bottom", disabled=(current_thumb_page <= 0)):
                st.session_state.thumb_page -= 1
                st.rerun()
        with nav_col_b3:
            if st.button("下一页 ➡️", key="nav_next_bottom", disabled=(current_thumb_page >= total_thumb_pages - 1)):
                st.session_state.thumb_page += 1
                st.rerun()

        st.markdown("---")

        # ===== 页码范围 =====
        st.markdown("### 🎯 选择正文页码范围")
        col_range1, col_range2 = st.columns(2)
        with col_range1:
            start_page = st.number_input("正文起始页", min_value=1, max_value=total_pages, value=1, step=1,
                                          help="正文第一页的页码（跳过封面、封二等）")
        with col_range2:
            end_page = st.number_input("正文结束页", min_value=1, max_value=total_pages, value=total_pages, step=1,
                                        help="正文最后一页的页码（跳过封底、封三等）")

        if start_page > end_page:
            st.error("❌ 起始页不能大于结束页！")
        else:
            st.info(f" 将处理第 {start_page} ~ {end_page} 页，共 {end_page - start_page + 1} 页")

        st.markdown("---")

        # ===== 检测效果预览 =====
        st.markdown("### 🔍 检测效果预览")
        st.caption("🔴红框=印章 🔵蓝框=释文 绿框=边款")

        preview_page_num = st.slider(
            "选择预览页码",
            min_value=start_page,
            max_value=end_page,
            value=start_page,
        )

        if preview_page_num != st.session_state.preview_page:
            st.session_state.preview_result = None

        col_hsv1, col_hsv2, col_area = st.columns(3)
        with col_hsv1:
            h_low = st.slider("H下限", 0, 179, 0, key="pv_h_low")
            h_high = st.slider("H上限", 0, 179, 10, key="pv_h_high")
        with col_hsv2:
            s_low = st.slider("S下限", 0, 255, 120, key="pv_s_low")
            s_high = st.slider("S上限", 0, 255, 255, key="pv_s_high")
        with col_area:
            v_low = st.slider("V下限", 0, 255, 70, key="pv_v_low")
            v_high = st.slider("V上限", 0, 255, 255, key="pv_v_high")
            min_area = st.slider("印面最小面积", 100, 5000, 800, key="pv_min_area")

        # 边款与padding参数
        col_edge1, col_edge2 = st.columns(2)
        with col_edge1:
            edge_enabled = st.checkbox("启用边款检测（绿色框）", value=True, key="pv_edge")
        with col_edge2:
            pad_ratio = st.slider("印面框外扩比例", 0.0, 0.5, 0.15, 0.01,
                                  key="pv_pad", help="确保红色内容完全在红框内")

        if st.button("🔍 预览检测效果", type="primary"):
            with st.spinner(f"正在检测第 {preview_page_num} 页..."):
                try:
                    template_preview = {
                        "hsv_low": [h_low, s_low, v_low],
                        "hsv_high": [h_high, s_high, v_high],
                        "min_area": min_area,
                        "text_offset": [-120, 0, 110, 140],
                        "density_min": 0.002,
                        "density_max": 0.08,
                        "edge_enabled": edge_enabled,
                        "pad_ratio": pad_ratio
                    }
                    vis_img, stamp_cands, edge_cands = visualize_page(
                        pdf_path, preview_page_num - 1, template_preview
                    )
                    vis_rgb = vis_img[:, :, ::-1]
                    pil_img = Image.fromarray(vis_rgb)
                    st.session_state.preview_result = (pil_img, stamp_cands, edge_cands)
                    st.session_state.preview_page = preview_page_num
                except Exception as e:
                    st.error(f"预览失败：{e}")

        if st.session_state.preview_result and st.session_state.preview_page == preview_page_num:
            pil_img, stamp_cands, edge_cands = st.session_state.preview_result
            st.image(pil_img, caption=f"第 {preview_page_num} 页 — 🔴印章({len(stamp_cands)}) 🟢边款({len(edge_cands)})", use_container_width=True)
            st.info(f"📌 检测到 {len(stamp_cands)} 个印章，{len(edge_cands)} 个边款")
        else:
            st.info("👆 调好参数后点击「预览检测效果」查看可视化结果")

        st.markdown("---")

        # ===== 精细化参数 =====
        st.markdown("### ⚙️ 精细化参数")

        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("**释文框位置**（相对印章左上角的偏移）")
            dx = st.number_input("X偏移", value=-120, key="cfg_dx")
            dy = st.number_input("Y偏移", value=0, key="cfg_dy")
            tw = st.number_input("宽度", value=110, key="cfg_tw")
            th = st.number_input("高度", value=140, key="cfg_th")

        with col_right:
            st.markdown("**文本密度阈值**（控制是否对印章区域做OCR）")
            d_min = st.number_input("密度下限", value=0.002, format="%.4f", key="cfg_dmin")
            d_max = st.number_input("密度上限", value=0.08, format="%.4f", key="cfg_dmax")

        template_data = {
            "hsv_low": [h_low, s_low, v_low],
            "hsv_high": [h_high, s_high, v_high],
            "min_area": min_area,
            "text_offset": [dx, dy, tw, th],
            "density_min": d_min,
            "density_max": d_max,
            "page_range": [start_page, end_page],
            "edge_enabled": edge_enabled,
            "pad_ratio": pad_ratio
        }

        if st.button("💾 保存当前版式模板"):
            save_template(pdf_basename, template_data)
            st.success(f"✅ 模板已保存：{pdf_basename}（正文：第{start_page}~{end_page}页）")

    else:
        st.info(" 请通过上方选择本地文件路径或上传PDF")


# ==================== Tab2: 批量解析 ====================
with tab2:
    st.subheader("批量自动解析整本PDF")
    templates = load_templates()

    if templates:
        pdf_name_sel = st.selectbox("选择已保存模板", list(templates.keys()))
        tmpl = templates[pdf_name_sel]

        if "page_range" in tmpl:
            pr = tmpl["page_range"]
            st.info(f"📖 模板正文范围：第 {pr[0]} ~ {pr[1]} 页")
        else:
            st.warning("⚠️ 此模板未保存页码范围，将处理全部页面。")

        if st.button("开始批量解析（无人工干预）"):
            if not pdf_path:
                st.error("❌ 请先在Tab1中选择或上传PDF文件")
                st.stop()
            progress_bar = st.progress(0)

            def update_progress(pct):
                progress_bar.progress(pct)

            with st.spinner("正在处理，上千印面耗时较长，请勿关闭页面"):
                if "page_range" in tmpl:
                    start_p, end_p = tmpl["page_range"]
                else:
                    start_p, end_p = None, None
                res = process_pdf(pdf_path, tmpl, progress_callback=update_progress,
                                  start_page=start_p, end_page=end_p)

            # 统计
            total_stamps = len(res)
            total_edges = sum(1 for r in res if r.get("edge_path"))
            st.success(f"✅ 解析完成！印面：{total_stamps} 个，边款：{total_edges} 个")
            book_name = os.path.splitext(os.path.basename(pdf_path))[0]
            st.info(f"📁 输出目录：`output/{book_name}/`")
    else:
        st.info("暂无模板，请先到【PDF上传与版式标定】页面创建模板")


# ==================== Tab3: 结果浏览 ====================
with tab3:
    st.subheader("提取结果预览")

    output_dir = "output"
    if os.path.exists(output_dir):
        # 列出所有书籍目录
        book_dirs = sorted([d for d in os.listdir(output_dir)
                            if os.path.isdir(os.path.join(output_dir, d))])

        if not book_dirs:
            st.info("暂无输出，请先执行批量解析")
        else:
            book_sel = st.selectbox("选择书籍", book_dirs)
            book_path = os.path.join(output_dir, book_sel)

            # 列出所有 webp 文件
            all_files = sorted(os.listdir(book_path))
            stamp_files = [f for f in all_files if f.endswith(".webp") and "_边款" not in f]
            total = len(stamp_files)
            st.write(f"共 {total} 枚印章")

            if total > 0:
                page_size = 8
                page_num = st.number_input("页码", min_value=1, max_value=(total + page_size - 1) // page_size, value=1)
                start_idx = (page_num - 1) * page_size
                end_idx = start_idx + page_size
                show_files = stamp_files[start_idx:end_idx]

                for fname in show_files:
                    base = fname.rsplit(".webp", 1)[0]
                    edge_file = f"{base}_边款.webp"
                    has_edge = edge_file in all_files

                    st.markdown(f"**{base}**")
                    if has_edge:
                        col_s, col_e = st.columns(2)
                        with col_s:
                            st.image(os.path.join(book_path, fname), caption="印面", use_container_width=True)
                        with col_e:
                            st.image(os.path.join(book_path, edge_file), caption="边款", use_container_width=True)
                    else:
                        st.image(os.path.join(book_path, fname), caption="印面（无边款）", use_container_width=True)
                    st.markdown("---")
    else:
        st.info("暂无输出，请先执行批量解析")
