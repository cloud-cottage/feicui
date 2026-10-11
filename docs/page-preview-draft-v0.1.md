# 文档预览（印谱解析线内）口径件 v0.1

- 起草：**Zang 2026-10-11**（**需求拆解件 / 口径草案**——不是规范；规范由 **Jing** 按 `feicui.spec.md` §0.4 流程入册）
- 需求输入（Kevin 2026-10-11 原话）：「我需要在 pdf 印谱解析的过程中预览文档，这个页面内容之前有，现在无」
- clarify 答复（Kevin 2026-10-11，两问两答）：
  1. 「之前有、现在无」＝ **新的 feicui「印谱解析」线里根本没有文档预览**（旧 Streamlit `feicui/app.py` 那个「🔍 检测效果预览」页没了 / 8501 已停）——**不是**某个页面变空白。
  2. 要看的东西（多选，只选了第 1 项）＝ **整页 PDF 渲染 ＋ 检测框叠加（印章红框 / 边款绿框），解析中可翻页**。
     ⇒ 未选的另三项（结果页定位、建 job 前试解析一页、仅缩略图浏览）**本轮不做**。

---

## 1. 现状实测（Zang，2026-10-11 07:53〜07:58；均为可复跑读数）

| 事实 | 读数 / 命令 |
| --- | --- |
| 新版 feicui 三个 job 页面**都不是空白** | `/`（任务台，含 E8 拖曳上传 ＋ inbox 用量）、`/jobs/{id}`（E2：`DONE 7/7`、counters）、`/jobs/{id}/results`（E3：`total=31`）、`/jobs/{id}/missing`（E5）均渲染正常 |
| 新版前端**只有一处「预览」** | `web/src/pages/JobsPage.vue` 的 inbox「预览清理」（dry-run）——**与文档预览无关** |
| 服务端**没有整页渲染端点** | `grep -rn "get_pixmap\|render_page\|page_image\|整页" server/app/*.py` ⇒ **零命中** |
| 唯一存在过文档预览的地方 | 旧 Streamlit `feicui/app.py` L188–250「🔍 检测效果预览」（选页码 → 整页图 ＋ 🔴印章/🔵释文/绿边款框）＋ L335「提取结果预览」；**8501 现无监听** |
| 接口层**无 pymupdf / cv2** | `server/.venv/bin/python -c "import pymupdf"` ⇒ `ModuleNotFoundError`；PIL 有 |
| worker 侧有 pymupdf | `feicui/venv/bin/python -c "import pymupdf"` ⇒ **1.28.2**；`cv2` / `numpy` 同在该 venv |
| **既有先例**：接口层要读 PDF / 跑图像栈 | `server/app/pdfmeta.py`「**子进程**调用 `feicui/venv/bin/python`」；`server/app/square_runner.py` 是完整形态（stdin→stdout 一行 JSON、`FEICUI_SQUARE=` 标记、纯计算、零 DB 写、不落盘） |
| 检测算法**只有一份** | `processor.py::detect_stamp_regions` / `detect_edge_inscriptions` / `visualize_page`（L449，`scale=1.5`，`min_area × ((scale*72/BASE_DPI)²)` 换算，`BASE_DPI=144`；生产 `RENDER_DPI=400`、`AREA_SCALE≈7.716`） |
| 模板真源 | `config/templates.json` **顶层只有 3 本书名键、无 `default` 键**；**`秦印类编 检索版.pdf` 未标定** ⇒ 需要内建兜底 ＋ **如实标注**（§3.14.6 的教训：**绝不引用不存在的来源键**） |
| 目标大书 | `feicui/inbox/20261011/秦印类编 检索版.pdf`：**2,019,683,630 B / 851 页 / 页盒 512.16×736.08 pt**；`jobs` 表**尚无**它的 job（现仍只有 2026-09-20 的 5 条） |
| 成本基线 | render **0.16 s/页**、detect **0.03 s/页**（`qa-baseline/`，2026-09-20 实测）⇒ 预览每页 ≈ 0.2 s 计算 ＋ 子进程冷启动 |

### 判负 / 边界事实（写清，免得派单踩）
- **老 job 的 `pdf_path` 已失效**：`stamps` 里 3 条 job 的路径是 `/Users/kevin/bistro/shu/feicui/tmp.pdf`（**该路径已不存在**）⇒ 预览必须能如实报 `PDF_MISSING`，**不得**用别的书顶替。
- **`jobs` 表无 `done_pages` 列**（列名是 `cursor_chunk_*` / `state`）——进度由 E2 复算，预览**不要**去改 E2 的形状。

---

## 2. 口径（默认值；每处标「一句话可改」＝ Kevin 一句话即可改）

### 2.1 端点（**2 个**，job 体系 ⇒ **建议登记 E9 / E10**；编号终裁归 Jing）
| 建议编号 | 端点 | 语义 |
| --- | --- | --- |
| **E9** | `GET /api/jobs/{job_id}/pages/{page}/preview.png` | **整页渲染（PNG 二进制）**。`{page}` **1-based**（↔ `stamps.page` / `job_pages.page`）。查询参数白名单：`dpi`（可选） |
| **E10** | `GET /api/jobs/{job_id}/pages/{page}/boxes` | **该页检测框（JSON）**。同一份检测实现、**现场检测** |

- **E9 响应**：`200` `Content-Type: image/png`、`Content-Length` 必填、`ETag`＝**PNG 字节 sha256**、`Cache-Control: private, max-age=600`；诊断头 `x-feicui-render-dpi` / `x-feicui-render-size=WxH` / `x-feicui-pdf-page-count` / `x-feicui-pdf-name`（**含中文书名 ⇒ 必须走既有的 header 安全口径（百分号编码），§3.13 的坑：原样回吐 DB 值曾让整条 500**）。
- **E10 响应（字段名逐字）**：
  ```json
  {"job_id":"...","page":13,"pdf_name":"tmp.pdf","pdf_page_count":132,
   "job_page_range":{"from":13,"to":19},
   "render":{"dpi":110,"width":797,"height":1125},
   "template_source":"book_template:tmp.pdf | builtin_default(<源码位置>) | none",
   "params_used":{"hsv_low":[...],"hsv_high":[...],"min_area_eff":466.821,"min_area_source":"...","pad_ratio":0.02,"edge_enabled":true,"scale":1.53},
   "boxes":[{"kind":"stamp|edge","x1":204,"y1":269,"x2":327,"y2":391,"w":123,"h":122,"area":15006.0,"aspect":1.01}],
   "counts":{"stamp":6,"edge":1},
   "db":{"stamp_rows":6},
   "notes":["人读提示，如「本书未标定：框由内建默认参数检出，可能不准」"]}
  ```
  - **`min_area_source` 一律复用 `app/square.py::min_area_source_label` 的同口径**（**不得**写 `templates.json:default`）。
  - **Errata（v0.1 修正｜Zang 2026-10-11，Kong 实报）**：本件初稿的 E10 样例曾写 `min_area_eff=6172.84`（＝800×`AREA_SCALE` 的 **400 dpi 生产值**）却又写 `scale=1.53`（110 dpi），**两者自相矛盾**；口径以 **§2.2「按本次渲染 dpi 换算」** 为准 ⇒ `dpi=110` 时 `min_area_eff = 800×(110/144)² ≈ 466.821`、`scale = 110/72 ≈ 1.528`；`6172.84` 只在 400 dpi 生产解析路径出现。Kong 按 §2.2 实现，**正确**；样例已按此更正。
  - **`db.stamp_rows` 是只读对照**（该 `(pdf_name,page)` 在 `stamps` 的行数），**框本身不来自 DB** —— 理由：解析中的页 / 未解析页在库里没有框，而预览要在整本书上都能翻。
- **错误面（一律结构化 JSON，顶层 `error` ＋ `detail`，v1.23 口径）**：
  `400 BAD_PARAM`（page 非正整数 / `dpi` 非白名单）· `404 JOB_NOT_FOUND` · `404 PDF_MISSING`（`jobs.pdf_path` 不在盘上）· `404 PAGE_OUT_OF_PDF`（page > PDF 页数）· `500 RUNNER_*`（沿用 §3.14 五码：`RUNNER_PYTHON_MISSING` / `RUNNER_TIMEOUT` / `RUNNER_EXIT_NONZERO` / `RUNNER_NO_OUTPUT` / `RUNNER_BAD_OUTPUT`）/ `500 RENDER_FAILED`。
  - **`PAGE_OUT_OF_PDF` 只按 PDF 实际页数判**；**job 的 `page_range` 不是硬边界**（Kevin 要能翻整本）。

### 2.2 框来源 ＝ **现场检测**（一句话可改）
- 一律走 `processor.detect_stamp_regions` / `detect_edge_inscriptions`，**在 worker 侧子进程里跑**；`min_area` 按**本次渲染 dpi** 换算（照 `visualize_page` 公式，不得另立第二套）。
- **边款框本轮给**（现场检出即可，库里本无边款真值）；**释文（蓝框）本轮不做**（Kevin 未选）。
- **框的种类与图例**：`stamp`＝🔴 印章、`edge`＝🟢 边款（与旧工具图例一致的口径；旧工具另有蓝框＝释文，本轮不启用）。

### 2.3 模板三态（**必须如实标注，不得假装权威**）
① `book_template:<pdf_name>`（`config/templates.json` 命中）；② `builtin_default(<常量源码位置>)`（未标定 ⇒ 内建兜底，**UI 必须可见提示**：「本书未标定，框由内建默认参数检出，可能不准」）；③ `none`（连兜底都不可用 ⇒ 只出图、`boxes:[]`、`notes` 说明）。`params_used.min_area_eff` **必须是 worker 侧真实生效值**（§3.14 判负第 ⑥ 条的同一纪律）。

### 2.4 前端落位（**不新增页签 ⇒ 不动 AC-23**）
- 落位：**任务详情页 `/jobs/{job_id}`（`JobDetailPage.vue`）内新增一张「文档预览」卡**。
- 交互：页码输入 ＋「上一页 / 下一页 / 首页 / 末页」＋ **键盘 ←/→**；`<img>`＝E9；**框用绝对定位覆盖层**（`left/top/width/height` 取 `bbox / render` 的百分比，**不烧进图**，便于开关）；图例 🔴印章(N) 🟢边款(M) ＋ 模板来源徽标 ＋「刷新」按钮（解析推进后重取框）。
- 边界：页码默认取 `job` 的 `page_range.from`（无则 1）；**loading / 失败必须可见**（不得空白、不得占位图冒充）；色值一律走既有 token；**零外链资源**。
- 顺带（**同轮必修 —— Kevin 2026-10-11 已裁定「修」，与默认相反）**：结果页 `ResultsPage.vue` 三处**数据源键路径错**（Zang 实测，载荷键路径真源＝§3.12）：
  | 行 | 现读（错） | 真值键路径 | 现象 |
  | --- | --- | --- | --- |
  | L260 | `it.pdf_name` | **`feicui.pdfName`** | 显示 `—` |
  | L264 | `it.img_path` | **`assets[0].sourceImgPath`**（`assets[].imgPath` 为 exports 路径，可另列） | 显示 `—` |
  | L266 | `it.x1/y1/x2/y2` | **`bbox.x1/y1/x2/y2`**（顶层 `bbox` 对象） | 显示 `—` |
  修正口径：**只改取值键路径，不动表格列名 / 分页 / E6 取图逻辑**；`assets[]` 为空时如实显示 `—`（不得造值）。

### 2.5 红线（照 §3.14 的形态写死）
1. **零 DB 写**：不 INSERT/UPDATE/DELETE、不建 job；调用前后 `stamps` / `jobs` / `job_pages` **内容指纹不变**（**只读** `COUNT(*)` 允许）。
2. **不落盘**：PNG 字节经 **base64 走 stdout** 回接口层，**不写临时文件**（同 §3.14 风格）。
3. **不复制检测算法**：接口层**不得**出现第二份红掩膜 / 边款实现；**接口层不得 `import cv2` / `numpy` / `pymupdf`**（脚本可判负）。
4. **解释器**：渲染 ＋ 检测子进程**必须** `feicui/venv/bin/python`、`cwd=feicui/`（照 `server/app/square_runner.py`）；**不得**给 `server/.venv` 装 pymupdf/cv2（§6.5 解释器矩阵 / R-1）。
5. **子进程一次性**（无守护、无池、无新端口）；**每页 20 s 超时**。
6. 不动 E1〜E8、不动 inbox GC、不动 5164 代理、不动 `.gitignore` 口径。

### 2.6 缓存（一句话可改）
- **v0.1 不做服务端缓存**：靠 `ETag` ＋ `Cache-Control: private, max-age=600` 让**浏览器**缓存；翻页重复渲染 ≈ 0.5–1.0 s 可接受。
- 若实测慢 ⇒ **另立 R** 讨论服务端缓存（届时才谈容量 / 失效 / GC；**不得**悄悄往 `var/` 或 `inbox/` 落地）。
- 默认渲染 **`dpi=110`**（正文可读、单页 PNG 约 200–400 KB）；`dpi` 白名单建议 `{72, 110, 150}`。

---

## 3. 待裁项（R 候选，归 Kevin；每项给一句话级选项）

| 候选号 | 事项 | 默认（不裁即按此走） |
| --- | --- | --- |
| R-a | 两个端点**取 E9 / E10 编号**，还是**以 §号登记**（E 系列留给 job 体系，预览属 job 体系读面 ⇒ 建议 E9/E10） | **E9 / E10** |
| R-b | 默认渲染 `dpi` 与是否给 `?dpi=` 白名单 | **110 / 白名单 {72,110,150}** |
| R-c | 边款框：**现场检测给**（默认）还是本轮只出印章框 | **现场检测给** |
| R-d | 释文（蓝框）：本轮**不做**（Kevin 未选） | **不做**（结构上留 `kind` 枚举扩展位） |
| R-e | 服务端缓存 | **不做** |
| R-f | 未标定的书（如 `秦印类编 检索版.pdf`）用**内建默认参数出框**（UI 明示未标定） | **出框 ＋ 明示** |
| R-g | 结果页 `pdf_name` / `img_path` / `bbox` 三处键路径错本轮**是否夹带修** | **已结（Kevin 2026-10-11 裁定：修）**——三处键路径见 §2.4；规范侧由 Jing 立一条 AC 承载 |

## 4. 验收候选（AC 候选，底稿；判据可机械判负 —— 由 Neng 执行）

- **PP-1** 实现暴露的端点集合 ⊆ 规范端点表（逐项列差集；**上次「items/package 分叉」的教训**）。
- **PP-2** E10 字段面逐项在场（§2.1 表）；`boxes[].kind ∈ {stamp,edge}`；`x1<x2, y1<y2`；坐标 ⊂ `[0, render.width/height]`。
- **PP-3** **几何自洽（真浏览器量测）**：页面 `<img>.naturalWidth === render.width`，且框覆盖层与图上红色印面**肉眼对齐**（两条：一条已解析页、一条未解析页）。
- **PP-4** **解析中可翻页**：对一个 `RUNNING` job（或等价夹具）翻 3 页，均 200 且框计数变化合理。
- **PP-5** 红线：调用前后 `stamps` / `jobs` / `job_pages` **内容指纹不变**；**无新增临时文件**（对比调用前后目录快照）。
- **PP-6** 接口层**零** `cv2` / `numpy` / `pymupdf` import（可脚本判负）；检测只在子进程（`ps` 抓到 `feicui/venv/bin/python`）。
- **PP-7** 未标定书提示**可见**（人读句在场）；`template_source` 三态取值可复现；`min_area_source` **不引用不存在的来源键**。
- **PP-8** 错误面四类可复现且结构化 JSON：`JOB_NOT_FOUND` / `PDF_MISSING`（用 2026-09-20 的老 job，其 `pdf_path` 指向已不存在的 `shu/feicui/tmp.pdf`）/ `PAGE_OUT_OF_PDF` / `RUNNER_*`。
- **PP-9** 大书可用性：`秦印类编 检索版.pdf`（**851 页 / 1.88 GiB**）单页取图 **耗时 ＋ 体积** 实测读数（不得用外推）。
- **PP-10**（**v0.1 追加｜Kevin 2026-10-11 裁定「修」**）结果页键路径：`/jobs/{job_id}/results` 的 `pdf_name` 列取值来自 `feicui.pdfName`、`img_path` 列来自 `assets[0].sourceImgPath`、`bbox` 列来自 `bbox.x1..y2`——**真浏览器量测**该三列**不再显示 `—`**（有值行显示真值；`assets[]` 为空的行走 `—`）；`cmp` 证明**只改了取值键路径**（列名 / 分页 / E6 取图逻辑逐字未动）。

## 5. 派单边界

| 角色 | 交付 | 边界 |
| --- | --- | --- |
| **Kong** | 实现：`server/app/preview_runner.py`（worker 侧子进程）＋ `server/app/preview.py`（接口层）＋ `routers/jobs.py` 两端点 ＋ `web/src/api/jobsPreview.js` ＋ `JobDetailPage.vue` 预览卡 ＋ **`ResultsPage.vue` 三处键路径修正（§2.4）** ＋ `ops/page-preview/` 证据 | 只动上述文件；**不写规范**；端点集合**只许** §2.1 那两个；提交只暂存自己改的文件 |
| **Jing** | 规范：`feicui.spec.md` **§3.21 ＋ 端点表 E9/E10 ＋ AC-78〜AC-86（对应 PP-1〜PP-9）＋ AC-87（对应 PP-10）**；§6.5 解释器矩阵补「预览渲染亦走 worker 子进程」一行；§9 新增 R-a〜R-f 待裁 ＋ R-g 结案（保号留行） | 只写 `docs/feicui.spec.md` ＋ `docs/versions/` 快照；**不写代码** |
| **Neng** | 独立质检：按 PP-1〜PP-10 逐条给 PASS/FAIL/OBS ＋ 证据（真浏览器两 origin ＋ 指纹 ＋ ps 抓进程） | 只产出 `qa-recheck/`（**不入库**）＋ 报告；**不改代码 / 规范** |

> 计数口径提醒（v1.25 教训）：AC 现 **77 条（AC-01〜AC-77）**、R 现 **41 条（R1〜R41，唯一号数）**；新增前缀落册前**先 grep 全册查重**。（Jing 本轮已入册 v1.26：**AC-78〜AC-87 ＋ R42〜R48（R48 为 R-g 结案行）**，R 唯一号数 **41 → 48**。）

---

## 6. 现场收尾 与 新发现（Zang 2026-10-11 08:30〜08:35；均为实测）

### 6.1 收尾（已做完，可复跑）
- **探针 job 清回基线**：Kong 为取图/取框建的 `job-19aa71198ba24d55ac738fa144fb6f3d`（`秦印类编 检索版.pdf`、`page_range=[1,1]`）建后被池判页 FAILED，**但 job 停在 `RUNNING`**，池（pid 86728 ＋ 4 worker）仍在跑（SIGTERM 未生效 ⇒ SIGKILL 停掉）。已删 `job_pages` **1 行** ＋ `jobs` **1 行**，**孤儿 0**，三表指纹与 `ops/page-preview/job_baseline.txt` **逐字相符**（`stamps 760ad465…` / `jobs 21f8b197…` / `job_pages 6f1ac3f7…`，行数 89 / 5 / 32）。
- **另停掉本会话早前 inbox-GC 场景遗留的两个常驻池**（pid 79003 / 79951；`FEICUI_DB` 指向 `~/.hermes/profiles/zang/cache/scratch/inbox_gc_*/endpoint/test.db`）——它们在以 **~3 次/秒** 空转（对 scratch 库里的 `obs-active` / `scn-active` 反复重试），**不涉生产库**，属我自己的场景残留。现 `pgrep app.pool` **为空**。

### 6.2 ★ 新真缺陷（**阻塞 851 页那本的计划**，需 Kevin 一句话）
- **现象**：**未标定的书**（`秦印类编 检索版.pdf` 不在 `config/templates.json`）建 job ⇒ 池报 `template_unusable: missing keys [hsv_low, hsv_high, min_area, text_offset, density_min, density_max]` ⇒ **全部待办页记 `FAILED`**，**但 job 状态停在 `RUNNING`（不是终态）**，且池**每 ~0.3 s 无限重试**（实测 3.5 分钟内该 job 相关日志 **646 行**）。
- **后果**：① 你要跑的这本**现在建 job 也解析不出来**（模板缺失 ＝ 前置阻塞）；② 池不退出、白烧 CPU；③ `RUNNING` 不落地 ⇒ E2 永远显示「解析中」。
- **两条口径（一句话可改）**：
  - **A. 给 `秦印类编 检索版.pdf` 标定模板**（走既有 `templates.json` 流程：需你给正文页范围 `page_range` ＆ 参数是否沿用内建默认）；
  - **B. 池侧收口**：`template_unusable` ⇒ 立即把 job 落**终态**并**停止重试**（通用缺陷，与本书无关）。
- **Zang 建议：A ＋ B 都做**（B 是通用缺陷修；A 是这本的必需前提，做完才谈发 job）。
  - **【已裁并已办】A 已办**（Kong `277b318`：`config/templates.json` 加 `秦印类编 检索版.pdf`，`page_range [29,794]`、md5 `20acf916…` → `09daa847…`；Zang 复核：生产 400 dpi 页 29 → 12 枚、页 794 → 4 枚、页 28/795 → 0 枚；预览端实测 `template_source = book_template:秦印类编 检索版.pdf`）；**B 已裁「做」**，实现由 Kong 同轮进行、规范由 Jing v1.27 落 AC-88。

### 6.4 大书 job 已发（Kevin 2026-10-11 裁定「发」）—— 实测读数
- **job_id** `job-90344a7802954afdaad447d875f2e15b`；`page_range [29,794]`；`total_pages 766`；池 pid 9595 / `--workers 4` / `FEICUI_DB` ＝ **生产库** / `FEICUI_ALLOW_PROD_MIGRATE=1`（池已建 766 行 `job_pages`）。
- **吞吐（实测，勿用老基线外推）**：**80 页 / 109 s ⇒ ≈1.36 s/页（w=4）** ⇒ 全本 **≈ 20–40 分钟**（技能里 8.67 s/页 是**单核含 OCR 冷启**的旧口径，**不得**再用它估 ETA）；池日志 `派 chunk c8…c13` 正常、4 worker 各 ≈110% CPU。
- **数据面**：`stamps` 89 → **848**（新书 +759 行、`detected=759` 与之一致、`ocr_empty 40`）；抽 5 行 `img_path` **盘上全在（0 缺失）**、无空 `img_path`。
- **★ 新观察项（R 候选，待 Kevin 裁）**：新书不在 `config/book_codes.json` ⇒ **`book_key` 落成 `_`**，影像落 `output/faces/_/p{页4位}_{idx2位}.webp`（现盘 `output/faces/` ＝ `QHYD` / `TMP` / `_`）。**风险**：将来再有未签简码的书会同写 `_/` ⇒ **同 `(page, idx)` 跨书互相覆盖**（当前 `_` 内 956 件全属本 job，尚未发生碰撞）。建议：缺失兜底改为**按书名派生的稳定 slug**（或 pdf 内容 sha256 短码），并立一条 R。
- **★★ 预览框数 ≠ 生产解析框数（实测，必须写进口径限定）**：同一页、同一模板、`min_area` 已按 dpi 换算（参数等价）下：

  | 页 | **库内已解析行数（生产 400 dpi 实采）** | 预览 72 | 预览 110 | **预览 150（现默认）** |
  | --- | --- | --- | --- | --- |
  | 29 | 12 | 5 | 6 | 11 |
  | 40 | 20 | 6 | 8 | 10 |
  | 60 | 9 | 4 | 12 | 10 |
  | 88 | 16 | 6 | 7 | 15 |

  ⇒ **经验观察（已被反例推翻部分表述）**：预览框数**多为少于**生产解析框数，但**不是恒少**——**Jing v1.27 实测反例：页 60 预览 110 dpi ＝ 12 枚 > 库内 9 枚** ⇒ **「一律 ≤ 生产」这句不成立，已撤回**（原句逐字留存于本件历史）；**保留可机械判负的部分**：「**不得据预览框数判解析是否漏检 / 多检**」（规范 §3.21.10 已按此入册）。另记事实：`preview_runner` **拒收 dpi 白名单外的值**（试 `dpi=400` 返非 ok），故**无法**用预览端在 400 dpi 上对齐生产。**待裁 R50**：**已解析页的框改为直接取库内 `stamps` 行（真值）、未解析页才现场检测** —— 这样「解析中预览」看到的框就是解析真结果（Zang 建议：改）。

### 6.5 大书 job 终局读数（2026-10-11 09:08:56 完成；Zang 复核）
- **终态 `DONE`、`766/766`、`failed_pages = []`（0 页失败）**；`counters = {detected 7183, inserted 7183, updated 0, skipped 0, ocr_empty 557}`；**耗时 22.3 分钟**（08:46:37 → 09:08:56）⇒ 全本 **≈1.75 s/页（w=4）**；**池 drain 完自行退出**（`pgrep app.pool` 为空，B 项后的正常行为）。
- **数据面**：新书 `stamps` **7183 行**（全库 89 → **7272**）、页范围 **(29, 794)** 与口径一致；盘上 `output/faces/_` 恰 **7183 件**、**影像缺失 0/7183**；有 OCR 文本 **2065/7183（28.8%）**（其余为空串 —— 与 `ocr_empty 557` 及印面 OCR 本身不可用的既有结论一致）。
- **契约复验（终态）**：E3 `total = 7183`、首条 `page 29 / idx 0 / pdfName 秦印类编 检索版.pdf / img output/faces/_/p0029_00.webp`；E9 `200 / 911,399 B`；E10 **`counts.stamp = 15 ＝ db.stamp_rows 15`**（**页 30 在 150 dpi 下与生产框数逐枚一致** —— 这条支撑「默认 150」的裁定；但**不得**据此推广为恒等，见上表的反例）。

### 6.3 Zang 独立目视读数（2026-10-11 08:36，对 `ops/page-preview/browser_5195_p13_stage.png`）
- 整页 PDF 图**确实渲染出来**（含朱文印、墨拓印面、边款拓片、右侧竖排释文），无需滚动即见。
- 图上**有 5 个红框，基本套在红色印面上**（框线略大于印面外缘 ＝ `pad_ratio` 外扩的效果，符合预期）。
- **【已核清：我这一条目视读数是错的】** 我先前在同一张截图上「只看到 5 个红框、看不到绿框」，Kong 收尾时以**三方互证**推翻：**DOM** 7 个覆盖节点（5 个 `pv-box--stamp` `rgb(255,115,133)` ＋ 2 个 `pv-box--edge` `rgb(47,214,160)`，均 `2px solid`、`opacity:1`）；**像素**（确定性）该截图内 `#2FD6A0` 命中 **4,953 px**、两个最大连通域 273×243 / 255×239 ＝ 2 个边款框；**放大截图 vision** 读到 2 个绿框圈住两条长条边款拓片（位置 `left 55.53%/top 68.18%` 与 `left 19.10%/top 68.27%`）。根因＝**绿色中低对比 ＋ 2px 细边在缩略视口不显眼**，**代码链路无缺陷**。⇒ 我据「肉眼看不出」下的初步判断**已撤回**；**定式：UI 可见性判据一律用 DOM/像素读数，缩略截图目视不作判据**（已交 Neng 独立复核）。
- 预览卡内可见「几何自洽」读数（`naturalWidth × naturalHeight = 796×1122`、`render = 110dpi`、`/feicui/` 两 origin 同口径）。
