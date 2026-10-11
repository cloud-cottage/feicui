# 印谱解析 · 文档预览（E9 / E10）—— 证据与收尾

> **一句话结论**：整页渲染（E9 `GET …/pages/{page}/preview.png`）与现场检测框（E10 `GET …/pages/{page}/boxes`）
> 已实现并**实测可达**；两端口（5195 直连、5164 反代）行为一致；框与图上红印面**几何对齐**（5 个印章框
> 内红色覆盖率 18%–28% ＝ 全页基线 1.73% 的 11–16 倍，框外**零**残留红）；结果页三列不再显示「—」；
> 前端 `npm run build` 干净；接口层**只读、不落盘、零 cv2/numpy/pymupdf import**（三表指纹调用前后逐字相等）。

- 口径真源：`docs/page-preview-draft-v0.1.md`（Zang 起草）；规范侧 `docs/feicui.spec.md` v1.26（AC-78〜AC-87、R42〜R48，Jing）。
- 本轮为**收尾**：实现已在上一轮落地并自证；本文件补齐 PP-10、几何对齐读数、构建证据、人工可见性核实。
- 红线（逐条守，见「③ 只读红线」）：零 DB 写 · 不落盘 · 不复制检测算法 · 子进程一次性 · 不动 E1〜E8/GC/5164 代理。

---

## 一、两端点契约（路径 / 头 / 字段）

| 端点 | 方法与路径 | 查询参数 |
|---|---|---|
| **E9** 整页渲染 | `GET /api/jobs/{job_id}/pages/{page}/preview.png` | 仅 `dpi` ∈ `{72,110,150}`，默认 **110** |
| **E10** 检测框 | `GET /api/jobs/{job_id}/pages/{page}/boxes` | 仅 `dpi` ∈ `{72,110,150}`，默认 **110** |

- `{page}` **1-based**（↔ `stamps.page` / `job_pages.page`）；`job` 的 `page_range` **不是硬边界**，可翻整本 PDF，超出实际页数才 `PAGE_OUT_OF_PDF`。
- 两端点必须用**同一个 `dpi`**：E10 的 `render.width/height` 与 E9 那张 PNG 是**同一像素空间**，覆盖层才能百分比对齐（PP-3）。
- 前端路径常量一处收口：`web/src/api/jobsPreview.js`（`PREVIEW_PNG_PATH_TEMPLATE` / `PREVIEW_BOXES_PATH_TEMPLATE`）。

**E9 响应头（实测逐字段，`ops/page-preview/e9_png_headers.txt`）**

```
Content-Type: image/png
Content-Length: 497857
ETag: "<sha256 of the PNG bytes>"
Cache-Control: private, max-age=600        # v0.1 不做服务端缓存，靠浏览器缓存
x-feicui-render-dpi: 110
x-feicui-render-size: 796x1122
x-feicui-pdf-page-count: 132
x-feicui-pdf-name: %E7%A7%A6%E5%8D%B0%E7%B1%BB%E7%BC%96 …   # §3.13：头值须 latin-1 可编码 ⇒ 中文名百分号编码
```

**E10 响应体（实测逐字段，`ops/page-preview/e10_boxes_p13.json`）**

```
job_id · page · pdf_name · pdf_page_count · job_page_range{from,to} · render{dpi,width,height,scale}
template_source            # 三态：book_template:<pdf> / builtin_default(<源码位置>) / none
params_used{hsv_low,hsv_high,min_area_eff,min_area_source,pad_ratio,edge_enabled,scale}
boxes[]{kind∈{stamp,edge}, x1,y1,x2,y2,w,h,area,aspect}      # 红=stamp 印章 / 绿=edge 边款；释文蓝框本轮不做
counts{stamp,edge} · db{stamp_rows}                          # db 是只读对照；框**不来自 DB**
notes[]                    # 未标定书带「本书未标定：框由内建默认参数检出，可能不准」
```

**错误面**（一律结构化 JSON，**顶层 `error` ＋ `detail`**，非 `{"detail":{…}}` 嵌套）：

`400 BAD_PARAM` · `404 JOB_NOT_FOUND` · `404 PDF_MISSING` · `404 PAGE_OUT_OF_PDF`（只按 PDF 实际页数判）· `500 RUNNER_*`（§3.14 五码）· `500 RENDER_FAILED`。

---

## 二、五类证据 → 各自指向的文件

| # | 证据类 | 结论 | 文件 |
|---|---|---|---|
| **①** | **契约与正常路径原样件** | 两头 200，头/字段逐字合口径 | `e9_png_headers.txt` · `e9_p13_dpi110.png` · `e10_boxes_p13_headers.txt` · `e10_boxes_p13.json` · `e10_boxes_p1.json`（本页 0 框）· `e10_boxes_cn_p5.json`（中文名书→打开失败如实 500） |
| **②** | **错误面矩阵（含 RUNNER_\* 注入）** | 7 类错误逐一复现；`RUNNER_PYTHON_MISSING` 经临时注入 config 验出 | `errors_raw.txt` · `runner_injection.txt` · `e9_png_headers_cn.txt` |
| **③** | **只读红线自证** | 三表指纹调用前后**逐字相等**；预览批次未落盘；接口层**零** cv2/numpy/pymupdf import | `fingerprint_before.json` · `fingerprint_after.json` · `redline_calls.txt` · `new_files_after.json` · `imports_scan.json` · `job_baseline.txt` · `redline_probe.py` |
| **④** | **规模读数（大书 851 页）** | 851 页 / 1.88 GiB 的书页 1 渲染 + 检测秒级返回 | `bigbook_http.txt` · `big_e9_p1_dpi110_headers.txt` · `big_e9_p1_dpi110.png` · `bigbook_worker_side.txt` · `big_e10_p1.json` · `big_e10_p2.json` · `big_e10_p3.json` |
| **⑤** | **前端可见性 + 几何对齐** | 覆盖层 7 框（5 红/2 绿）真渲染；框扣在红印面上 | `browser_5195_p13_stage.png` · `browser_5195_p13_edges_zoom.png` · `browser_5195_p13_fullpage_refresh.png` · `browser_5195_p5_unparsed_stage.png` · `browser_boxes_5195_p13.json` · `alignment_check.py` · `alignment_check_p13.json` · `box_visibility.py` · `box_visibility.json` · `pp10_5195_results_table.png` · `pp10_5164_results_table.png` · `pp10_readings.json` · `results_keypath_diff.txt` · `build.txt` |

---

## 三、实测读数表

**PP-3 框 × 红印面对齐**（`alignment_check_p13.json`；PNG `e9_p13_dpi110.png` 796×1122，与浏览器加载**同一字节**，见 `redline_calls.txt`：`E9 p13 dpi110 size=497857`）：

| 框 | imgSpace (x1,y1,x2,y2) | 框内红覆盖率 | ÷ 全页基线(1.73%) | 红质心偏移(归一短边) |
|---|---|---|---|---|
| stamp #0 | 144,193,261,310 | **0.2405** | 13.9× | 0.049 |
| stamp #1 | 194,593,330,733 | **0.1946** | 11.2× | 0.041 |
| stamp #2 | 355,202,443,286 | **0.2811** | 16.2× | 0.029 |
| stamp #3 | 466,591,601,730 | **0.2783** | 16.1× | 0.003 |
| stamp #4 | 551,200,630,280 | **0.1847** | 10.7× | 0.045 |
| edge #5 | 442,765,626,937 | 0（边款黑为主） | — | 暗像素占比 0.3331 |
| edge #6 | 152,766,349,941 | 0 | — | 暗像素占比 0.3155 |

- **裁决**：`verdict_stamp_boxes_on_red = true`（5 个印章框内覆盖率均 > 3× 基线）；`stamp_boxes_max_centroid_offset_norm = 0.049`（红质心几乎压框心）。
- **框外是否还有大片红**：`outside_boxes.red_outside_all_stamp_boxes_px = 0` —— 全页红 15 465 px **全部**落在 5 个印章框内，**框外零残留** ⇒ 无漏检印章（`verdict_no_large_missed_stamp = true`）。

**规模读数（大书「秦印类编 检索版.pdf」851 页 / 1.88 GiB）**：

| 端点 | 参数 | HTTP | 耗时 | 字节 | render |
|---|---|---|---|---|---|
| E9 | page1 **dpi110** | 200 | **0.490547 s** | **1 458 001 B** | 783×1125 |
| E9 | page1 dpi150 | 200 | 0.513822 s | 2 799 216 B | 1067×1534 |
| E9 | page1 dpi72 | 200 | 0.326619 s | 582 644 B | 513×737 |
| E10 | page1 dpi110 | 200 | 0.320069 s | — | 计数 stamp 8 / edge 2 |
| E9 | page900（>851） | **404** | — | — | `PAGE_OUT_OF_PDF` |
| E9 | page1 dpi110（worker 直调） | — | 0.363 s | 1 458 001 B | 同上 |

**PP-10 结果页三列（`pp10_readings.json`；job-502016dd…，两端口逐字一致）**：

| 列 | 旧实现（顶层键） | 修正后（形状真源） | 5195 实测 | 5164 实测 |
|---|---|---|---|---|
| `pdf_name` | `it.pdf_name` ⇒ 「—」 | `it.feicui.pdfName` | **tmp.pdf** | **tmp.pdf** |
| `img_path` | `it.img_path` ⇒ 「—」 | `it.assets[0].sourceImgPath` | **output/pairs/p13_0/stamp.png** | 同 |
| `bbox` | `it.x1..y2` ⇒ 「—」 | `it.bbox.x1..y2` | **102,134,164,196**（x1=**102**） | 同 |

- 7 列逐列「—」计数 = `[0,0,0,0,0,0,0]`；两端口截图 **sha256 相同**（`ef4dfba6…`）。前后片段对照见 `results_keypath_diff.txt`。

**前端构建（`build.txt`）**：`vite v6.4.3` → `✓ 56 modules transformed` → `✓ built in 793ms`，**EXIT=0，零报错零警告**（`dist/index.html 0.65 kB` · `assets/index-DWpZKMdZ.css 9.62 kB` · `assets/index-CyrzOjoX.js 246.71 kB │ gzip 75.99 kB`）。

---

## 四、人工可见性（截图目视 ＋ DOM/像素核实）

> 本节同时回答**第 5 项**（两张截图的肉眼结论）与**第 7 项**（父层「只见 5 红框、无绿框」的矛盾核实）。

**① `browser_5195_p13_stage.png`（p13 预览台，1300×1900）**
- **目视（vision）**：可见 **5 个红/粉框**（各圈一枚朱文/白文印章）＋ **2 个绿/青框**（圈住下半两段长条边款拓片）。红框与红印面**重合**。
- **DOM 计数（真浏览器 getComputedStyle）**：`document.querySelectorAll('.pv-box')` ＝ **7 节点** ＝ 5 `pv-box--stamp`（`rgb(255,115,133)`）＋ 2 `pv-box--edge`（`rgb(47,214,160)`），均 `2px solid`、`opacity 1`、`position absolute`。
- **像素判定（确定性）**：截图中贴近 `#FF7385` 的像素 15 861 个（前 5 大连通域外接框 162×163 / 189×194 / 122×116 / 188×193 / 110×111 —— 正是 5 个印章框）；贴近 `#2FD6A0` 的像素 4 953 个，**两个最大连通域 273×243 / 255×239 正是 2 个边款框**。

**② `browser_5195_p5_unparsed.png`（未解析页 p5）**
- **如实说明**：该文件是 **1280×577 的「页首视口」**截图，画面是任务详情的**页头/进度卡**（`state DONE`、`done_pages/total_pages 7/7`、后端连通横幅），**并不包含预览台**——故它**本身不构成框的证据**（无红/绿框像素：`#FF7385` 0 px；`#2FD6A0` 命中的是进度条/UI 强调色，非框）。
- **补齐**：另截 `browser_5195_p5_unparsed_stage.png`（1106×1500，预览台区）——p5 **未解析页**：整页图正常加载（`naturalWidth×Height = 796×1122`），**0 个框**、`印章(0) 边款(0)`、`db.stamp_rows = 0`。即「未解析页也能翻页预览，只是没有框」，符合口径。

**③ 第 7 项裁决：边款绿框**确实渲染**（父层「只见 5 红框」不成立）**
- 三方互相印证：**DOM** 2 个 `pv-box--edge` 节点、`rgb(47,214,160)`、`2px solid`、`opacity:1`、`display:block`；
  **像素**（`box_visibility.py`）在 `browser_5195_p13_edges_zoom.png` 上恰好 **2 个** `#2FD6A0` 连通域（各 ≈ 3840 / 3288 px）；
  **vision** 在边缘放大图上读到「2 红框（印章）＋ 2 绿框（分别圈住左右两条长条边款拓片）」。
- 绿框**位置与配色**（DOM 逐节点）：`left 55.53% / top 68.18% / w 23.12% / h 15.33%`（右条，视口 701,2511,255×239）与 `left 19.10% / top 68.27% / w 24.75% / h 15.60%`（左条，视口 299,2512,273×243）；配色＝ `--accent` `rgb(47,214,160)`。
- 全量读数见 `box_visibility.json`（DOM 节点 + 像素 + vision 三段）。**未改任何产品默认样式**；只为取证加了放大图 `browser_5195_p13_edges_zoom.png`。
- **根因（为何肉眼易漏）**：绿 `#2FD6A0` 是**中低对比**的青绿，叠在偏白页面 + 黑底白字拓片上，2px 细边在缩略视口里不显眼；`#FF7385` 粉红则醒目。**代码链路无缺陷**（`kind==='edge'` 正常进 `previewBoxes`、正常给 `pv-box--edge` 上色），即「不是没画，是不显眼」。

---

## 五、已知未验项（诚实清单）

1. **释文蓝框**未实现 —— 口径件 v0.1 明确本轮不做（只做红=印章 / 绿=边款）。
2. **`RUNNER_*` 五码只逐字验了 `RUNNER_PYTHON_MISSING`**（经临时注入 `worker_python` 指向不存在路径，见 `runner_injection.txt`）。`RUNNER_TIMEOUT / RUNNER_EXIT_NONZERO / RUNNER_NO_OUTPUT / RUNNER_BAD_OUTPUT` **未被单独强制触发**（用 1.88 GiB 的大书页 1 想诱发 TIMEOUT，实际只到 0.49 s，未超 20 s）。
3. 大书读数取自**临时探针 job `job-19aa71198ba24d55ac738fa144fb6f3d`**（已由 Zang 亲手清回基线：三表指纹 89/5/32 与 `job_baseline.txt` 逐字相符）；那些读数是**该 job 存在期间**的实测。
4. **`browser_5195_p5_unparsed.png` 未包含预览台**（见上 §四②）——已用 `browser_5195_p5_unparsed_stage.png` 补齐，原文件保留以如实反映上一轮的取证瑕疵。
5. 5164 侧的预览台截图（`browser_5164_*`）同为**页首视口**，不含预览台；5164 的**结果页**证据由 `pp10_5164_results_table.png` 承载（与 5195 逐字节相同）。
6. `errors_raw.txt` 里标为 `RUNNER_TIMEOUT(Downloads)` 的那条，实际响应是 `RENDER_FAILED`（`秦汉印典 …ok.pdf` 打不开）——措辞与真实码不符，**以响应体为准**。

---

## 六、如何复跑（命令逐字）

```bash
# 工作目录
cd /Users/kevin/bistro/xiai/feicui

# ① 几何对齐（框 × 红印面）—— 结果落 stdout
venv/bin/python ops/page-preview/alignment_check.py \
  ops/page-preview/e9_p13_dpi110.png ops/page-preview/browser_boxes_5195_p13.json

# ①b 截图框可见性（像素计数，两种边框 token）
venv/bin/python ops/page-preview/box_visibility.py ops/page-preview/browser_5195_p13_stage.png

# ② 只读红线：三表内容指纹（调用前后各跑一次，逐字相等）
FEICUI_DB=/Users/kevin/bistro/xiai/data/yinpu.db \
  venv/bin/python ops/page-preview/redline_probe.py --fingerprint
# 接口层不得 import cv2/numpy/pymupdf（应为零命中；worker 侧脚本除外）
venv/bin/python ops/page-preview/redline_probe.py --imports

# ③ 两端点契约（API 端口 5196）
curl -sS -D - -o /tmp/e9.png \
  'http://127.0.0.1:5196/api/jobs/job-6e7471ff9c464695b9463cdad5122246/pages/13/preview.png?dpi=110'
curl -sS \
  'http://127.0.0.1:5196/api/jobs/job-6e7471ff9c464695b9463cdad5122246/pages/13/boxes?dpi=110'

# ④ 前端构建（须干净）
cd /Users/kevin/bistro/xiai/feicui/web && npm run build

# ⑤ 重启 API（控制面板；JSON body 单键 sid）
curl -sS -X POST http://127.0.0.1:5555/api/restart \
  -H 'Content-Type: application/json' -d '{"sid":"feicui-api"}'

# ⑥ 前端两条入口（PP-9/PP-10 用真浏览器）
#   直连：  http://127.0.0.1:5195/feicui/jobs/<job_id>
#   反代：  http://localhost:5164/feicui/jobs/<job_id>          # 5164 必须用 localhost
```

> 取证夹具用 job：`job-6e7471ff9c464695b9463cdad5122246`（`tmp.pdf`，page_range 13–19，132 页）—— 仅**读**，不建 job、不改库。
