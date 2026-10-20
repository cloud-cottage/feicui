# -*- mode: python ; coding: utf-8 -*-
# local-dist/build/feicui.spec —— 「斐萃 · 本地封装分发版」打包（PyInstaller 6.x / Python 3.11，**macOS ＋ Windows**）
#
# 跑法（**必须**用独立构建环境；共用 `venv` 一字不改 —— 见 README §0）：
#   cd /Users/kevin/bistro/feicui
#   PYTHONPATH=$PWD/venv/lib/python3.11/site-packages \
#   FEICUI_PACK_STAGE=1 \
#   local-dist/build/.venv-build/bin/python -m PyInstaller --noconfirm --clean \
#       --distpath local-dist/build/dist --workpath local-dist/build/build local-dist/build/feicui.spec
#
# Windows（CI 里就是这么跑的，见 `.github/workflows/windows.yml`；本机不装 Windows 也能读）：
#   set FEICUI_PACK_STAGE=1
#   python -m PyInstaller --noconfirm --clean ^
#       --distpath local-dist/build/dist/win --workpath local-dist/build/build/win local-dist/build/feicui.spec
#   ⇒ `local-dist/build/dist/win/斐萃-s1/斐萃.exe` ＋ `_internal/`（**onedir**，不是 onefile）
#
# ── 平台分支（**本 spec 唯一的 `sys.platform` 分叉点**）────────────────────────────
#   | 平台 | 形态 | 图标 | 输出 |
#   | --- | --- | --- | --- |
#   | darwin | `COLLECT` ＋ **`BUNDLE`**（`.app`） | `build/feicui.icns` | `dist/斐萃-s1.app`（＋ `dist/斐萃-s1/`） |
#   | win32  | **只有 `COLLECT`**（onedir） | `build/feicui.ico`  | `dist/win/斐萃-s1/斐萃.exe` ＋ `_internal/` |
#   | linux  | 只有 `COLLECT`（onedir，未验收） | 无 | `dist/斐萃-s1/斐萃` |
#
#   ⚠ 三条**不能动**的取舍：
#   1) **Windows 不用 onefile**：onefile 每次启动都要把 ~200 MB 解到 `%TEMP%\_MEIxxxx`（慢、且
#      「引擎子进程 + 启动解压」= 一层不必要的失败面）。onedir 下 `sys.executable` 就是 `斐萃.exe`，
#      `api.JobRunner` 走 `[斐萃.exe, --engine-run, <脚本>]` 自调，路径全是绝对路径 ⇒ 最稳。
#   2) **`webview.platforms.cocoa` 绝不能进 Windows 分析**：它 `import AppKit/WebKit`（pyobjc，Windows
#      上不存在）⇒ 要么构建期 `ModuleNotFoundError`、要么运行期 ImportError。平台后端按 `sys.platform` 选。
#   3) **`BUNDLE` 段只在 darwin 追加**：在 Windows 上调 `BUNDLE(...)` 会直接抛
#      `AssertionError: BUNDLE is supported only on macOS`（PyInstaller 6 的 `building.osx` 断言）。
#
# 阶段（`FEICUI_PACK_STAGE`）：
#   1 = 壳 + UI + api + 逻辑层 + Python 运行时（含渲染栈）—— **不含 OCR**
#   2 = 阶段 1 ＋ RapidOCR（`rapidocr` 含 ONNX 模型 ＋ `onnxruntime`）
#   3 = 阶段 2 ＋ `--collect-all` paddle / paddlex / paddleocr（**只为体积对照**；见 README §3 路 A）
#
# 关键结构约定（**冻结态路径**，与 `local-dist/build/pack_main.py` 配套）：
#   _MEIPASS/{ui,assets,data,src,app.py}            ← 壳与 UI（`app.py` 走 data，避免模块名 `app` 撞车）
#   _MEIPASS/ops/book-page-2400/render_page_2400.py ← 引擎脚本（`REPO = parents[2]` ⇒ 正好落 _MEIPASS）
#   _MEIPASS/server/app/{__init__,naming,colorcal,seal_canvas}.py ← 引擎的 `app.*`（**必须是源码文件**）
#   _MEIPASS/config/book_dir_keys.json              ← `naming.DEFAULT_DIR_KEYS_PATH = parents[2]/config/…`

import os
import sys

from PyInstaller.utils.hooks import collect_all

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
IS_LINUX = not (IS_MAC or IS_WIN)

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))          # 仓根
WEBUI = os.path.join(ROOT, "local-dist")
STAGE = os.environ.get("FEICUI_PACK_STAGE", "1")
WITH_OCR = STAGE in ("2", "3")
WITH_PADDLE = STAGE == "3"
SUFFIX = {"1": "-s1", "2": "-s2", "3": "-s3-paddle"}[STAGE]

# ── `.app` 图标（**用户可见的那个**）──────────────────────────────────────────
# 来源：**`local-dist/assets/feicui.svg`**（矢量，viewBox 0 0 480 480；与 480×480 的 `feicui.png` 同一设计）。
# 生成：`bash local-dist/build/make-icns.sh`（只用 macOS 自带 qlmanage / sips / iconutil，**无新 Python 依赖**）
#   qlmanage -t -s 1024 -o <dir> local-dist/assets/feicui.svg      # ⇒ 1024×1024 原生母图（矢量重渲染）
#   sips -z N N <母图> --out feicui.iconset/icon_<s>x<s>[@2x].png   # 16…512 ＋ @2x 共 9 槽
#   cp <母图> feicui.iconset/icon_512x512@2x.png              # ★ 1024 槽＝母图原样，不重采样
#   iconutil -c icns feicui.iconset -o local-dist/build/feicui.icns
# ⇒ `feicui.icns`（10 图像槽 ＋ info；2026-10-17 重生成后 1 013 361 B）**随仓提交**（spec 的构建输入；
#   `local-dist/build/dist/**` 才是产物）。母图留档 `local-dist/build/feicui-1024.png`。
# ⚠ 旧版 icns 的 1024 槽是 sips 从 480×480 PNG **放大**（边缘能量 3.539）；现为 SVG **原生重渲染**
#   （边缘能量 5.394，且 `ic10` 解码像素与母图**逐像素一致**/max diff 0）⇒ ≥1024 槽不再是放大。
#   取图工具比选与失败原样留档见 `local-dist/build/readings-theme.md` §4.1（PyMuPDF 渲染全黑、
#   ImageMagick 报 `vector graphics nested too deeply`，只有 qlmanage 可用）。
ICON_ICNS = os.path.join(WEBUI, "build", "feicui.icns")
ICON_ICO = os.path.join(WEBUI, "build", "feicui.ico")

# ── Windows `.ico`（**同一个母图**的 6 帧位图：16/32/48/64/128/256）──────────────────────
# 来源：`local-dist/build/feicui-1024.png`（与 icns 的 1024 槽**同一张** 1024 母图）。
# 生成：`./venv/bin/python local-dist/build/make-ico.py`（Pillow；只缩不放）
# 产物：`local-dist/build/feicui.ico` —— 114 314 B / 6 帧 / 全 32bpp PNG 帧 ⇒ **随仓提交**
#   （体积小、构建输入稳定；CI 用 `make-ico.py --check` 校验帧与尺寸，不现场生成）。
if IS_MAC:
    ICON = ICON_ICNS
    if not os.path.exists(ICON):
        raise SystemExit(f"缺 .app 图标：{ICON}（用 `bash local-dist/build/make-icns.sh` 从 local-dist/assets/feicui.svg 生成）")
elif IS_WIN:
    ICON = ICON_ICO
    if not os.path.exists(ICON):
        raise SystemExit(f"缺 Windows 图标：{ICON}（用 `python local-dist/build/make-ico.py` 从 build/feicui-1024.png 生成）")
else:
    ICON = ICON_ICO if os.path.exists(ICON_ICO) else None      # Linux 未验收：有就带上，没有不拦

APP_NAME = "斐萃"

# ── 产物名（按平台派生）────────────────────────────────────────────────────────────
# macOS：可执行文件与 `.app` 都带阶段后缀（历史口径，别动 —— 老 DMG/脚本按它找）。
# Windows：**exe 就叫 `斐萃.exe`**（双击/快捷方式/任务栏固定都按它走）；阶段后缀只留在**目录名**上。
EXE_NAME = "斐萃" if IS_WIN else "斐萃" + SUFFIX
BUNDLE_NAME = "斐萃" + SUFFIX

# ── 随包数据（相对路径必须与上面的结构约定一致）────────────────────────────────
datas = [
    (os.path.join(WEBUI, "ui"), "ui"),
    (os.path.join(WEBUI, "assets"), "assets"),
    (os.path.join(WEBUI, "data"), "data"),
    (os.path.join(WEBUI, "app.py"), "."),                 # 壳：**按文件路径**加载（见 pack_main.py ①）
    (os.path.join(ROOT, "ops", "book-page-2400", "render_page_2400.py"), "ops/book-page-2400"),
    (os.path.join(ROOT, "server", "app", "__init__.py"), "server/app"),
    (os.path.join(ROOT, "server", "app", "naming.py"), "server/app"),
    (os.path.join(ROOT, "server", "app", "colorcal.py"), "server/app"),
    (os.path.join(ROOT, "server", "app", "seal_canvas.py"), "server/app"),
    (os.path.join(ROOT, "config", "book_dir_keys.json"), "config"),
]
binaries = []

# ── `src/` **精确到文件**（禁止再收整目录）────────────────────────────────────────
# ⚠ 历史坑（2026-10-17 修复）：此处原为 `(WEBUI/src, "src")` **整目录 data** ⇒ 把退役的
#   Streamlit 页 `local-dist/src/webui.py`（内含旧色 `#FF6700` 等）连同只被它引用的
#   `tencent_doc_api.py` / `baidu_disk_api.py`、以及 `src/__pycache__/` 一并塞进产物。
#   ⇒ **`excludes` 拦不住 data 目录**：excludes 只作用于 import 分析（PYZ），对 datas 无效；
#     必须在这里逐文件列出。仓内源文件**一律保留**（`webui.py` 是需求真源，见
#     `local-dist/selftest.py` 红线段），只是**不进包**。
#   运行时真源（照 `local-dist/api.py` 顶层 import 面）：
#     `src/__init__.py`（包身份）＋ `src/pdf_library.py`（tab1/tab3 盘点/探针/侧车）
#     ＋ `src/validator.py`（文件名解析/新名预览，单一真源）。
#   OCR 两件**仅阶段 2/3** 需要（`--engine-run src/ocr_rapid.py` 走文件级执行；
#   `src/ocr_corrector.py` 是它的字表链路）——阶段 1 收进去也跑不了（无 rapidocr）。
#   2026-10-18 追加：`src/yinyuan_client.py`（B4 yinyuan 接入；`api.py` 顶层 `from src import`
#   ⇒ 缺它会在打包态 import 阶段直接炸，源码态看不出来）。
#   2026-10-20 追加（v1.0.1）：`src/highres_pdf.py`（tab1 一键高清化）＋ `src/seal_detect.py` /
#   `src/seal_crop.py`（tab2 切图台）。`api.py` 经 `_src_module()` **动态 import**（静态分析看不见）
#   ⇒ 不显式列就是「打包成功、运行时 ImportError」。三者只依赖 cv2/numpy/tifffile/pymupdf
#   （hiddenimports 已含），**无 rapidocr/paddle 依赖** ⇒ 全阶段收，不含 OCR 的 s1 也能用。
SRC_FILES = ["__init__.py", "pdf_library.py", "validator.py",
             "yinyuan_client.py",
             "highres_pdf.py", "seal_detect.py", "seal_crop.py",  # v1.0.1：tab1 高清化 + tab2 切图台
             "field_extract.py",                                  # 2026-10-20：tab2 三字段提取 + 阅读顺序（seal_crop.grid_order 依赖它）
             "paths.py"]                                          # 全阶段必需（paths.py = 用户目录单一真源）
if WITH_OCR:
    SRC_FILES += ["ocr_rapid.py", "ocr_corrector.py"]
for _src_name in SRC_FILES:
    datas.append((os.path.join(WEBUI, "src", _src_name), "src"))

# ── 隐藏导入 ────────────────────────────────────────────────────────────────────
# ⚠ **本单实测的头号坑**：`local-dist/app.py`（壳）与 `ops/book-page-2400/render_page_2400.py`（引擎）
#   都是**按文件路径**加载/执行的（前者为避免模块名 `app` 撞车、后者为满足「逐件独立子进程」），
#   PyInstaller 的静态分析**看不见它们内部的 import** ⇒ 首版产物仅 88 MB：`cv2` / `tifffile` /
#   `webview`＋pyobjc **全被静默丢掉**（只有 pymupdf/numpy/PIL 因 `api.py → src.pdf_library` 的
#   函数内 import 被捡到）。⇒ 这两个文件的**全部第三方依赖必须在这里显式列全**
#   （缺一个的后果是「打包成功、运行时 ImportError」）。
hiddenimports = [
    "api", "src", "src.pdf_library", "src.validator",           # 壳 + 逻辑层
    "src.yinyuan_client",                                        # yinyuan 接入（B4）
    "src.paths",                                                 # 用户目录单一真源（pack_main 也 import 它）
    "src.highres_pdf", "src.seal_detect", "src.seal_crop",       # v1.0.1：tab1 高清化 + tab2 切图台（api._src_module 动态 import ⇒ 必须显式列）
    "src.field_extract",                                         # 2026-10-20：字段提取（缺它 ⇒ seal_crop.grid_order 静默退回「仅 ltr-ttb」＝RTF 方向静默错）
    "cv2", "tifffile", "pymupdf", "numpy", "PIL", "PIL.Image",   # 引擎（render_page_2400.py）渲染栈
]

# ── PyWebView 原生窗口后端：**按平台二选一，绝不混装** ────────────────────────────────
# 这个包（`webview`）在本仓两个「按文件路径加载」的脚本里被 import（`app.py`），所以静态分析看不见
# ⇒ 必须显式列。但后端的实现模块是**平台绑定**的：
#   macOS   → `webview.platforms.cocoa`（pyobjc：AppKit/WebKit/Quartz…）
#   Windows → `webview.platforms.edgechromium`（WebView2 via pythonnet/clr）＋ `webview.platforms.winforms`
#             （GUI 容器）；`mshtml` 是 IE 老后端，**不列**（Win10/11 上无意义且会拉 COM 依赖）
#   Linux   → `webview.platforms.gtk`（未验收；本仓不安装 PyGObject，故不列，让 pywebview 自己回落/报错）
# ⚠ 历史坑：这一行原来是**无条件** `"webview.platforms.cocoa"` ⇒ 在 windows-latest 上构建会
#   `ModuleNotFoundError: No module named 'AppKit'`（pyobjc 只在 darwin 装）。
if IS_MAC:
    hiddenimports += ["webview", "webview.platforms.cocoa"]
elif IS_WIN:
    hiddenimports += [
        "webview",
        "webview.platforms.edgechromium",       # WebView2（EdgeChromium）后端
        "webview.platforms.winforms",           # WinForms 窗口容器（edgechromium 依赖它）
        "clr",                                  # pythonnet（pywebview 在 win32 上的硬依赖，见 METADATA）
        # pythonnet 的 .NET 运行时装载器：contrib 的 hook-clr.py 会带走 `Python.Runtime.dll`；
        # `clr_loader` 负责找 runtime（`coreclr` / `netfx` 两种），两个都列上防漏。
        "clr_loader",
    ]
else:
    hiddenimports += ["webview"]
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
    "streamlit", "webui", "main",                             # 退役 Streamlit 壳（local-dist/main.py / src/webui.py）
    "src.webui", "src.tencent_doc_api", "src.baidu_disk_api",  # 退役页 ＋ 只被它引用的两个云端 API（不进包，源文件保留）
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

if not WITH_OCR:
    # 阶段 1 双保险（2026-10-18）：**rapidocr 整条依赖链一律不进包**。
    # 根因不在本 spec 的 datas/hiddenimports（阶段 1 本来就没列 `src/ocr_rapid.py`），
    # 而是 `local-dist/api.py` 曾把 `from src import ocr_rapid` 写在 `tab3_ocr()` 函数体内
    # ——**PyInstaller 的 AST 分析会追踪函数体内的 import** ⇒ ocr_rapid 被收进 PYZ
    # ⇒ 它 import rapidocr ⇒ 触发 contrib 的 `hook-onnxruntime.py`（自带 dylib 收集）
    # 与 `hook-shapely.py` ⇒ 连带 onnxruntime(70 MB) + shapely(4.3 MB) + pyclipper + ONNX 模型，
    # s1 从 210 MB 涨到 298 MB。api.py 已改 `importlib.import_module`（动态，不被分析）。
    # ⚠ `excludes` 只作用于 PYZ 的 import 分析，**对 datas/binaries 无效**；阶段 1 没有
    #   `collect_all(...)` 也没有把模型列进 datas，所以这里能真正拦住。
    excludes += ["rapidocr", "onnxruntime", "shapely", "pyclipper"]

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

exe_kwargs = dict(
    exclude_binaries=True,
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # `--windowed`：无控制台 ⇒ 日志落 `log_dir()`（见 pack_main.py）。
    # Windows 上这也意味着 GUI 子系统 exe（双击不弹黑框）；引擎子进程的 stdout 由父进程重定向到日志文件。
    console=False,
    disable_windowed_traceback=False,
)
if IS_MAC:
    # 仅 macOS 有意义的开关（PyInstaller 在其他平台上会忽略/断言，故只在 darwin 传）
    exe_kwargs.update(argv_emulation=False, target_arch=None,
                      codesign_identity=None, entitlements_file=None)
if IS_WIN:
    # Windows：图标嵌进 `.exe`（资源节）。macOS 的图标由下面的 `BUNDLE(icon=…)` 负责（`.icns`），
    # **不给 EXE 传 mac 图标** ⇒ mac 产物与历史构建保持一致。
    exe_kwargs["icon"] = ICON

exe = EXE(pyz, a.scripts, [], **exe_kwargs)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=BUNDLE_NAME,
)

# ── `.app` 只属于 macOS ──────────────────────────────────────────────────────────────
# `BUNDLE` 内部是 `PyInstaller.building.osx`，非 darwin 直接断言失败 ⇒ **必须**包在 if 里。
# Windows/Linux 到此为止：`COLLECT` 产出的 onedir 目录（`斐萃-s1/`，内含 `斐萃.exe` ＋ `_internal/`）
# 就是最终产物，双击 `斐萃.exe` 即启动。
if IS_MAC:
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
