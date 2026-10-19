# webui/build/readings-theme.md —— 本地版「暖橙 → 翡翠绿」换色 ＋ SVG 高清图标（读数留档）

> 单：Kong 2026-10-17。真源：Kevin 选定**候选 C**（逐字给定，不得自换）＋ 规范 `docs/feicui.spec.md`
> **§0.5.2 V-1**「配色＝蓝绿色的宝石感」（判负形态含「出现非蓝绿系的产品主色」）⇒ 本地版改绿是**向既有条款靠拢**。
> 本单**未改** `docs/**`（规范登记另派 Jing）；**未动** `web/`（线上 Vue 站已是翡翠绿）、`server/`、`output/**`、
> `src/validator.py` 与任何逻辑层行为。

---

## 1. 新 token 组（集中定义在 `:root`）

| token | 值 | 用途 | H 色相 |
| --- | --- | --- | --- |
| `--accent` | `#1fbe8f` | 主色：主按钮 / 激活页签 / 进度条 / 选中描边 | 162.3° |
| `--accent-deep` | `#118a66` | 深阶：hover / 按下 / 凹面 | 162.1° |
| `--accent-soft` | `#e7f8f2` | 浅淡底：列表 & 子目录 hover 垫色 / 选中格底 | 158.8° |
| `--accent-line` | `#43e6bd` | 描边 / 焦点环 / 高光 | 164.9° |
| `--on-accent` | `#04201a` | 主色块上的文字 | 167.1° |
| `--accent-wash` | `#f3fcf8` | **派生**：`mix(--accent-soft, #fff, 50%)` | 153.3° |
| `--accent-soft-2` | `#c3eee0` | **派生**：`mix(--accent-soft, --accent, 18%)` | 160.5° |
| `--orange` / `--orange-dark` | `var(--accent)` / `var(--accent-deep)` | **旧变量名保留为别名**（减 diff；app.js / 内联样式若引用仍可用） | — |

底色 / 文字保持原值：`--bg #f5f5f5`、`--card #ffffff`、`--line #e5e5e5`、`--text #1a1a1a`、`--muted #7a7a7a`。

## 2. 逐点 before → after（★ 验收①：下列 9 个暖橙 hex 残留 **0**）

| 位置 | before（暖橙） | after |
| --- | --- | --- |
| `:root` 主色 / 深阶 | `#FF6700` / `#e55c00` | `--accent #1fbe8f` / `--accent-deep #118a66` |
| 输入框焦点环 `outline` | `#ffd9bf` | `var(--accent-line)` |
| 列表 / 子目录 hover 垫色 | `#faf0e8` | `var(--accent-soft)` |
| 表格 / 树 / 缩略图 hover | `#fcf7f2` | `var(--accent-wash)` |
| 列表 / 表格选中行 | `#ffe8d9` | `var(--accent-soft-2)` |
| `.cur` 当前目录底 | `#faf7f3` | `var(--accent-wash)` |
| `.cur` 虚线框 | `#e0c9b4` | `var(--accent-line)` |
| `.thumb-item.selected` 底 | `#fff5ec` | `var(--accent-soft)` |
| 主色块上的文字（`.btn.primary` / `.tab.active` / 子目录 / 档位 / 引导页按钮 / 步骤序号） | `#fff` | `var(--on-accent)` |
| `.logo` 文字 / 进度条 `.bar` / 选中描边 | `var(--orange)` | `var(--accent)` |

grep 口径（`webui/ui/style.css` ＋ `webui/ui/index.html` ＋ `webui/index.html` ＋ `webui/ui/app.js`）：
`FF6700=0 e55c00=0 ffd9bf=0 faf0e8=0 ffe8d9=0 fcf7f2=0 faf7f3=0 e0c9b4=0`（另 `#fff5ec / #fff3e0 / #e65100 / #b06a00` 亦 0）。
> 注释里也**不留**旧 hex 字面量（否则纯 grep 会命中注释）——before→after 只在本文件登记。

**`webui/index.html`（公网引导页）**：原本无 `:root`（内联 `<style>` 里 4 处硬编码暖橙）；现补上**同一 token 组**
（含 `--warn*`），`.btn-primary` / `.btn-secondary:hover` / `.steps li::before` / `.copy-btn` 全部走 token。
`webui/ui/index.html` 无任何内联色（仅有 `style="width:0%"` 一个布局属性）⇒ 无需改动。

## 3. ★ 语义色**未**改绿（验收④）

| token | 值 | 说明 |
| --- | --- | --- |
| `--ok` | `#1f9d55` | **原值，一字未动**（成功） |
| `--err` | `#d93025` | **原值，一字未动**（错误；`app.js` 里的 toast 错误色亦然） |
| `--warn` / `--warn-bg` / `--warn-line` | `#8a5a00` / `#fff7e6` / `#e0b070` | 原先散落 3 处（`.notice`、`.badge-warn`、列表档 `.name.bad`）＋ 引导页 `.tip` 的 `#fff3e0`/`#e65100` 归一为 token |

**为什么不把警示也改成绿**：`--ok` 本身就是绿（`#1f9d55`）——警示若也改绿，则「成功」与「警示」在界面上不可分，
`.notice` / `.badge-warn`（tab3 的「腾讯文档未接入」标注）会与成功态撞色。故保留琥珀语义，只做 token 化。
引导页 `.tip`（⚠ 未上传公网提示）的左侧警示条原用产品主色 `#FF6700`，同因改为 `var(--warn-line)`。

## 4. ★ 高清图标：SVG 无损导出 ≥1024 母图（验收③）

### 4.1 取图工具比选（本机实测，**失败原样留档**）

| 路径 | 结果 | 读数 / 原始报错 |
| --- | --- | --- |
| `qlmanage -t -s 1024 -o <dir> webui/assets/feicui.svg` | ✅ **采用** | 产出 1024×1024；与 480 PNG 同族直方图；边缘能量 **5.3942** vs 480 PNG 放大到 1024 的 **3.7802** |
| venv 已有 PyMuPDF（`pymupdf.open(svg)`） | ❌ 不可用 | MuPDF 能打开（`page.rect = 480×480`）但**忽略 SVG 内嵌 `<style>` 的 class 填充** ⇒ 全黑：`(0,0,0,255)` 占 1007937 px、仅 255 色（对照 qlmanage 4085 色） |
| `magick -density 300 -background none <svg> -resize 1024x1024` | ❌ 不可用 | `magick: vector graphics nested too deeply 'cls-12' @ error/draw.c/RenderMVGContent/2804.` |
| 系统 `rsvg-convert` / `inkscape` | 未测 | `command -v` **MISSING**（未安装） |

⇒ 只有 **qlmanage** 跑通且保真，全流程仅用 macOS 自带工具，**零新增 Python 依赖**。
生成脚本：`bash webui/build/make-icns.sh`（含上述失败记录注释）。母图留档：`webui/build/feicui-1024.png`。

### 4.2 icns 槽位表（反解 ICNS 容器；`iconutil` 反解 iconset 亦一致）

| 元素 | 载荷 | 旧 icns（before） | 新 icns（after） |
| --- | --- | --- | --- |
| `ic11` | PNG 32×32 | 2 672 B | 2 524 B |
| `ic12` | PNG 64×64 | 8 352 B | 8 059 B |
| `ic07` | PNG 128×128 | 26 405 B | 25 534 B |
| `ic13` / `ic08` | PNG 256×256 | 79 552 B | 76 263 B |
| `ic14` / `ic09` | PNG 512×512 | 208 953 B | 208 296 B |
| **`ic10`** | **PNG 1024×1024** | 587 110 B（480→1024 放大） | **403 848 B（SVG 原生重渲染）** |
| `ic04` / `ic05` | 16/32 位 RLE | 872 / 3 287 B | 781 / 3 091 B |
| `info` | 元数据 | 310 B | 310 B |
| 合计 | 槽数 **10 图像槽 ＋ info** | 1 206 114 B | **1 013 361 B** |

**原生分辨率证据**（不是只报尺寸）：
- `ic10` 载荷 PNG 的 IHDR = 1024×1024；解码像素与母图 `feicui-1024.png` **逐像素完全一致**（`ImageChops.difference().getbbox() is None`，max diff **0**）⇒ 1024 槽＝原生母图，未经重采样；
- 边缘能量（FIND_EDGES 均值，同尺寸 1024×1024 对比）：旧 ic10 **3.539** → 新 ic10 **5.394**（**+52.4%**）⇒ 旧版确为放大（模糊），新版为矢量重渲染。
- ⚠ 未做「目视验收」：以上全部为**可复算读数**，无人工目视结论。

## 5. ★ 渲染后 DOM 断言（验收②）

脚本 `webui/build/domcheck-theme.py`（配方**复用 `webui/domtest.py`**：`build_window(api)` ＋ **主线程**
`webview.start(probe)` ＋ `threading.Timer` 看门狗 ＋ `evaluate_js` 读 `getComputedStyle` **实际计算值**）。
读数落盘 `webui/build/readings-theme.json`。本轮 **PASS 17 / FAIL 0**：

| 断言 | 渲染后计算值（实测原文） |
| --- | --- |
| `:root` token 解析 | `--accent #1fbe8f`、`--accent-deep #118a66`、`--accent-soft #e7f8f2`、`--accent-line #43e6bd`、`--on-accent #04201a`、`--accent-wash #f3fcf8`、`--accent-soft-2 #c3eee0`、别名 `--orange #1fbe8f`、`--ok #1f9d55`、`--err #d93025` |
| 主按钮 `.btn.primary`（`#btn-login`） | `backgroundColor = rgb(31, 190, 143)`、`color = rgb(4, 32, 26)`、`borderColor = rgb(31, 190, 143)` |
| 激活页签 / 子目录 / 档位 | `rgb(31, 190, 143)` / 文字 `rgb(4, 32, 26)`（`3_Cropped_Tiff`、`📁 A特例`、`🖼️ 大图标`） |
| 选中缩略图 `.thumb-item.selected` | `outlineColor = rgb(31, 190, 143)`、`border = rgb(31, 190, 143)`、`background = rgb(231, 248, 242)`（＝`--accent-soft`） |
| 焦点环（聚焦中的 `#tab3-shiwen` / `#tab1-notes`） | `outlineColor = rgb(67, 230, 189)`（＝`--accent-line`）、`borderColor = rgb(31, 190, 143)` |
| `.cur` 派生浅阶 | `background = rgb(243, 252, 248)`（＝`--accent-wash`）、`borderStyle = dashed`、`borderColor = rgb(67, 230, 189)` |
| 进度条 `.progress .bar` / `.logo` | `rgb(31, 190, 143)` / `rgb(31, 190, 143)` |
| tab1 选中行 `.grid tbody tr.active`（真出 PDF 行后点选） | `rgb(195, 238, 224)`（＝`--accent-soft-2`） |
| 语义色未被改绿 | `.notice` / `.badge-warn` `color = rgb(138, 90, 0)`、`background = rgb(255, 247, 230)` |
| **旧暖橙计算值残留扫描**（遍历全部节点 × 9 个颜色属性 ＋ boxShadow/borderColor） | 主界面 **263 节点 → 命中 0**；引导页 **54 节点 → 命中 0**；绿色 token 命中计数 `{accent:87, on:32, soft:1, line:11, wash:2, soft2:1, ok:27, err:9, warn:26}` |
| 引导页 `webui/index.html`（同窗口 `load_url` 二次加载） | `.btn-primary` `rgb(31, 190, 143)` / `rgb(4, 32, 26)`；`.steps li::before`（**伪元素** computed）`rgb(31, 190, 143)`；`.tip` 仍为琥珀 `rgb(255, 247, 230)` / `rgb(138, 90, 0)` / 左边框 `rgb(224, 176, 112)` |

## 6. 重打阶段 1 ＋ `.app` 三读数（验收③后半）

命令（与 `webui/build/feicui.spec` 头注一致；日志 `webui/build/build-s1-theme.log`，`EXIT=0`）：

```bash
PYTHONPATH=$PWD/venv/lib/python3.11/site-packages FEICUI_PACK_STAGE=1 \
  webui/build/.venv-build/bin/python -m PyInstaller --noconfirm --clean \
  --distpath webui/build/dist --workpath webui/build/build webui/build/feicui.spec
```

| 读数 | 值 |
| --- | --- |
| `Contents/Resources/feicui.icns` | 存在，md5 `cd0075fb9e80b06d2fda5f2c1c50d234`（＝ `webui/build/feicui.icns` md5，**随包一致**） |
| `Info.plist → CFBundleIconFile` | `feicui.icns` |
| 启动实测 | `open …/斐萃-s1.app` ⇒ `ps` 见 `…/Contents/MacOS/斐萃-s1` 存活（etime 00:14）；日志 `pack-20261017.log` 新增 `feicui pack entry … mode=gui | frozen=True`、`BOOT: resource_root=…/Contents/Frameworks`、`WEBUI_START mode=native ui=…/Frameworks/ui/index.html`，**无 FATAL**；随后按 PID `kill`（未用 `pkill -f`），`ps` 复查已退出 |
| 包内主题资源 | `Contents/Resources/ui/style.css` 含 `1fbe8f`（2 行命中）、`FF6700` **0** 命中 |

## 7. NOT_MEASURED（如实登记）

| 项 | 原因 |
| --- | --- |
| `:hover` / `:active` 态（`--accent-deep #118a66`）的计算值 | pywebview(macOS)＝WKWebView，**无 CDP**；合成 `MouseEvent` 不触发 `:hover`。只能登记其引用的 token 值（`:root` 计算后 `--accent-deep = #118a66`）。全 DOM 扫描里 `deep` 命中 0 亦因此（该 token 只出现在 hover 规则里） |
| `.app` 窗口**内**渲染的绿色计算值 | 打包产物无调试通道（非 CDP 可连）；`webui/build/domcheck-theme.py` 测的是**源码态同一 UI 文件**。包内一致性用「`Resources/ui/style.css` 命中 `1fbe8f` ×2 / `FF6700` ×0」间接证明 |
| Windows 版图标 / 配色 | 本单只做 macOS；Windows 需另在 Windows 上打（EdgeWebView2） |
| 线上 `web/` 与规范登记 | **本单范围外**（红线：不改 `web/`、`docs/**`） |
