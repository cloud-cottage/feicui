# webui/build —— 「斐萃本地电脑版」打包要点（PyInstaller ＋ PyWebView）

> 状态：**未打包**（本单只写要点与实测读数）。入口 `webui/app.py`，UI `webui/ui/**`，
> 桥 `webui/api.py`，引擎脚本 `ops/book-page-2400/render_page_2400.py`（老工程 `venv`）。
> 本文档里的体积 / 依赖读数均为**本机实测**（2026-10-16，Apple Silicon / macOS 15.7.4），
> 取证命令逐条列出，可复跑。

---

## 0. 先定一件事：本地版**要 OCR**

原始需求「体积裁剪：不含 paddleocr/paddlepaddle」**已被 Kevin 2026-10-16 的口径更新取代**：

> 本地版**要 OCR** ⇒ 打包**必须含 OCR 能力**。

⇒ 打包体积从「≈ 数百 MB」直接跳到「**≥ 1 GB**」量级（见 §3 实测）。这一条决定后面所有取舍。
**但在动手打包之前，请先读 §4 的《OCR 用途未确认》** —— 若 Kevin 要的是**印面释文识别**，
那么**打哪个 OCR 都不解决**（PP-OCR 对篆书印面实测基本不可用），这会直接影响这笔 1 GB 投入是否值得。

---

## 1. 打包形态与入口

| 项 | 取值 / 说明 |
| --- | --- |
| 入口 | `webui/app.py`（`pywebview.create_window(..., js_api=FeicuiApi())` → `webview.start()`） |
| UI 资源 | `webui/ui/{index.html,style.css,app.js}`（纯本地、**零 CDN 外链**）⇒ 作为 `datas` 随包 |
| 桥 | `webui/api.py`（**不含 UI、不 import webview/streamlit**，可独立 import 做自测） |
| 引擎 | `ops/book-page-2400/render_page_2400.py` ＋ `server/app/{naming,colorcal,seal_canvas}.py` ＋ `config/book_dir_keys.json` |
| 目标 | macOS `.app`（`--windowed`）；Windows 版需另在 Windows 上打（PyWebView 用 EdgeWebView2） |
| 解释器 | **3.11**（与 `venv` 一致；paddle 3.3.1 / pymupdf / cv2 / tifffile 均按 cp311 wheel） |

**关键结构约束：打包后 `api.py` 依赖的相对路径必须仍然成立**（`__file__` 基准）：

```
webui/{app.py,api.py,ui/**,assets/**,.env}
ops/book-page-2400/render_page_2400.py
server/app/{naming,colorcal,seal_canvas}.py
config/book_dir_keys.json
venv/bin/python          ← 见 §2「子进程解释器」
```

PyInstaller 默认把源码收进 `_internal/`（onefile 则收进临时解包目录），
⇒ **`datas` 必须按同样的相对层级摆放**，或改为「**随包旁放一份 `runtime/` 目录树**」并在
`api.py` 里把 `REPO_ROOT` 改成可配置（推荐后者：体积不变、路径可读、引擎脚本可单独跑）。

## 2. 引擎＝子进程（**打包后仍必须能起解释器**）

`api.py` 的 HighRes 渲染走：

```
<engine_python> ops/book-page-2400/render_page_2400.py --pdf … --page … --dpi 1200 --out … --progress …
```

`engine_python` 现在取 `REPO_ROOT/venv/bin/python`（不存在则回落 `sys.executable`）。
打包后的两条路：

- **路 ①（推荐，先做）**：包外仍带 `venv/`（或一份裁剪过的 runtime），`engine_python` 指它。
  `.app` 负责 UI，重活交给外部解释器 ⇒ 不解 PyInstaller 侧的原生栈问题。
- **路 ②**：`sys.executable` 自调（`--windowed` 下要处理「无 stdout」：用 `stdout=logfile` 已内置）。
  注意 PyInstaller 下 `sys.executable` 是**包内**可执行文件，需要 `--runtime-hook` / `sys.frozen`
  分支来转发参数到 `app.py`，且**每次重活都会再起一份 1 GB 级进程**（内存翻倍）。

### 2.1 硬纪律：**逐件独立子进程**（不是风格问题）

本仓**历史实测**：Paddle 原生栈在**同进程反复建立 / 释放推理上下文**会
**`SIGSEGV`（`Segmentation fault: 11`，Python 层无 traceback）** —— 整批单进程跑到第 4 本即崩。
证据：`docs/feicui.spec.md` §3.26.5（＋ AC-132）、`ops/biblio-metadata/README.md` §2、
现场日志 `ops/biblio-metadata/scan_run.log`。

⇒ 打包后**任何 OCR / 渲染调用都必须保持「一件一进程」**：
`subprocess.Popen([...])` **逐个**跑、跑完就回收，**严禁**在打包进程内做「循环里复用同一个引擎实例」。
这条同时也是「路 ①」更强的理由：子进程要能真的起来。

---

## 3. OCR 两条路：实测体积 / 依赖 / 迁移代价

### 路 A：直打 `paddleocr` ＋ `paddlepaddle`（＝现环境）

| 组件 | 实测体积（`du -sh`） | 取证 |
| --- | --- | --- |
| `site-packages/paddle` | **429 MB** | `venv/lib/python3.11/site-packages/paddle` |
| └ `paddle/libs`（原生 `.dylib`） | **130 MB** | `libphi_core.dylib` 单件 **88 MB**、`libblas/liblapack` 各 20 MB |
| `site-packages/paddlex` | **19 MB** | |
| `site-packages/paddleocr` | **1.3 MB** | 纯 Python 壳 |
| 模型（`~/.paddlex/official_models`） | **182 MB** | `PP-OCRv6_medium_det` 59 MB ＋ `PP-OCRv6_medium_rec` 73 MB ＋ `UVDoc` 31 MB ＋ `PP-LCNet_x1_0_doc_ori` 6.6 MB ＋ `PP-LCNet_x1_0_textline_ori` 6.6 MB ＋ `PP-OCRv4_mobile_seal_det` 4.7 MB |
| 现 `venv` 总量（含 pymupdf/cv2/tifffile/PIL/pywebview） | **1.3 GB** | `du -sh venv` |
| └ 其中 `cv2`（**渲染引擎也要用，不是 OCR 独占**） | 221 MB | |
| ⊙ **OCR 独占 ≈** | **≈ 631 MB**（429 ＋ 19 ＋ 1.3 ＋ 182） | |

**打包难点（逐条）**：

1. **C++ `.dylib` 收集**：`paddle/libs/*.dylib` 不进 `binaries` 就 `dlopen` 失败（`libphi_core.dylib` 88 MB，
   是体积与「签名/公证」两处的痛点）。必须 `binaries=[('venv/…/paddle/libs/*.dylib','paddle/libs')]`，
   并 `codesign --deep` 后逐个 `--options runtime` 重签（macOS 公证要求）。
2. **模型文件随包**：模型**不在 wheel 里**，落在 `~/.paddlex/official_models/`（用户机可能没有）。
   ⇒ ① 作为 `datas` 打包；② 设 `PADDLE_PDX_MODEL_SOURCE` / `PADDLE_PDX_CACHE_HOME`（或
   `PADDLEX_HOME`）指向包内 model 目录，否则首次运行**联网下载**（打包版必须**离线可用**）。
3. **hidden imports / collect_all**：`paddle`、`paddlex`、`paddleocr` 三个包都有**动态导入**
   （`paddlex.inference.pipelines` 按名字反射、`importlib.metadata` 查版本、`.so` 旁边还有 `.pyi`）
   ⇒ 需要 `--collect-all paddle --collect-all paddlex --collect-all paddleocr`
   （PyInstaller 对 paddle 常需 `--collect-submodules` ＋ 手写 hook）。
4. **已知坑（本仓实测）**：原生栈 `SIGSEGV`（见 §2.1）⇒ **必须**保持子进程形态；
   另外 `paddlex` 有 extra 门禁（`seal_recognition` 管线未装 extra 时初始化即
   `DependencyError`，实例见 `labeling/raw/seal_recognition_dep_error.txt`）⇒ 打包时
   **要么装齐 extra（＋体积/依赖），要么在 UI 上明确标注该能力不可用**，别让用户以为「有 OCR 就能识印面」。
5. **打包后的量级估算（Packaged）**：
   `.app` ≈ 源码 1 MB ＋ OCR 631 MB ＋ 渲染栈（cv2 221 MB ＋ pymupdf ≈ 40 MB ＋ tifffile/numpy/PIL ≈ 60 MB）
   ＋ PyWebView/pyobjc ≈ 60 MB ⇒ **未压缩 ≈ 1.0 ～ 1.1 GB**；
   DMG（zlib）通常 **≈ 450 ～ 600 MB**（`.dylib` 压缩比一般）。

### 路 B：改 **RapidOCR（onnxruntime ＋ PP-OCR 的 ONNX 模型）**

| 组件 | 实测（wheel 下载 ＋ 解包） | 取证 |
| --- | --- | --- |
| `rapidocr-onnxruntime` 1.4.4 wheel | **14.9 MB**（解包 16 MB，其中 **模型 15 MB**：`ch_PP-OCRv4_rec_infer.onnx` 10 MB ＋ `det` 4.5 MB ＋ `cls` 0.57 MB） | `pip download --no-deps` ＋ `zipfile.extractall` 后 `du -sh` |
| `onnxruntime` 1.31.0 wheel（macOS arm64 / cp311） | **20.9 MB**（解包 **75 MB**） | 同上 |
| ⊙ **两者安装后 ≈ 91 MB** | 另需 `opencv-python`（**已装**，渲染线共用 221 MB）＋ `pyclipper` / `shapely` / `Pillow` / `numpy`（**均已装，≈ 数十 MB，非新增**） | |
| ⊙ **净增（相对现环境已有依赖）** | **≈ 95 ～ 130 MB**（onnxruntime ＋ rapidocr ＋ pyclipper/shapely 若未装） | |

⇒ **体积对照：路 A ≈ 631 MB 独占、路 B ≈ 0.1 GB 独増（约 1/5 ～ 1/6）**。

**迁移代价（与现调用面比对）**：

- 现调用面（`processor.py::ocr_text`）＝ `PaddleOCR(use_angle_cls=False, lang="ch")` →
  `ocr.predict(img)` → 取 `rec_texts`（list）或 `item.json["res"]["rec_texts"]`（3.x 兼容分支）。
- RapidOCR 调用面＝ `from rapidocr_onnxruntime import RapidOCR; engine = RapidOCR()`;
  `res, elapse = engine(img)` ⇒ `res = [(box, text, score), …]`（**无 doc 方向 / 无 UVDoc 矫正**）。
- 迁移工作量：**一个适配函数（≈30 行）**即可产出与 `rec_texts` 同形的列表
  （`[t for _box, t, _s in res]`） ⇒ **代码面代价低**。
- 但**能力面有不可逆损失**：
  ① `PP-OCRv6_medium_det/rec`（medium）换成 RapidOCR 自带的 **PP-OCRv4 mobile**（精度档位下调）；
  ② **doc 方向分类 / UVDoc 去扭曲**（现 pipeline 有）在 RapidOCR 默认管线下**没有**；
  ③ **印章专用模型全在 Paddle 生态**（`PP-OCRv4_mobile_seal_det`、`SealTextDetection` /
  `SealRecognition`）⇒ 路 B **拿不到**（要自己转 ONNX，且 `seal_recognition` 本仓从未跑通，见 §3-A.4）。
- 结论（体积 / 打包难度 / 精度风险）：

| 维度 | 路 A（paddle） | 路 B（RapidOCR/ONNX） |
| --- | --- | --- |
| 体积（独占） | ≈ 631 MB | **≈ 95 ～ 130 MB** |
| 打包难度 | **高**（C++ dylib 收集 ＋ 签名公证 ＋ 模型 data ＋ hidden imports ＋ 原生栈 SIGSEGV 约束） | **低**（纯 wheel，onnxruntime 自带 `.dylib` 但无自研 C++ 链；无模型下载问题——模型**在 wheel 内**；无 extra 门禁） |
| 精度风险 | 基准（PP-OCRv6 medium） | **降档**（PP-OCRv4 mobile）＋ 无 UVDoc/doc-ori；印章专用模型需自行转 |
| 与本仓关系 | 现有 `processor.py` 直接可用；`SealRecognition` 依赖缺失 | 需 30 行适配；`seal_*` 能力**不可得** |

**推荐**：**路 B（RapidOCR）做本地版**，把路 A 留在服务端 / 内部产线。
理由：本地版要「下载得下来、装得上、不炸」，体积差 5 倍、打包复杂度差一个量级，
而**本地版 OCR 的定位本来就不是产线精度**；印章专用模型全在 Paddle 生态且本仓从未跑通，
不构成「必须选 A」的理由。**若最终确认要的是印面释文识别，则 §4 生效——两条路都不解决，先别包。**

---

## 4. ⚠ 单列风险：**「OCR 用途」未确认**（决策前必读）

本仓**历史实测：PP-OCR 对篆书印面基本不可用**：

- `labeling/README.md` §5：248 枚印面裁图，三套配置（A baseline / B 关 doc 预处理 / C 仅 rec）
  **没有任何一枚三套同时给出相同且非空的文本**；C（rec-only）非空率 128/248 ＝ 51.6%，
  **平均 `rec_score` 0.211（很低）**。
- `labeling/README.md` §6：印章专用模型 `PP-OCRv4_mobile_seal_det` 只出**检测框**（48 枚中检出 42 枚），
  `SealRecognition` **初始化即失败**（`paddlex[ocr]` extra 缺失）⇒ **D 列文本全空**。
- `README.md`：新库行里 `seal_name` 非空率仅 **2.53%**，且实测释文可疑（`田用海厦`），
  建议「加 `rec_score` 阈值 ＋ 去重后再当 `seal_name`」——即**连人工复核都还没过**。

**⇒ 判断口径**：

1. 若本地版 OCR 的用途是**印面释文识别**（把印章上的字读出来）⇒ **换任何通用 OCR（含路 A/B）都不解决**，
   需要**篆书专用模型**或**人工录入**；这 1 GB（路 A）／100 MB（路 B）**都花不到点子上**。
2. 若用途是**书页上的常规汉字**（标题页 / 版权页 / ISBN / CIP / 目录）⇒ 路 B 足够，
   体积代价可接受，可以打。
3. 若用途是**版面/框线辅助**（配合印面裁切）⇒ 检测侧即可，识别侧不重要。

**建议动作**：在打包前让 Kevin 一句话确认用途；**未确认前不要投入「含 paddle 的 1 GB 打包」**。

---

## 5. 其余打包检查清单（与 OCR 无关的坑）

1. **`.env` 不进包**（真实凭据）：打包时排除，改由首次启动在用户目录写配置
   （`api.py` 已支持 `FEICUI_ROOT` 回写 `.env`，打包版建议改写到 `~/Library/Application Support/feicui/`）。
2. **`.session.json` / `webui/var/**`**：运行时文件，**不入包、不入库**（`.gitignore` 已覆盖）。
3. **PyWebView 后端**：macOS 用 Cocoa/WebKit（`pyobjc-framework-WebKit`，本项目已装）；
   Windows 需 EdgeWebView2 Runtime（大多数 Win10+ 已有，缺失要引导安装）。
4. **`--windowed` 下无 stdout**：`api.py` 已把引擎输出重定向到 `webui/var/jobs/<job>.log`
   ⇒ 打包后**日志落文件**，UI 的「任务日志（尾部）」照常可见。
5. **沙箱 / 签名**：`.dylib` 全部 `codesign --force --options runtime`；
   公证后首次运行可能被 Gatekeeper 拦（引导「右键打开」）。
6. **首启自检**：打包版建议内置「自检」按钮 ⇒ 跑 `webui/selftest.py --no-e2e`
   （秒级、无需真渲染）＋ 一次 `render_page_2400.py --smoke`（小合成页），把结果贴给用户/售后。
7. **模型目录环境变量**（路 A 才需要）：
   `PADDLE_PDX_CACHE_HOME`（新）或 `PADDLEX_HOME`（旧）指向包内 model 目录；
   否则首次运行联网下载（打包版红线是**离线可用**）。

---

## 6. 取证命令（可复跑）

```bash
cd /Users/kevin/bistro/feicui
SP=venv/lib/python3.11/site-packages
du -sh $SP/paddle $SP/paddlex $SP/paddleocr $SP/cv2 $SP/paddle/libs
du -sh ~/.paddlex/official_models ~/.paddlex/official_models/*
du -sh venv
# 路 B：只下 wheel、不装（体积取证）
mkdir -p /tmp/rapidocr_probe && cd /tmp/rapidocr_probe
/Users/kevin/bistro/feicui/venv/bin/python -m pip download --no-deps -d . rapidocr-onnxruntime onnxruntime
python3 -c "import zipfile,glob;[zipfile.ZipFile(w).extractall('unpacked') for w in glob.glob('*.whl')]"
du -sh unpacked/* ; find unpacked -name '*.onnx' -exec du -h {} \;
```

## 7. 本单**未做**的事（如实）

- **没有**跑 PyInstaller（未生成 `.app` / `.dmg`，未做体积实测的「打包后」读数；§3 的量级为**估算**）。
- **没有**安装 RapidOCR / onnxruntime（只 `pip download` ＋ 解包量体积；**未验证** API 实测可用）。
- **没有**接入任何 OCR（`webui/` 内**零 OCR 调用**；`api.py` 的 `app_info().log_note` 与
  `tab2` 说明里明确标注「OCR 未接入」）。
- **没有**验证 Paddle 打包后的 SIGSEGV 是否复现（只引用了本仓历史实测）。

> §7 是 2026-10-16「只出要点」那一单的状态，**已过期**：2026-10-17 起已实际打包（产物在
> `webui/build/dist/**`，gitignore）；打包/验证/DMG 的现役跑法见 §8。

---

## 8. 现役打包跑法（2026-10-18 实测：重打 ＋ 包内验证 ＋ 未签名 DMG）

### 8.1 重打两阶段

```bash
cd /Users/kevin/bistro/feicui
for S in 1 2; do
  PYTHONPATH=$PWD/venv/lib/python3.11/site-packages FEICUI_PACK_STAGE=$S \
  webui/build/.venv-build/bin/python -m PyInstaller --noconfirm --clean \
    --distpath webui/build/dist --workpath webui/build/build webui/build/feicui.spec
done
```

实测（Apple Silicon / macOS 15.7.4，含 B4 `src/yinyuan_client.py`）：**s1 22.8 s / 210 MB（220 397 568 B）**、
**s2 30.3 s / 329 MB（345 235 456 B）**，两次 `EXIT=0`。

#### 8.1b ⚠ 体积回涨的根因：**函数体内的 `import` 照样被 PyInstaller 分析**（2026-10-18 实测）

现象：同一套 spec 重打，**s1 从 210 MB 涨到 298 MB（312 508 416 B）**，构建日志多出
`hook-onnxruntime.py` / `hook-shapely.py`，包内 `find` 命中 `onnxruntime`(70 MB) / `shapely`(4.3 MB) /
`pyclipper` / `rapidocr` 模型 —— 即 rapidocr 整条依赖链。

根因**不在 spec**（阶段 1 的 `datas` 只有 4 个 `src/*.py`，`hiddenimports` 也没列 `src.ocr_rapid.py`），
而在 `webui/api.py::tab3_ocr()` 里那行**本意是懒加载**的
`from src import ocr_rapid`：PyInstaller 的 AST 分析**会追踪函数体内的 import 语句** ⇒
`src/ocr_rapid.py` 被收进 PYZ ⇒ 它 import `rapidocr` ⇒ contrib hook 连带整条链。
对照：同文件的 `ocr_available()` 用 `importlib.util.find_spec` / `importlib.import_module`（动态），
**不触发任何收集**。

修法（两条同时上）：
1. `webui/api.py` 该行改 `ocr_rapid = importlib.import_module("src.ocr_rapid")`
   （`importlib` 顶部已 import；`try/except` 与错误文案不变）。阶段 2/3 照旧拿得到 ——
   spec 的 `if WITH_OCR:` 已把 `src.ocr_rapid` 列进 `hiddenimports`。
2. `feicui.spec` 加 `if not WITH_OCR: excludes += ["rapidocr", "onnxruntime", "shapely", "pyclipper"]`
   作双保险（`excludes` 只作用于 PYZ import 分析，对 datas/binaries 无效；阶段 1 没有
   `collect_all`、也没把模型列 datas ⇒ 这里有效）。

重打读数（2026-10-18，同机）：**s1 21.8 s / 210 MB（219 894 347 B，find 求和）**、
**s2 28.9 s / 329 MB（344 362 049 B）**，`EXIT=0`；s1 日志对
`onnxruntime|shapely|rapidocr|pyclipper` **0 命中**，s2 仍命中 17 项（含
`rapidocr/models/PP-OCRv6_det_small.onnx`）。

`tab3_correct()` 里的 `from src import ocr_corrector` **保留静态 import**：该模块只依赖
`argparse/json/sys/pathlib/typing`（无 numpy/cv2/rapidocr）⇒ 静态收进 PYZ 只多 21 163 B 源码，
**不拉任何重型依赖**；且阶段 1 反而因此能真用纠错（探针实测 `n_hits=1`）。


### 8.2 包内验证（**打包态的坑只能在包里验**，源码态看不出来）

```bash
A=webui/build/dist/斐萃-s1.app
ls -1 "$A/Contents/Frameworks/src"        # ← PyInstaller 6：_MEIPASS=Contents/Frameworks（数据/源码在此，非 Resources）
PROBE_STAGE=s1 "$A/Contents/MacOS/斐萃-s1" --engine-run /path/to/probe.py   # 见下
open -n "$A" --args --test-exit-after 12  # 起窗 12 s 自关；日志 ~/Library/Logs/斐萃/pack-<yyyymmdd>.log
```

`--engine-run <脚本>` 是**唯一**能在包内解释器里跑自定义代码的入口（`pack_main.py` 的 `run_engine`）；
脚本自己的 `print` 会被 `_boot()` 接到日志文件 ⇒ **探针结果要写文件**，别指望 stdout。

2026-10-18 读数（两阶段一致）：
- `Contents/Frameworks/src/`：s1 = `__init__.py, pdf_library.py, validator.py, yinyuan_client.py`；
  s2 另含 `ocr_rapid.py`、`ocr_corrector.py`；
- `from src import yinyuan_client, pdf_library, validator` ⇒ `import_ok=True`（`__file__` 均指向包内 `Contents/Frameworks/src/`）；
- `YinyuanClient(data_dir=<空目录>).status()` ⇒ 结构化 dict 12 键（`ok/connected=False/key_file_exists=False/
  prefix=""/local_dynasty_count=15/base_url/cache…`），**不抛**；
- `.dynasty_values(allow_network=False)` ⇒ `source=fallback_local, reason=NO_KEY, total=15`，且
  **逐字等于 `pdf_library.DYNASTY_OPTIONS`（15 项）**；两阶段均无网络、无凭据；
- 启动实测：`WEBUI_START mode=native` ⇒ `WINDOW_TEST: 窗口存活 12.0s（自动关窗）`，日志 0 处 `Traceback`；
- 敏感件扫描：两包内 `.env` / `.session.json` / `yinyuan.json` **各 0 个**（真 key 绝不进包）。

### 8.3 未签名 DMG（**ad-hoc，非正式签名**）

本机 `security find-identity -v -p codesigning` = **0 valid identities** ⇒ 只能 ad-hoc：

```bash
STAGE=$(mktemp -d)/dmg && mkdir -p "$STAGE"
ditto webui/build/dist/斐萃-s1.app "$STAGE/斐萃-s1.app"
ln -s /Applications "$STAGE/Applications"
codesign --force --deep -s - "$STAGE/斐萃-s1.app"          # adhoc（PyInstaller BUNDLE 步本身也已是 adhoc）
codesign --verify --deep --strict --verbose=2 "$STAGE/斐萃-s1.app"
hdiutil create -volname "斐萃 s1" -srcfolder "$STAGE" -ov -format UDZO -fs HFS+ \
  webui/build/dist/斐萃-s1.dmg
hdiutil verify webui/build/dist/斐萃-s1.dmg
```

实测：**94 MB（99 045 133 B）、UDZO/zlib、压缩比 0.440、`hdiutil verify` = checksum VALID**；
挂载后目录 = `斐萃-s1.app` ＋ `Applications -> /Applications`，**挂载内启动也能自关（`--test-exit-after 8` ⇒ EXIT=0）**。

### 8.4 分发现状（必须对用户说清）

产物 **未签名、未公证** ⇒ 用户机首次打开会被 **Gatekeeper** 拦（「无法验证开发者」）：

- 临时绕过：右键 → 打开；或 `xattr -dr com.apple.quarantine /Applications/斐萃-s1.app`；
- **正式分发**：需人类提供 **Developer ID Application 证书** ＋ **App Store Connect 凭据**，
  然后 `codesign --force --deep --options runtime --timestamp` ＋ `xcrun notarytool submit --wait` ＋ `xcrun stapler staple`；
- **ad-hoc 不是正式签名**（`TeamIdentifier=not set`），不可当作已签名的对外说法。
