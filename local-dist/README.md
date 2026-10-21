# local-dist —— 「斐萃」玺印解析任务台・本地封装分发版

PyWebView 壳 ＋ 纯 stdlib 逻辑层 ＋ 引擎子进程。入口 `app.py`（窗口）、桥 `api.py`（`js_api`）、
UI `ui/{index.html,style.css,app.js}`、算法 `src/**`。**零外网、零 CDN、零新依赖**。

跑法（必须用老工程 venv，`venv/bin/<console script>` 的 shebang 已失效）：

```bash
cd /Users/kevin/bistro/feicui
./venv/bin/python local-dist/app.py                      # 起窗口
./venv/bin/python local-dist/selftest.py --no-e2e       # 逻辑层自检
./venv/bin/python local-dist/tests/test_field_extract.py # 字段提取单测
./venv/bin/python local-dist/domtest_tabs.py            # tab1/tab2 渲染后 DOM
./venv/bin/python local-dist/domtest.py                 # tab3 渲染后 DOM
./venv/bin/python local-dist/domtest_yinyuan.py         # yinyuan 连接面
```

---

## 字段提取与命名（tab2 切图台 → tab3 3_Cropped_Tiff）

一句话：**自动检测把印面框出来，字段提取把「释文 / 状态字 / 编号」从页面 OCR 文本里归到每一枚印上，
再按阅读顺序定 C/R、按编号定文件名**；三字段在 tab2 字段区可改，改完的名子就是落盘名。

真源：`src/field_extract.py`（算法 ＋ 常量）、`src/seal_crop.py`（`grid_order` / `build_crop_name`）、
`src/validator.py::parse_tiff_name`（反向兼容解析）。**改口径先改这三处，UI 只做展示与入参。**

### 1. 流程：检测 ⇒ OCR ⇒ **四轮过滤** ⇒ 就近归属 ⇒ 分类 ⇒ 纠错/排序

1. **红印检测**（`src/seal_detect.py`，400 dpi 系；与库内 `stamps` bbox 同坐标系）；
2. **整页 OCR**（`src/ocr_rapid.py`，可注入 `ocr_fn` ⇒ 单测能跑纯逻辑）；
3. **四轮过滤**（顺序即优先级，先命中先剔）：
   | 轮次 | 判据 | 目的 |
   | --- | --- | --- |
   | ① 印章内 | 文本框中心落在某枚印 bbox（外扩 6%）内 | 篆书区文本，一律剔 |
   | ② 页边带 | 左 4.5%、上 5.5%、**下仅 2.2%**；右边缘不判 | 栏目名/页眉页脚；下边距给小是因为末行的状态字/编号贴着版心底 |
   | ③ 过远 | 与最近印框边缘距 > `平均印边长 × 2.2`（且不小于页短边 10%） | 版心外栏目名 |
   | ④ 噪声 | 纯数字短串（页码、手写标注号 1–6 …） | 非字段 |
4. **就近归属**：剩余文本按「bbox 边缘距」归到最近的那一枚印（`bbox_gap`，相交记 0）；
5. **分类**：`3–5 位数字`（`O/o` 归一成 `0`）⇒ **编号 `code`**；**仅一个汉字** ⇒ **状态字 `status`**；
   其余多字串 ⇒ **释文 `inscription`**（取最长，并列取分数高者）；数字/符号单字 ⇒ 噪声；
6. **纠错/打分**（见 §3）＋**阅读顺序**（见 §2）。

返回里带 `dropped:{inside_seal, edge, far, noise}` 与 `dropped_texts` —— **过滤不是黑箱**：
每枚被判掉的文本都能回指到是哪一轮、什么内容（验收时按这四个计数对拍）。

### 2. 阅读顺序：**人工 > 编号推断 > 兜底**，它决定 C/R 方向

- **方向语义**（与 `seal_crop.grid_order` 同一真源，别另算）：
  **列 C** 按水平方向编号（`rtl` ⇒ **右列＝C1**，`ltr` ⇒ 左列＝C1）；
  **行 R** 按垂直方向编号（`ttb` ⇒ 上行为 R1，`btt` ⇒ 下行为 R1）。
  取反会把整页命名左右/上下颠倒 —— 这是命名正确性唯一依赖的一条。
- **三级优先级**（`_resolve_reading_order` / `extract_fields`）：
  1. **人工**：用户在下拉里显式选了 `rtl-ttb` 等 ⇒ `order_source='manual'`（最高优先，永不被覆盖）；
  2. **编号推断**：`auto` 且 ≥2 枚印都有编号 ⇒ 编号升序后比较首末 x 得 `rtl/ltr`、同列相邻 y 得
     `ttb/btt` ⇒ `order_source='code-sequence'`（编号即版序，这是本工具的主路径）；
  3. **兜底**：无编号 ⇒ 本书元数据（tab1「阅读顺序」）`book-meta`；再没有 ⇒ `ltr-ttb`（`fallback`，
     **保持改动前行为**）。
- **`auto` 的语义分界（前端↔后端必须同口径）**：下拉停在 `auto` ⇒ 前端**只传 `'auto'`**，
  由后端自己推断；**不要**把上一轮 `tab2_extract` 的结果当显式值回传 —— 那会把「机器推的」
  冒充成「人选的」（`order_source` 被写成 `manual`），排障时再也分不清是谁定的顺序。
  只有用户真的动了下拉，才传具体值。
- 界面上的来源标签带后端原值：`自动 ⇒ rtl-ttb（code-sequence：按编号序列推断）` /
  `手动：…（manual）` / `兜底：…（book-meta|fallback）`。

### 3. 纠错口径：**禁止猜测式改字**

历史教训：曾按「字形相近」把正确的「中羞行府」改成「中差行府」。此后口径固定为**只认两个来源**：

| 来源 | 行为 |
| --- | --- |
| **权威词表** `authoritative`（`{原始: 核定}` 映射 / 已核定释文集） | **唯一允许改字**的路径；改时保留 `inscription_raw` 与 `corrected_by='authoritative'` |
| **同页多数票**（同一释文出现 ≥ **3** 次且完全一致，`MIN_VOTES=3`） | 只把 `inscription_verified` 标真，**一个字都不改** |
| 其余（低分、词表外、只出现 1–2 次） | **原样输出**；`inscription_score < 0.95` 且未验证 ⇒ 标 `needs_review`（UI 整行加 `.rev`、分数旁「⚠」），交人工确认 |

⇒ **`authoritative` 为空时，输出必须与 OCR 原文逐字相同**（单测里有这条反向断言，并用「给了映射就会改」
证明它不是永远为真的空转）。任何「用字表/语言模型猜一个字」的实现都算越线。

### 4. 命名规则（`src/seal_crop.py::build_crop_name`）

```
有编号：  <编号>_P<页>_C<列>_R<行>_<释文>_<朝代>_<作者>.tiff      naming = with_code
         例：0424_P370_C1_R1_中羞行府_清中期_吳熙載.tiff
无编号：  P<页>-C<列>-R<行>.tiff                                  naming = legacy（保兼容）
         例：P370-C1-R2.tiff
```

- `P` ＝ 页码（1-based，与 `page_range` / `stamps.page` 同轴）；`C`/`R` 见 §2；
  **P/C/R 的字母前缀保留**（机器可解析）——编号只加在最前面，不影响 C/R 方向。
- 朝代/作者优先级：**印级字段 > 本书元数据（tab1）> `NA`**；空段一律写 `NA`（位置稳定，不塌缩）。
- **清洗**（段内）：`/ \ : * ? " < > |` 与换行/制表 ⇒ `-`；连续 `-` 折叠；首尾 `-` 去掉；
  整段为空 ⇒ `NA`。例：编号写成 `04/24` ⇒ `04-24_…`。
- **长度**：整名上限 **200 字符**（Windows 单段 255/全路径 260 留余量）；超长按
  **释文 → 作者 → 朝代**逐段截断（每段保 ≥4 字），仍超则整名截到 200 加 `~`。
- **落点**：`3_Cropped_Tiff/<目录键>/`；目录键来自 `config/book_dir_keys.json`
  （ISBN-13 优先，未登记 ⇒ 书名并标 `dir_key_source='fallback'`）。
- **同页一次提交**：C/R 按**本次框集合**的网格位次排 ⇒ 分多次各传一枚会各自从 `C1-R1` 起、同名互相覆盖。
- `<目录键>/_fields.json`：按页合并的字段 sidecar（含 `naming`、`reading_order`、`order_source`
  与每枚三字段原值），`per_seal_json=true` 另写每枚 `<名>.json`。

### 5. tab3（3_Cropped_Tiff）兼容说明

- tab3 **业务语义未改**（缩略图/分页/方向键导航/大图预览/重命名/校验一律照旧）；本单只扩了
  **文件名解析**：`validator.parse_tiff_name` 现在认三种形态并给出 `naming`
  —— ① 旧模板 `P001-C2-R3-释文-朝代-作者.tiff`（`legacy`）；
  ② 切图台新命名 `<编号>_P…_C…_R…_释文_朝代_作者.tiff`（`with_code`，`page_raw` 保留零填充）；
  ③ **无编号回落** `P<页>-C<列>-R<行>.tiff`（`legacy`，P/C/R 照读、三字段为空）。
  不含 `P` 段的件（如 `清心-宋-齐白石.tiff`）**仍按旧行为**返回 `None`（`standard=false`）——
  这条没动，别指望它被「兼容」进来。
- 新命名的件在 tab3 里能回填 **页码 / 列 / 行** 与 **释文 / 朝代 / 作者**三个输入框，并给出
  「已自动解析：第 370 页 · 第 1 列 · 第 1 行（前缀 0424_P370_C1_R1_）」；新名预览不会把它降级成旧模板。
- `_fields.json` / 每枚 `.json` 不是 `.tiff`，不进缩略图网格。

### 6. 验收读数（2026-10-20 本机实测，可复跑）

| 面 | 命令 | 读数 |
| --- | --- | --- |
| 字段提取单测 | `tests/test_field_extract.py` | **26 OK**（6 枚真值 6/6、四轮过滤 7/2/0/5、`rtl-ttb`/`code-sequence`、纠错反向断言、命名逐字、tab3 反解） |
| 逻辑层自检 | `selftest.py --no-e2e` | **80 PASS / 0 FAIL** |
| tab1/tab2 渲染后 DOM | `domtest_tabs.py` | **31 PASS / 0 FAIL** |
| tab3 渲染后 DOM | `domtest.py` | **39 PASS / 0 FAIL** |
| yinyuan 连接面 | `domtest_yinyuan.py` | **11 PASS / 0 FAIL** |
| 真后端沙箱（`tab2_extract → tab2_crop → _fields.json → tab3_list`） | 见下 | **13/13**，6 枚全 `with_code`、`rtl-ttb`/`code-sequence` |

真后端沙箱的做法（不碰正式产物）：`FEICUI_DATA_DIR` ＋ feicui 根都指临时目录，
用 `tests/fixtures/sample_rtl_ttb.png` 造一页 PDF，跑 `tab2_extract`（auto）⇒ 6 枚编号 0421–0426、
`reading_order=rtl-ttb`、`order_source=code-sequence`；`tab2_crop`（**传 `reading_order='auto'`**，
带 fields）⇒ 6 件全 `naming=with_code`、回 `code-sequence`；回读 `_fields.json` 与 `tab3_list`
⇒ 6 件都能读出 page/col/row ＋ 三字段。

### 7. tab1 一键高清化 v2 口径（全页输出 · 已达标页跳过）

真源：`src/highres_pdf.py`（模块 docstring 即契约）。**输出 PDF 恒含源 PDF 全部页**，第 i 页 ≡ 源第 i 页
（页数 / 顺序 / pt 尺寸不变）⇒ tab2 按页索引切图时页码与原件一一对应。`page_from/page_to` 只决定
**哪些页渲高清**，其余页三分：`highres`（已达标，嵌旧位图，跳过渲染）/ `render`（范围内且无达标位图，
含档位更低 ⇒ 升级重渲）/ `passthrough`（范围外且从未高清化 ⇒ `insert_pdf` 原样复制，保文字层）。
**曾经高清化过、本次不在范围内**的页保持原档，不降级成 passthrough。

进度文件升 schema **v2**（`units` 页级 dpi 登记表 ＋ `run` 本次读数），**兼容读 v1**（`done` 按 `prog.dpi` 迁移）。
位图可得性：① `var/highres_pages/…/P####.png` 缓存 → ② 旧 `out_pdf` 同页 `extract_image`（校验 px 一致，
range-only 旧输出按进度页清单做页映射）→ ③ 重渲。取回的位图**不写回缓存**。`CANCELLED`/`SIZE_LIMIT`/
`PAGE_COUNT_MISMATCH` 一律不覆盖上一版 `out_pdf`；体积只累计高清 PNG 字节（passthrough 不计）。

| 面 | 命令 | 读数（2026-10-21 本机） |
| --- | --- | --- |
| 高清化 v2 单测 | `tests/test_highres_pdf.py` | **7 OK / 0 FAIL**，0.8 s（全页+passthrough 文字层、1200→600 跳过 3 页、幂等 rendered=0、清缓存靠旧 PDF 恢复、v1 迁移、range-only 重建、CANCELLED 不动产物） |
| 全部单测 | `python -m unittest discover -s local-dist/tests` | **188 OK** |
| 逻辑层自检 | `selftest.py --no-e2e` | **80 PASS / 0 FAIL**（不变） |
| tab1/tab2 渲染后 DOM | `domtest_tabs.py` | **52 PASS / 0 FAIL**（含新增 3 条：页范围文案、running 行「已渲/跳过/原样/共」、done 行同口径） |
