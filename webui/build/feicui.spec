# -*- mode: python ; coding: utf-8 -*-
# webui/build/feicui.spec —— 「斐萃 · 本地电脑版」macOS `.app` 打包（PyInstaller 6.x / Python 3.11）
#
# 跑法（**必须**用独立构建环境；共用 `venv` 一字不改 —— 见 README §0）：
#   cd /Users/kevin/bistro/feicui
#   PYTHONPATH=$PWD/venv/lib/python3.11/site-packages \
#   FEICUI_PACK_STAGE=1 \
#   webui/build/.venv-build/bin/python -m PyInstaller --noconfirm --clean \
#       --distpath webui/build/dist --workpath webui/build/build webui/build/feicui.spec
#
# 阶段（`FEICUI_PACK_STAGE`）：
#   1 = 壳 + UI + api + 逻辑层 + Python 运行时（含渲染栈）—— **不含 OCR**
#   2 = 阶段 1 ＋ RapidOCR（`rapidocr` 含 ONNX 模型 ＋ `onnxruntime`）
#   3 = 阶段 2 ＋ `--collect-all` paddle / paddlex / paddleocr（**只为体积对照**；见 README §3 路 A）
#
# 关键结构约定（**冻结态路径**，与 `webui/build/pack_main.py` 配套）：
#   _MEIPASS/{ui,assets,data,src,app.py}            ← 壳与 UI（`app.py` 走 data，避免模块名 `app` 撞车）
#   _MEIPASS/ops/book-page-2400/render_page_2400.py ← 引擎脚本（`REPO = parents[2]` ⇒ 正好落 _MEIPASS）
#   _MEIPASS/server/app/{__init__,naming,colorcal,seal_canvas}.py ← 引擎的 `app.*`（**必须是源码文件**）
#   _MEIPASS/config/book_dir_keys.json              ← `naming.DEFAULT_DIR_KEYS_PATH = parents[2]/config/…`

import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))          # 仓根
WEBUI = os.path.join(ROOT, "webui")
STAGE = os.environ.get("FEICUI_PACK_STAGE", "1")
WITH_OCR = STAGE in ("2", "3")
WITH_PADDLE = STAGE == "3"
SUFFIX = {"1": "-s1", "2": "-s2", "3": "-s3-paddle"}[STAGE]

# ── `.app` 图标（**用户可见的那个**）──────────────────────────────────────────
# 来源：**`webui/assets/feicui.svg`**（矢量，viewBox 0 0 480 480；与 480×480 的 `feicui.png` 同一设计）。
# 生成：`bash webui/build/make-icns.sh`（只用 macOS 自带 qlmanage / sips / iconutil，**无新 Python 依赖**）
#   qlmanage -t -s 1024 -o <dir> webui/assets/feicui.svg      # ⇒ 1024×1024 原生母图（矢量重渲染）
#   sips -z N N <母图> --out feicui.iconset/icon_<s>x<s>[@2x].png   # 16…512 ＋ @2x 共 9 槽
#   cp <母图> feicui.iconset/icon_512x512@2x.png              # ★ 1024 槽＝母图原样，不重采样
#   iconutil -c icns feicui.iconset -o webui/build/feicui.icns
# ⇒ `feicui.icns`（10 图像槽 ＋ info；2026-10-17 重生成后 1 013 361 B）**随仓提交**（spec 的构建输入；
#   `webui/build/dist/**` 才是产物）。母图留档 `webui/build/feicui-1024.png`。
# ⚠ 旧版 icns 的 1024 槽是 sips 从 480×480 PNG **放大**（边缘能量 3.539）；现为 SVG **原生重渲染**
#   （边缘能量 5.394，且 `ic10` 解码像素与母图**逐像素一致**/max diff 0）⇒ ≥1024 槽不再是放大。
#   取图工具比选与失败原样留档见 `webui/build/readings-theme.md` §4.1（PyMuPDF 渲染全黑、
#   ImageMagick 报 `vector graphics nested too deeply`，只有 qlmanage 可用）。
ICON = os.path.join(WEBUI, "build", "feicui.icns")
if not os.path.exists(ICON):
    raise SystemExit(f"缺 .app 图标：{ICON}（用 `bash webui/build/make-icns.sh` 从 webui/assets/feicui.svg 生成）")

APP_NAME = "斐萃"
EXE_NAME = "斐萃" + SUFFIX
BUNDLE_NAME = "斐萃" + SUFFIX

# ── 随包数据（相对路径必须与上面的结构约定一致）────────────────────────────────
datas = [
    (os.path.join(WEBUI, "ui"), "ui"),
    (os.path.join(WEBUI, "assets"), "assets"),
    (os.path.join(WEBUI, "data"), "data"),
    (os.path.join(WEBUI, "src"), "src"),                  # 立即可文件级 run（`--engine-run src/ocr_rapid.py`）
    (os.path.join(WEBUI, "app.py"), "."),                 # 壳：**按文件路径**加载（见 pack_main.py ①）
    (os.path.join(ROOT, "ops", "book-page-2400", "render_page_2400.py"), "ops/book-page-2400"),
    (os.path.join(ROOT, "server", "app", "__init__.py"), "server/app"),
    (os.path.join(ROOT, "server", "app", "naming.py"), "server/app"),
    (os.path.join(ROOT, "server", "app", "colorcal.py"), "server/app"),
    (os.path.join(ROOT, "server", "app", "seal_canvas.py"), "server/app"),
    (os.path.join(ROOT, "config", "book_dir_keys.json"), "config"),
]
binaries = []

# ── 隐藏导入 ────────────────────────────────────────────────────────────────────
# ⚠ **本单实测的头号坑**：`webui/app.py`（壳）与 `ops/book-page-2400/render_page_2400.py`（引擎）
#   都是**按文件路径**加载/执行的（前者为避免模块名 `app` 撞车、后者为满足「逐件独立子进程」），
#   PyInstaller 的静态分析**看不见它们内部的 import** ⇒ 首版产物仅 88 MB：`cv2` / `tifffile` /
#   `webview`＋pyobjc **全被静默丢掉**（只有 pymupdf/numpy/PIL 因 `api.py → src.pdf_library` 的
#   函数内 import 被捡到）。⇒ 这两个文件的**全部第三方依赖必须在这里显式列全**
#   （缺一个的后果是「打包成功、运行时 ImportError」）。
hiddenimports = [
    "api", "src", "src.pdf_library", "src.validator",           # 壳 + 逻辑层
    "webview", "webview.platforms.cocoa",                        # PyWebView 原生窗口（macOS=WKWebView）
    "cv2", "tifffile", "pymupdf", "numpy", "PIL", "PIL.Image",   # 引擎（render_page_2400.py）渲染栈
]
# ↑ 引擎的 `app.colorcal` / `app.naming` / `app.seal_canvas` **故意不列**：它们必须留在
#   `_MEIPASS/server/app/*.py`（datas）走源码导入 —— 一进 PYZ，`naming.DEFAULT_DIR_KEYS_PATH`
#   的 `parents[2]` 就会算到 `.app/Contents/` 而不是 `_MEIPASS`，目录键会**静默失效**（见 excludes）。

if WITH_OCR:
    hiddenimports += ["src.ocr_rapid", "src.ocr_corrector"]
    # `rapidocr` 无 contrib hook ⇒ 必须 collect_all：**ONNX 模型（≈31 MB）与 yaml 在 wheel 内**，
    # 不 collect 就是「装得上、跑起来找不到模型」。onnxruntime 走 contrib 的 `hook-onnxruntime.py`
    # （自带 `libonnxruntime.*.dylib` 收集）⇒ 只列 hiddenimport、**不再** collect_all（避免重复 TOC）。
    _d, _b, _h = collect_all("rapidocr")
    datas += _d
    binaries += _b
    hiddenimports += _h
    hiddenimports += ["onnxruntime", "onnxruntime.capi._pybind_state", "shapely", "pyclipper"]

# ── 排除（**打包侧**排除；`venv` 里装着也不算进来）────────────────────────────────
excludes = [
    "app", "app.naming", "app.colorcal", "app.seal_canvas",   # ⚠ 与 server/app 撞名 ⇒ 只允许走源码文件
    "streamlit", "webui", "main",                             # 退役 Streamlit 壳（webui/main.py / src/webui.py）
    "matplotlib", "tkinter", "IPython", "pytest", "PyQt5", "PySide6", "pandas", "scipy",
]

if WITH_PADDLE:
    # 阶段 3：**只为体积对照**把 paddle 全家 collect 进来（`paddleocr` 3.x 的 C++ `.dylib` 走 binaries）
    for pkg in ("paddle", "paddlex", "paddleocr"):
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
else:
    excludes += ["paddle", "paddlex", "paddleocr"]            # 阶段 1/2：打包侧排除（省 ≈631 MB）

a = Analysis(
    [os.path.join(WEBUI, "build", "pack_main.py")],
    pathex=[WEBUI, os.path.join(ROOT, "server")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,             # `--windowed`：无控制台 ⇒ 日志落 ~/Library/Logs/斐萃/（见 pack_main.py）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=BUNDLE_NAME,
)

app = BUNDLE(
    coll,
    name=f"{BUNDLE_NAME}.app",
    icon=ICON,
    bundle_identifier="com.cloudcottage.feicui.local",
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "CFBundleName": APP_NAME,
        "CFBundleShortVersionString": "0.3.0",
        "CFBundleVersion": "0.3.0",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "LSApplicationCategoryType": "public.app-category.productivity",
    },
)
