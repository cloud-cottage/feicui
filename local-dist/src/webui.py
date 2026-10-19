# src/webui.py
# ⚠ DEPRECATED（2026-10-16，Kevin 裁定）：本地版壳已由 Streamlit 换为 **PyWebView**（`webui/app.py`
#   ＋ `webui/api.py` ＋ `webui/ui/**`）。本文件**保留不删**（历史 Streamlit UI，966 行），
#   但**不再维护、不要起 8502**；逻辑层仍被新壳复用（`src/pdf_library.py` / `src/validator.py`）。
"""
「斐萃」本地电脑版
- 登录 → feicui 目录校验 → 主界面（左：仿真资源管理器 / 右：操作面板）
"""
import os
import re
import uuid
import random
import json
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st

from dotenv import load_dotenv

from src.validator import (
    parse_filename,
    build_filename,
    validate_fields,
    count_chinese,
    SHIWEN_MAX,
    AUTHOR_MAX,
)
from src.tencent_doc_api import (
    append_log_record,
    get_today_write_count,
    fetch_log_page,
)
from src.baidu_disk_api import lock_file, unlock_file, get_file_lock_status

load_dotenv()

# ============================================================
# 常量
# ============================================================
APP_TITLE_BROWSER = "「斐萃」数字玺印生成工具"
APP_TITLE_IN_PAGE = "「斐萃」玺印解析任务台"

FEICUI_NAME = "feicui"
SUB_DIRS = ["1_Original_PDF", "2_HighRes_PDF", "3_Cropped_Tiff"]
TIFF_DIR = "3_Cropped_Tiff"

# 硬编码用户
USER_LIST = {
    "ji":   {"pwd": "6666", "is_admin": True},
    "pan":  {"pwd": "1234", "is_admin": False},
    "test": {"pwd": "test", "is_admin": False},
}

DAILY_QUOTA = int(os.getenv("DAILY_QUOTA", "1000"))
SESSION_FILE = Path(".session.json")
SESSION_EXPIRE_DAYS = 7

# 随机测试数据
RANDOM_SHIWEN = ["长乐未央", "吉祥如意", "延年益寿", "清心", "淡泊明志",
                 "宁静致远", "翰墨", "金石寿", "得自在", "安且吉兮"]
RANDOM_DYNASTY = ["汉", "唐", "宋", "明", "清", "战国", "秦", "元"]
RANDOM_AUTHOR = ["陈巨来", "吴昌硕", "齐白石", "邓石如", "赵之谦", "吴让之"]


# ============================================================
# 页面基础设置
# ============================================================
st.set_page_config(
    page_title=APP_TITLE_BROWSER,
    page_icon=str(Path(__file__).parent.parent / "assets" / "feicui.png"),
    layout="wide",
)

# ============================================================
# 初始化 session_state
# ============================================================
def save_session(username: str, feicui_root: str = ""):
    """保存登录状态到本地文件，7天有效"""
    data = {
        "username": username,
        "expire": (datetime.now() + timedelta(days=SESSION_EXPIRE_DAYS)).isoformat(),
        "feicui_root": feicui_root,
    }
    SESSION_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_session():
    """读取本地登录状态，返回 (username, is_admin, feicui_root)；过期或不存在返回 (None, False, '')"""
    if not SESSION_FILE.exists():
        return None, False, ""
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        expire = datetime.fromisoformat(data["expire"])
        if datetime.now() > expire:
            SESSION_FILE.unlink()
            return None, False, ""
        username = data["username"]
        user = USER_LIST.get(username)
        if not user:
            return None, False, ""
        return username, user["is_admin"], data.get("feicui_root", "")
    except Exception:
        return None, False, ""


def clear_session():
    """清除本地登录状态"""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def init_state():
    ss = st.session_state
    ss.setdefault("logged_in", False)
    ss.setdefault("username", "")
    ss.setdefault("is_admin", False)
    ss.setdefault("dir_verified", False)
    ss.setdefault("feicui_root", "")
    ss.setdefault("current_subdir", "")
    ss.setdefault("selected_file", None)
    ss.setdefault("log_enabled", True)
    ss.setdefault("today_count", get_today_write_count())

    # 自动登录（7天内免登录）
    if not ss.logged_in:
        uname, admin, saved_root = load_session()
        if uname:
            ss.logged_in = True
            ss.username = uname
            ss.is_admin = admin
            # 自动加载已校验过的目录
            if saved_root and Path(saved_root).exists():
                ss.feicui_root = saved_root
                ss.dir_verified = True


init_state()


# ============================================================
# 工具函数
# ============================================================
def update_env_feicui(path: str):
    """把选中的 feicui 路径写回 .env 的 FEICUI_ROOT"""
    env_path = Path(".env")
    if not env_path.exists():
        # 从 .env.example 复制一份
        example = Path(".env.example")
        if example.exists():
            env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    # 读取现有内容
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    new_lines = []
    found = False
    for ln in lines:
        if ln.startswith("FEICUI_ROOT="):
            new_lines.append(f"FEICUI_ROOT={path}")
            found = True
        else:
            new_lines.append(ln)
    if not found:
        new_lines.append(f"FEICUI_ROOT={path}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def verify_feicui_dir(root: Path):
    """
    校验 feicui 目录结构。
    返回 (ok, msg)
    """
    if not root.exists() or not root.is_dir():
        return False, "目录不存在"
    if root.name != FEICUI_NAME:
        return False, f"目录名称必须是 `{FEICUI_NAME}`，当前为 `{root.name}`"

    # 校验③：根目录下只能有 3 个子目录（忽略 .DS_Store 等系统隐藏文件）
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

    # 校验④：3_Cropped_Tiff 下只能有一级子目录，不能嵌套
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


def list_subdirs():
    """列出 3_Cropped_Tiff 下的一级子目录"""
    root = Path(st.session_state.feicui_root) / TIFF_DIR
    if not root.exists():
        return []
    return sorted([d.name for d in root.iterdir() if d.is_dir()])


def list_tiff_files(subdir_name: str):
    """列出某个一级子目录下的 tiff/tif 文件"""
    d = Path(st.session_state.feicui_root) / TIFF_DIR / subdir_name
    if not d.exists():
        return []
    files = []
    for f in sorted(d.iterdir()):
        if f.is_file() and f.suffix.lower() in (".tiff", ".tif"):
            files.append(f.name)
    return files


def generate_test_tiff(subdir_name: str):
    """在指定一级子目录生成一个测试 tiff（合规命名，P/C/R 编号自动递增不重复）"""
    import re as _re
    shiwen = random.choice(RANDOM_SHIWEN)
    dynasty = random.choice(RANDOM_DYNASTY)
    author = random.choice(RANDOM_AUTHOR)

    target_dir = Path(st.session_state.feicui_root) / TIFF_DIR / subdir_name

    # 扫描已有文件，提取已用的页码（P后3位数字）
    used_pages = set()
    for f in target_dir.iterdir():
        if f.is_file() and f.suffix.lower() in (".tiff", ".tif"):
            m = _re.match(r"P(\d{3})-C\d-R\d-", f.name)
            if m:
                used_pages.add(int(m.group(1)))

    # 下一个可用页码（从1开始递增）
    page = 1
    while page in used_pages:
        page += 1
    page_str = f"{page:03d}"

    # 随机列码(C)和行码(R)，确保与页码不重复
    used_digits = set()
    for d in page_str:
        used_digits.add(int(d))
    col = random.choice([d for d in range(10) if d not in used_digits])
    used_digits.add(col)
    row = random.choice([d for d in range(10) if d not in used_digits])

    # 拼接完整文件名
    name = f"P{page_str}-C{col}-R{row}-{shiwen}-{dynasty}-{author}.tiff"
    target = target_dir / name

    # 避免重名（理论上页码递增不会重名，兜底）
    idx = 1
    while target.exists():
        idx += 1
        name = f"P{page_str}-C{col}-R{row}-{shiwen}_{idx}-{dynasty}-{author}.tiff"
        target = target_dir / name

    # 复制占位 tiff 作为测试文件
    placeholder = Path(__file__).parent.parent / "assets" / "test_seal.tiff"
    if not placeholder.exists():
        st.error("占位图 assets/test_seal.tiff 不存在")
        return None
    target.write_bytes(placeholder.read_bytes())
    return target.name


# ============================================================
# 页面1：登录
# ============================================================
def page_login():
    st.title(APP_TITLE_IN_PAGE)
    st.caption("请登录后使用")

    with st.form("login_form"):
        username = st.text_input("账号")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary")

    if submitted:
        user = USER_LIST.get(username.strip())
        if user and user["pwd"] == password:
            uname = username.strip()
            st.session_state.logged_in = True
            st.session_state.username = uname
            st.session_state.is_admin = user["is_admin"]
            save_session(uname)
            st.rerun()
        else:
            st.error("账号或密码错误")


# ============================================================
# 页面2：feicui 目录初始化校验
# ============================================================
def page_dir_setup():
    st.title(APP_TITLE_IN_PAGE)
    st.subheader("目录初始化")
    st.info(
        f"请选择本地名为 `{FEICUI_NAME}` 的百度网盘企业同步目录。\n\n"
        f"目录结构必须为：\n"
        f"- `feicui/1_Original_PDF`\n"
        f"- `feicui/2_HighRes_PDF`\n"
        f"- `feicui/3_Cropped_Tiff/`（仅一级子目录）"
    )

    # 尝试读取 .env 缓存
    cached = os.getenv("FEICUI_ROOT", "").strip()

    # 初始化导航起点
    if "nav_root" not in st.session_state:
        st.session_state.nav_root = str(Path.home())

    nav_root = st.session_state.nav_root

    st.markdown("**逐级浏览选择目录**")
    st.caption(f"当前位置：`{nav_root}`")

    # 列出当前目录下的子文件夹
    try:
        entries = sorted([
            e.name for e in Path(nav_root).iterdir()
            if e.is_dir() and not e.name.startswith(".")
        ])
    except PermissionError:
        entries = []
        st.warning("无权限访问该目录")

    col_up, col_into = st.columns([1, 3])
    with col_up:
        if st.button("⬆️ 返回上一级"):
            parent = str(Path(nav_root).parent)
            st.session_state.nav_root = parent
            st.rerun()

    if entries:
        chosen = st.selectbox("选择子文件夹进入", [""] + entries)
        if chosen:
            new_path = str(Path(nav_root) / chosen)
            st.session_state.nav_root = new_path
            st.rerun()
    else:
        st.caption("（该目录下没有子文件夹）")

    # 使用当前导航路径按钮
    if st.button("📍 使用当前导航路径"):
        st.session_state["dir_path_input"] = nav_root
        st.rerun()

    # 当前导航路径填入输入框
    path_input = st.text_input(
        f"feicui 目录绝对路径",
        value=st.session_state.get("dir_path_input", cached),
        placeholder="/Users/xxx/百度网盘/feicui",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("校验目录并进入", type="primary"):
            p = Path(path_input.strip())
            ok, msg = verify_feicui_dir(p)
            if ok:
                st.session_state.feicui_root = str(p.resolve())
                st.session_state.dir_verified = True
                update_env_feicui(str(p.resolve()))
                save_session(st.session_state.username, str(p.resolve()))
                st.success(msg)
                st.rerun()
            else:
                st.session_state.dir_verified = False
                st.session_state["verify_error_path"] = str(p)
                st.session_state["verify_error_msg"] = msg
                st.error(msg)

    with col2:
        st.caption("管理员可在此页直接跳过校验（仅调试用）")
        if st.session_state.is_admin:
            if st.button("跳过校验（管理员调试）"):
                st.session_state.dir_verified = True
                st.session_state.feicui_root = str(Path(path_input.strip()).resolve())
                st.rerun()

    # 校验失败时，管理员可一键创建标准目录结构
    if st.session_state.get("verify_error_msg") and st.session_state.is_admin:
        st.warning("目录结构不符合规范，管理员可一键自动创建标准子目录：")
        error_path = st.session_state.get("verify_error_path", "")
        if st.button("🔧 自动创建标准目录结构（管理员）"):
            p = Path(error_path)
            if p.exists() and p.is_dir() and p.name == FEICUI_NAME:
                for sub in SUB_DIRS:
                    (p / sub).mkdir(exist_ok=True)
                st.success("已创建三个标准子目录，请重新点击「校验目录并进入」")
                st.session_state.pop("verify_error_msg", None)
                st.rerun()
            else:
                st.error("请先选择名为 feicui 的目录，再自动创建子目录")


# ============================================================
# 页面3：主界面
# ============================================================
def page_main():
    # ========== 顶部菜单栏（所有功能按钮） ==========
    st.markdown(
        """<style>
        /* 小米风格全局 */
        .stApp {
            background: #f5f5f5;
            font-family: -apple-system, "PingFang SC", "MiSans", sans-serif;
        }
        /* 按钮：圆角 + 小米橙主色 */
        div[data-testid="stHorizontalBlock"] button,
        button[kind="primary"] {
            border-radius: 8px !important;
            border: none !important;
            padding-top: 4px !important;
            padding-bottom: 4px !important;
            min-height: 32px !important;
            font-size: 13px !important;
            font-weight: 500 !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
            transition: all 0.2s !important;
        }
        button[kind="primary"] {
            background: #FF6700 !important;
            color: white !important;
        }
        button[kind="secondary"] {
            background: white !important;
            color: #333 !important;
        }
        button:disabled {
            background: #e0e0e0 !important;
            color: #999 !important;
            box-shadow: none !important;
        }
        /* 文字缩小 */
        div[data-testid="stHorizontalBlock"] p {
            font-size: 13px !important;
            margin-bottom: 0px !important;
            padding-top: 4px !important;
        }
        /* 输入框圆角 */
        input, textarea {
            border-radius: 8px !important;
            border: 1px solid #e0e0e0 !important;
        }
        /* 卡片背景 */
        div[data-testid="stVerticalBlock"] {
            gap: 0.5rem !important;
        }
        /* 标题 */
        h1, h2, h3 {
            font-weight: 600 !important;
            color: #1a1a1a !important;
        }
        /* 分割线 */
        hr {
            margin: 0.5rem 0 !important;
            border-color: #e0e0e0 !important;
        }
        /* 下拉框 */
        div[data-baseweb="select"] > div {
            border-radius: 8px !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    with st.container():
        c1, c2, c3, c4 = st.columns(4)

        # 用户名弹出菜单（含退出）
        with c1:
            admin_tag = "（管理员）" if st.session_state.is_admin else ""
            with st.popover(f"👤 {st.session_state.username}{admin_tag}"):
                st.caption(f"当前用户：{st.session_state.username}")
                st.caption(f"角色：{'管理员' if st.session_state.is_admin else '操作员'}")
                if st.button("🚪 退出登录", use_container_width=True):
                    clear_session()
                    for k in ["logged_in", "username", "is_admin", "dir_verified"]:
                        st.session_state.pop(k, None)
                    st.rerun()

        # 日志状态弹出菜单（含切换）
        with c2:
            log_label = f"📊 日志状态：{'开启' if st.session_state.log_enabled else '关闭'}｜今日已写：{st.session_state.today_count}/{DAILY_QUOTA}"
            with st.popover(log_label):
                if st.button(
                    "🔴 关闭日志" if st.session_state.log_enabled else "🟢 开启日志",
                    use_container_width=True,
                ):
                    st.session_state.log_enabled = not st.session_state.log_enabled
                    st.rerun()

        # 目录弹出菜单（含重新选择）
        with c3:
            with st.popover(f"📁 {Path(st.session_state.feicui_root).name}"):
                st.caption(f"当前目录：{st.session_state.feicui_root}")
                if st.button("🔄 重新选择目录", use_container_width=True):
                    st.session_state.dir_verified = False
                    st.rerun()

        with c4:
            if st.button("🔁 重启"):
                import subprocess, sys
                webui_dir = str(Path(__file__).parent.parent)
                pid = os.getpid()
                script = (
                    f"sleep 2; kill {pid} 2>/dev/null; "
                    f"cd {webui_dir}; "
                    f"{sys.executable} -m streamlit run src/webui.py"
                )
                subprocess.Popen(["bash", "-c", script])
                st.session_state["toast_msg"] = "服务即将重启..."

    st.divider()

    # ========== 下方主操作区 ==========
    left, right = st.columns([1.5, 1])

    # ---------------- 左侧：缩略图文件管理器 ----------------
    with left:
        # 子目录选择（文件夹按钮标签页）+ 管理员生成测试按钮
        subdirs = list_subdirs()
        if not subdirs:
            st.warning("3_Cropped_Tiff 下没有子目录")
        else:
            # 文件夹标签页
            nav_cols = st.columns(min(len(subdirs), 6))
            for i, sd in enumerate(subdirs[:6]):
                with nav_cols[i]:
                    is_active = (sd == st.session_state.current_subdir)
                    if st.button(
                        f"📁 {sd}",
                        disabled=is_active,
                        key=f"nav_{sd}",
                        use_container_width=True,
                    ):
                        st.session_state.current_subdir = sd
                        st.session_state.thumb_page = 0
                        st.rerun()
            chosen_sub = st.session_state.current_subdir if st.session_state.current_subdir in subdirs else subdirs[0]
            st.session_state.current_subdir = chosen_sub

            # 管理员生成测试按钮
            if st.session_state.is_admin:
                if st.button("🎲 在此目录生成测试TIFF", use_container_width=True):
                    name = generate_test_tiff(chosen_sub)
                    st.success(f"已生成：{name}")

            # 视图切换（Windows 风格）
            current_view = st.session_state.get("thumb_view", "medium")
            view_cfg = {
                "large":  {"cols": 5,  "per_page": 20},
                "medium": {"cols": 10, "per_page": 50},
                "small":  {"cols": 20, "per_page": 100},
                "list":   {"cols": 1,  "per_page": 30},
            }
            vb1, vb2, vb3, vb4 = st.columns(4)
            with vb1:
                if st.button("🖼️ 大图标", disabled=(current_view == "large"),
                            use_container_width=True):
                    st.session_state.thumb_view = "large"
                    st.session_state.thumb_page = 0
                    st.rerun()
            with vb2:
                if st.button("📋 中等图标", disabled=(current_view == "medium"),
                            use_container_width=True):
                    st.session_state.thumb_view = "medium"
                    st.session_state.thumb_page = 0
                    st.rerun()
            with vb3:
                if st.button("📄 小图标", disabled=(current_view == "small"),
                            use_container_width=True):
                    st.session_state.thumb_view = "small"
                    st.session_state.thumb_page = 0
                    st.rerun()
            with vb4:
                if st.button("📃 列表", disabled=(current_view == "list"),
                            use_container_width=True):
                    st.session_state.thumb_view = "list"
                    st.session_state.thumb_page = 0
                    st.rerun()

            cfg = view_cfg[current_view]
            cols_per_row = cfg["cols"]
            per_page = cfg["per_page"]

            files = list_tiff_files(chosen_sub)
            if not files:
                st.info("该目录下没有 tiff 文件")
            else:
                total = len(files)
                total_pages = (total + per_page - 1) // per_page
                page = st.session_state.get("thumb_page", 0)
                page = min(page, total_pages - 1)

                # 当前选中文件的索引
                current_idx = 0
                if st.session_state.selected_file:
                    sel_name = Path(st.session_state.selected_file).name
                    if sel_name in files:
                        current_idx = files.index(sel_name)

                # 检测 URL 里的 file_idx 参数（方向键导航）
                query_params = st.query_params
                if "file_idx" in query_params:
                    try:
                        idx = int(query_params["file_idx"])
                        if 0 <= idx < total:
                            fpath = (Path(st.session_state.feicui_root)
                                     / TIFF_DIR / chosen_sub / files[idx])
                            st.session_state.selected_file = str(fpath)
                            # 清除参数避免重复触发
                            st.query_params.clear()
                            st.rerun()
                    except Exception:
                        pass

                # 注入键盘导航 JS
                st.markdown(
                    f"""<script>
                    (function() {{
                        const total = {total};
                        const current = {current_idx};
                        document.onkeydown = function(e) {{
                            let next = current;
                            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = Math.min(current + 1, total - 1);
                            if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = Math.max(current - 1, 0);
                            if (next !== current) {{
                                window.location.hash = 'file_idx=' + next;
                                // 触发 Streamlit rerun
                                const frames = window.parent.document.querySelectorAll('iframe');
                                if (frames.length > 0) {{
                                    // 通过修改 query param 触发 rerun
                                    const url = new URL(window.location);
                                    url.searchParams.set('file_idx', next);
                                    window.history.pushState({{}}, '', url);
                                    // 模拟刷新
                                    window.parent.location.reload();
                                }}
                            }}
                        }}
                    }})();
                    </script>""",
                    unsafe_allow_html=True,
                )

                st.caption(f"共 {total} 个文件 · 第 {page+1}/{total_pages} 页 · ↑↓←→ 切换")

                # 分页导航
                nav1, nav2, nav3 = st.columns([1, 2, 1])
                with nav1:
                    if st.button("⬅️ 上一页", disabled=(page == 0),
                                use_container_width=True):
                        st.session_state.thumb_page = page - 1
                        st.rerun()
                with nav2:
                    st.markdown(
                        f'<div style="text-align:center;padding-top:5px;">'
                        f'{page+1} / {total_pages}</div>',
                        unsafe_allow_html=True,
                    )
                with nav3:
                    if st.button("下一页 ➡️", disabled=(page >= total_pages - 1),
                                use_container_width=True):
                        st.session_state.thumb_page = page + 1
                        st.rerun()

                # 当前页文件
                start = page * per_page
                end = min(start + per_page, total)
                page_files = files[start:end]

                if current_view == "list":
                    # 列表模式：小缩略图 + 文件名左对齐
                    import subprocess, tempfile, base64
                    tmp_dir = Path(tempfile.gettempdir()) / "feicui_thumbs"
                    tmp_dir.mkdir(exist_ok=True)
                    for fname in page_files:
                        fpath = (Path(st.session_state.feicui_root)
                                 / TIFF_DIR / chosen_sub / fname)
                        thumb_path = tmp_dir / f"{fpath.stem}.png"
                        if not thumb_path.exists():
                            try:
                                subprocess.run(
                                    ["sips", "-s", "format", "png",
                                     "-Z", "150", str(fpath),
                                     "--out", str(thumb_path)],
                                    check=True, capture_output=True
                                )
                            except Exception:
                                pass
                        selected = (st.session_state.selected_file == str(fpath))
                        row_c1, row_c2 = st.columns([1, 6])
                        with row_c1:
                            if thumb_path.exists():
                                b64 = base64.b64encode(
                                    thumb_path.read_bytes()
                                ).decode()
                                border = ("2px solid #ff4b4b" if selected
                                          else "1px solid #ddd")
                                st.markdown(
                                    f'<img src="data:image/png;base64,{b64}" '
                                    f'style="width:48px;height:48px;object-fit:cover;'
                                    f'border:{border};border-radius:4px;">',
                                    unsafe_allow_html=True,
                                )
                        with row_c2:
                            st.markdown(
                                f"""<style>
                                div[data-testid="stButton"] button {{
                                    text-align: left !important;
                                    justify-content: flex-start !important;
                                }}
                                </style>""",
                                unsafe_allow_html=True,
                            )
                            label = fname
                            if st.button(label, key=f"file_{fname}",
                                         use_container_width=True):
                                st.session_state.selected_file = str(fpath)
                                st.rerun()
                else:
                    # 缩略图网格
                    import subprocess, tempfile, base64
                    tmp_dir = Path(tempfile.gettempdir()) / "feicui_thumbs"
                    tmp_dir.mkdir(exist_ok=True)

                    for i in range(0, len(page_files), cols_per_row):
                        row_files = page_files[i:i + cols_per_row]
                        cols = st.columns(cols_per_row)
                        for j, fname in enumerate(row_files):
                            fpath = (Path(st.session_state.feicui_root)
                                     / TIFF_DIR / chosen_sub / fname)
                            thumb_path = tmp_dir / f"{fpath.stem}.png"
                            if not thumb_path.exists():
                                try:
                                    subprocess.run(
                                        ["sips", "-s", "format", "png",
                                         "-Z", "150", str(fpath),
                                         "--out", str(thumb_path)],
                                        check=True, capture_output=True
                                    )
                                except Exception:
                                    pass
                            with cols[j]:
                                if thumb_path.exists():
                                    b64 = base64.b64encode(
                                        thumb_path.read_bytes()
                                    ).decode()
                                    selected = (
                                        st.session_state.selected_file == str(fpath)
                                    )
                                    border = ("3px solid #ff4b4b" if selected
                                              else "1px solid #ddd")
                                    st.markdown(
                                        f'<img src="data:image/png;base64,{b64}" '
                                        f'style="width:100%;border:{border};'
                                        f'border-radius:4px;">',
                                        unsafe_allow_html=True,
                                    )
                                short = fname[:15] + ("..." if len(fname) > 15 else "")
                                if st.button(short, key=f"file_{fname}",
                                             use_container_width=True):
                                    st.session_state.selected_file = str(fpath)
                                    st.rerun()

    # ---------------- 右侧：操作面板 ----------------
    with right:
        sel = st.session_state.selected_file
        if not sel:
            st.info("请在左侧点击选择一个 tiff 文件")
        else:
            sel_path = Path(sel)
            old_name = sel_path.name

            # 正方形大图预览
            import subprocess, tempfile, base64
            tmp_png = Path(tempfile.gettempdir()) / "feicui_preview_big.png"
            try:
                subprocess.run(
                    ["sips", "-s", "format", "png", "-Z", "400",
                     str(sel_path), "--out", str(tmp_png)],
                    check=True, capture_output=True
                )
                b64 = base64.b64encode(tmp_png.read_bytes()).decode()
                st.markdown(
                    f'<div style="display:flex;justify-content:center;">'
                    f'<img src="data:image/png;base64,{b64}" '
                    f'style="width:300px;height:300px;object-fit:contain;'
                    f'border:1px solid #ddd;border-radius:8px;background:#fafafa;">'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            except Exception:
                st.info("（图片预览不可用）")

            st.caption(f"当前文件：{old_name}")

            parsed = parse_filename(old_name)
            if parsed:
                page, col, row, def_sw, def_dy, def_au = parsed
                prefix = f"P{page}-C{col}-R{row}-"
                st.success(f"已自动解析：第 {int(page)} 页 · 第 {col} 列 · 第 {row} 行")
            else:
                def_sw, def_dy, def_au = "", "", ""
                prefix = ""
                st.warning("文件名非标准模板，请手动填写")

            shiwen = st.text_input(
                f"印面释文（最多 {SHIWEN_MAX} 个汉字）", value=def_sw)
            dynasty = st.text_input("朝代", value=def_dy)
            author = st.text_input(
                f"作者（最多 {AUTHOR_MAX} 个汉字）", value=def_au)

            st.caption(
                f"释文 {count_chinese(shiwen)}/{SHIWEN_MAX}　"
                f"作者 {count_chinese(author)}/{AUTHOR_MAX}")

            valid_ok, valid_msg = validate_fields(shiwen, dynasty, author)
            new_name = f"{prefix}{shiwen}-{dynasty}-{author}.tiff"
            st.markdown(f"**预览新文件名：** `{new_name}`")

            if not valid_ok:
                st.error(valid_msg)
                st.button("执行重命名 + 写入日志", disabled=True)
            elif new_name == old_name:
                st.caption("文件名未变化")
                st.button("执行重命名 + 写入日志", disabled=True)
            else:
                new_path = sel_path.parent / new_name
                if new_path.exists():
                    st.error(f"同目录已存在：{new_name}")
                    st.button("执行重命名 + 写入日志", disabled=True)
                else:
                    cloud_path = f"/feicui/{TIFF_DIR}/{st.session_state.current_subdir}/{old_name}"
                    lock_status = get_file_lock_status(cloud_path)
                    if lock_status == "locked":
                        st.error("文件已被他人锁定")
                    else:
                        if st.button("执行重命名 + 写入日志", type="primary"):
                            with st.spinner("正在处理..."):
                                lock_ok, lock_msg = lock_file(cloud_path, st.session_state.username)
                                if not lock_ok:
                                    st.error(f"锁定失败：{lock_msg}")
                                else:
                                    try:
                                        sel_path.rename(new_path)
                                        import hashlib
                                        md5 = hashlib.md5(new_path.read_bytes()).hexdigest()
                                        record = {
                                            "original_path": str(sel_path),
                                            "old_filename": old_name,
                                            "new_filename": new_name,
                                            "印面释文": shiwen,
                                            "朝代": dynasty,
                                            "作者": author,
                                            "file_md5": md5,
                                            "operator": st.session_state.username,
                                            "status": "success",
                                        }
                                        if not st.session_state.log_enabled:
                                            st.warning("文件已改名，日志已关闭，未写入")
                                        else:
                                            log_ok, log_msg = append_log_record(record)
                                            if log_ok:
                                                st.success(f"✅ 改名完成，日志已写入")
                                                st.session_state.today_count = get_today_write_count()
                                            else:
                                                st.warning(f"文件已改名，日志写入失败：{log_msg}")
                                        st.session_state.selected_file = str(new_path)
                                    finally:
                                        unlock_file(cloud_path)

    # ========== 底部悬浮 toast + 日志 ==========
    st.markdown(
        """<style>
        .bottom-bar {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: white;
            border-top: 1px solid #e0e0e0;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
            padding: 8px 20px;
            z-index: 999;
            max-height: 140px;
            overflow-y: auto;
        }
        .bottom-toast {
            background: #fff3e0;
            border: 1px solid #ffcc80;
            border-radius: 8px;
            padding: 6px 12px;
            margin-bottom: 6px;
            font-size: 13px;
            color: #e65100;
            animation: toast-fade 3s forwards;
        }
        @keyframes toast-fade {
            0% { opacity: 1; }
            70% { opacity: 1; }
            100% { opacity: 0; }
        }
        .bottom-bar table {
            font-size: 12px;
            width: 100%;
            border-collapse: collapse;
        }
        .bottom-bar th, .bottom-bar td {
            padding: 2px 8px;
            text-align: left;
            border-bottom: 1px solid #f0f0f0;
        }
        .bottom-bar th {
            color: #666;
            font-weight: 500;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    # 底部悬浮内容
    toast_msg = st.session_state.pop("toast_msg", "")
    rows = fetch_log_page(page_size=5, page=1)

    log_html = '<div class="bottom-bar">'
    if toast_msg:
        log_html += f'<div class="bottom-toast">⚠️ {toast_msg}</div>'
    log_html += '<div style="font-size:12px;color:#999;margin-bottom:4px;">最近操作日志</div>'
    if rows:
        log_html += '<table><tr><th>时间</th><th>操作人</th><th>旧文件名</th><th>新文件名</th></tr>'
        for r in reversed(rows[:5]):
            log_html += (
                f'<tr><td>{r.get("operate_time","")[:19]}</td>'
                f'<td>{r.get("operator","")}</td>'
                f'<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;">{r.get("old_filename","")}</td>'
                f'<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;">{r.get("new_filename","")}</td></tr>'
            )
        log_html += '</table>'
    else:
        log_html += '<div style="font-size:12px;color:#999;">暂无日志</div>'
    log_html += '</div>'
    st.markdown(log_html, unsafe_allow_html=True)


# ============================================================
# 路由
# ============================================================
def main():
    if not st.session_state.logged_in:
        page_login()
        return
    if not st.session_state.dir_verified:
        page_dir_setup()
        return
    page_main()


main()
