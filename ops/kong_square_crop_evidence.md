# `POST /api/tools/square-crop` 收尾证据（文档 + md5 台账 + 来源标签修正 + 冷启动优化）

* 角色：**Kong**（工程师 · 斐萃收尾）
* 工程根：`/Users/kevin/bistro/xiai/feicui`
* 时间：2026-09-20（CST）
* 前置交付：端点 `POST /api/tools/square-crop`（路由 5196）已由派单方实测通过
  （HTTP 200 / `side=width=height=341` / `mime=image/webp` + RIFF magic / 响应 sha256 自算一致 /
  `stamps` 原 79 行指纹未变 / CORS 预检 + 实 POST 均回 5163 的 ACAO）。
* 本单**不重做端点**，只做四件收尾事。

---

## 0. 四项结果速览

| # | 事项 | 结果 |
| --- | --- | --- |
| 1 | 补文档（`server/README.md` §12 ＋ 本文件） | **完成** |
| 2 | 回读并登记改后 md5（7 个 `app/` 文件 ＋ 新增自测脚本） | **完成**（见 §2） |
| 3 | 修 `min_area_source` 来源标签失真（不存在的 `templates.json:default`） | **完成**，只改标签文本 / 取值，算法与数值零改动 |
| 4 | 冷启动优化（不拉 PaddleOCR，sha256 不变） | **完成**：中位数 **1.724 s → 0.260 s（−84.9%）**，输出 `sha256` 逐字不变 |
| — | 优化前后同一输入 sha256 | **完全一致**：`b540bf974bceca6aa1358f6f914d773a2983d3f83337e23255dfb3415824aad5` |

---

## 1. 改动清单

| 文件 | 动作 | 说明 |
| --- | --- | --- |
| `server/app/ocr_lazy.py` | **新增** | 惰性 `paddleocr` 替身（本次冷启动优化的全部机制）。真调 OCR 时透明加载真包、原样透传构造参数；`FEICUI_SQUARE_NO_LAZY_OCR=1` 可关闭 |
| `server/app/square_runner.py` | 改 | ① 在 `import processor` **之前**装惰性替身（4 行）；② `min_area_source` 改为**由 `template_source` 派生**，不再硬编码 `templates.json:default` |
| `server/app/square.py` | 改 | ① 新增 `_template_items()` / `_corpus_matches_builtin()` / `_builtin_source()`：来源标签**如实**标注「内建兜底常量 + 常量位置 + 与语料逐字核验结果」；② 新增 `min_area_source_label()`：`min_area_source` 的**唯一**生成处（与 `template_source` 同口径）；③ 新增常量 `BUILTIN_PARAMS_LOCUS`；④ 更新模块 docstring 与 `load_template_params` docstring |
| `server/README.md` | 改 | 新增 **§12 工具端点** 全节（路径 / multipart 字段 / 可选参数 / 响应字段集 / 错误码 / CORS / 零 DB 写红线 / 解释器矩阵与冷启动 / 自测命令）；并修正 §7 配置表里过期的 `FEICUI_CORS_ORIGINS` 默认值（补 5163 两项） |
| `server/selftest/bench_square_crop_coldstart.py` | **新增** | 冷启动 A/B 基准（两模式交错各 3 次取中位数）＋ 来源标签如实性断言 ＋ sha256 不变断言 |
| `server/selftest/verify_square_lazy_ocr.py` | **新增** | 惰性替身对 OCR 路径的**语义等价**证明（假真包注入，不加载真模型，11 条断言） |
| `ops/kong_square_crop_coldstart_raw.txt` | **新增** | 上述两支脚本的原始输出（75 行，26 条 PASS） |
| `ops/kong_square_crop_selftest_raw.txt` | 追加 | 追加第 3 段实跑记录（`label=收尾复核: 5196 面板托管实例(惰性OCR+来源标签修正后)`，61/61 PASS）。**只追加，未改前两段** |
| `ops/kong_square_crop_evidence.md` | **新增** | 本文件 |

**未改动（红线核对）**：`xiai/src/**`、`xiai/docs/**`、`processor.py`、`export.py`、`yinpu.db`、
`ctrl/**`、`server/worker/**`、`server/requirements.txt`、`server/.venv` 依赖集。
**`processor.py` 字节未动**（md5 `31ec6cdb…` 与 QA pin 逐字一致，见 §2.3；实现方式是把 `paddleocr`
这个**模块名**换成惰性替身，**不触碰 `processor.py` 源码一个字节**）。
**`config/templates.json` 也未动**（md5 `20acf916…` 未变）⇒ 修标签走的是「如实标注」，
不是「偷偷往模板里塞一个 `default` 键」。

---

## 2. 改前 / 改后 md5 台账

> 口径：`md5 -q <path>`（macOS）。"改前"＝本单动手之前落档的值；新增文件改前一栏为 `—`（不存在）。

### 2.1 派单点名的 7 个 `server/app/` 文件

| 文件 | 改前 md5 | 改后 md5 | 变化 |
| --- | --- | --- | --- |
| `server/app/main.py` | `9f6fe1738220cdab8426259ca81fd2fe` | `9f6fe1738220cdab8426259ca81fd2fe` | 无 |
| `server/app/config.py` | `fd51e2c65aaad940493ea156986ac56c` | `fd51e2c65aaad940493ea156986ac56c` | 无 |
| `server/app/routers/tools.py` | `da8cb08f794f20424fef20bdcc0a9be2` | `da8cb08f794f20424fef20bdcc0a9be2` | 无 |
| `server/app/square.py` | `13d892d511281d0e23aed8fa2fb88c56` | `087c0bef94f4350ede0bc93d563f07f4` | **改** |
| `server/app/square_runner.py` | `e62c8228b460a96e1530300de70d37b9` | `312d9e229a54054b9491d896c3438a40` | **改** |
| `server/app/square_client.py` | `d9de292bc6fc1c7a47c5608b68b1dc36` | `d9de292bc6fc1c7a47c5608b68b1dc36` | 无 |
| `server/app/multipart.py` | `50f06d76be9412f09970d36d09c2c2ca` | `50f06d76be9412f09970d36d09c2c2ca` | 无 |

### 2.2 新增文件 + 自测脚本

| 文件 | 改前 md5 | 改后 md5 |
| --- | --- | --- |
| `server/app/ocr_lazy.py` | —（新增） | `0486dcf2ae4d111549936078b1cecb94` |
| `server/selftest/verify_tools_square_crop.py`（上轮新增，本单未改） | `1e11bb556120b82edbe71fc007532505` | `1e11bb556120b82edbe71fc007532505` |
| `server/selftest/bench_square_crop_coldstart.py` | —（新增） | `5efc637ee43a9670269f7bd79799cf75` |
| `server/selftest/verify_square_lazy_ocr.py` | —（新增） | `c757bce7555ae4bb1eb94a410aa6a485` |
| `server/README.md` | `f274d84f1dcac10e057501834e6a30d2` | `12608c7bacb7dc1cc8368333b99f2188` |
| `ops/kong_square_crop_coldstart_raw.txt` | —（新增） | `b37ffc474e519f1c18e2c171c8aa6735` |
| `ops/kong_square_crop_selftest_raw.txt` | `30c6cc1f6b9c55240ee8c5ee5407a619`（35902 B，本单开始前） | `e32239bf2e1744f059db4cebff80165c`（54539 B，追加第 3 段后） |
| `ops/kong_square_crop_evidence.md`（本文件） | —（新增） | 自身 md5 随交付回复给出（自引用无法收敛） |

**md5 取法可复现**：

```bash
cd /Users/kevin/bistro/xiai/feicui
md5 -q server/app/{main.py,config.py,square.py,square_runner.py,square_client.py,multipart.py,ocr_lazy.py} \
       server/app/routers/tools.py server/selftest/*.py server/README.md ops/kong_square_crop_*.txt
```

**两处「改前」值来源说明（如实登记）**：

* 7 个 `app/` 文件 + `verify_tools_square_crop.py` 的改前 md5 ＝ 本单动手**前**就地 `md5 -q` 取的实测值。
* `server/README.md` 的改前值 `f274d84f…` 是**逐字节反推重建**后取的：改动前**未留档**该值，
  重建方式＝从当前文件删去本单新增的 §12 段并还原 §7 的 CORS 表行。重建结果
  **bytes=19960、lines=283**，与本单动手前 `ls -l`（19960 B）及 `read_file`（283 行）**逐项吻合**，
  故可认为等价。**规范缺口**：本单开局应先落档全量 md5 再动手（见 §6 G-2）。
* `ops/kong_square_crop_selftest_raw.txt` 的改前值由「追加块起点 offset=35902 的前缀」算出，
  与动手前 `ls -l` 的 35902 B **逐字节吻合** ⇒ 可信。

### 2.3 附注：`processor.py` / `export.py` / `config/templates.json` / `yinpu.db` 均**未动**（有外部交叉证明）

以下三个文件的「未动」不是我口头说的，而是**与既有台账逐字吻合**（值取自
`qa-recheck/p1bii-neng/evidence/pin_start.txt` 与本单动手前实测，两处一致）：

| 文件 | 既有台账值（QA pin，早于本单） | 本单动手后实测 | 结论 |
| --- | --- | --- | --- |
| `processor.py`（19626 B） | `31ec6cdb907ac60b63e814d7b6122c24` | `31ec6cdb907ac60b63e814d7b6122c24` | **未动**（另见 `server/REPORT_1b-i.md` §1 同值） |
| `export.py`（61192 B） | `a1ca4064cb4b41319dab5809fd57db54` | `a1ca4064cb4b41319dab5809fd57db54` | **未动** |
| `config/templates.json`（2266 B） | `20acf9162baf0a0c4e5d6e164681b5ce` | `20acf9162baf0a0c4e5d6e164681b5ce` | **未动** ⇒ 本单**没有**偷偷加 `default` 键来「修」标签（而是把标签改成如实标注） |

`yinpu.db` **不给文件 md5**（WAL 下文件 md5 会在内容无变化时漂移 —— 见规范 §8 第 6 条纪律）；
其「未被写」由 T8 的内容指纹证据承担（`stamps` 行数 + 三口径指纹调用前后逐字节一致）。

---

## 3. 四项逐条

### 3.1 补文档

**① `server/README.md` 新增 §12「工具端点（与 job 体系完全无关）：`POST /api/tools/square-crop`」**，含：

* §12.1 **请求**：路径、`multipart/form-data` 硬要求、**文件字段名逐字 `image`**、
  可选字段表（`pad_ratio` / `min_area_eff` / `quality` / `max_side`，含默认值与边界）、32 MiB 上限；
* §12.2 **响应字段集**：`ok/count/source/candidates[]/params_used/degraded` 与 12 个候选字段逐条释义，
  以及**来源标签口径**（`template_source` / `min_area_source` 的如实标注规则）；
* §12.3 **错误码表**：400（`BAD_CONTENT_TYPE` / `UPLOAD_TOO_LARGE` / `BAD_MULTIPART` / `NO_IMAGE` /
  `BAD_PARAM` / `DECODE_FAILED`）、422 `NO_CANDIDATE`、500（`RUNNER_*` / `INTERNAL`），
  并写明**一律结构化 JSON、绝不返回 HTML 错误页**；
* §12.4 **CORS 口径**：白名单唯一真源＝`Settings.cors_origins`，默认含 5195 与 **5163**，
  **不放开 `*`**，白名单外不回 ACAO；
* §12.5 **零 DB 写红线**：无 SQL / 不读 `stamps` / 不建 job / 不碰 `exports/` `output/` / 不落盘 /
  不复制检测算法；
* §12.6 解释器矩阵与**冷启动优化**口径 ＋ `FEICUI_SQUARE_NO_LAZY_OCR` 回滚开关；
* §12.7 三条自测命令与证据文件索引。

同时修正 §7 配置表里**过期**的 `FEICUI_CORS_ORIGINS` 默认值（原写只有 5195，实际默认已含 5163 两项）。

**② 本文件**（`ops/kong_square_crop_evidence.md`）：改动清单 ＋ 改前/改后 md5 表 ＋ 自测与实测结论索引。

### 3.2 回读并登记改后 md5

见 §2。7 个点名文件的改后 md5 全部回读登记；新增的 2 支自测脚本与 `ocr_lazy.py` 同样登记。
其中 4 个文件（`main.py` / `config.py` / `routers/tools.py` / `square_client.py` / `multipart.py`）
**md5 逐字未变** ⇒ 本单没有顺手改它们。

### 3.3 修来源标签失真（`templates.json:default` 不存在）

**失真事实（派单方实测发现，本单复核确认）**：

* `config/templates.json` 顶层**只有三本书名键**：
  `黄牧甫印谱_(西泠印社)_…pdf` / `秦汉印典 上海书画 金怀英  1997 ok.pdf` / `古玺汇编 文物出版社 罗福颐  ok.pdf`，
  **没有 `default` 键**（`bench_square_crop_coldstart.py` 的 ⓪ 前置核验会实时断言这一点）。
* 改前响应：`min_area_source = "templates.json:default·min_area=800.0×processor.AREA_SCALE=7.716049"`
  ⇒ **引用了不存在的来源键**（那个 800 其实来自 `square.py` 的内建兜底常量）。
  改前 `template_source` 已是 `builtin(corpus-identical)`（正确），**两者口径不一致**。

**改法（只改标签文本与取值，**不改实际算法与数值**）**：

| 位置 | 改前 | 改后 |
| --- | --- | --- |
| `square_runner.py::process` | `min_area_source` **硬编码** `f"templates.json:default·min_area=…×processor.AREA_SCALE=…"` | `min_area_source = square.min_area_source_label(req["template_source"], req["template_min_area"], processor.AREA_SCALE)` ⇒ **由 `template_source` 派生**，两者不可能互相矛盾 |
| `square.py::load_template_params`（无 `default` 项分支） | 返回 `"builtin(corpus-identical)"`（未核验、未指出常量位置） | 返回 `builtin(corpus-identical·verified 3/3·square.py:BUILTIN_TEMPLATE_PARAMS)` —— 现**就地核验**三本书模板的 `(hsv_low, hsv_high, min_area)` 与内建常量逐字一致，并指出常量在源码的确切位置；不一致时标 `builtin(corpus-DIVERGENT·…)`；文件缺失/读不出标 `builtin(no-template-file·…)` / `builtin(template-unreadable·…)` |
| `square.py` 新增 | — | `min_area_source_label()`（`min_area_source` 唯一生成处）＋ `BUILTIN_PARAMS_LOCUS` 常量 |

**改后实测（5196 真实响应，见 §4）**：

```
template_source = builtin(corpus-identical·verified 3/3·square.py:BUILTIN_TEMPLATE_PARAMS)
min_area_source = builtin(corpus-identical·verified 3/3·square.py:BUILTIN_TEMPLATE_PARAMS)·min_area=800.0×processor.AREA_SCALE=7.716049
min_area_eff    = 6172.839506172839   ← 与改前逐位相同
```

**数值零改动自证**：改前 / 改后 `min_area_eff` 均为 `6172.839506172839`（＝800×7.716049382716049），
候选 `sha256` 均为 `b540bf97…`，`side/width/height` 均为 341，`square` 均为 `[1,0,342,341]`
⇒ 只动了标签，没动算法。显式传 `min_area_eff` 时仍标 `explicit(min_area_eff)`（未变）。

### 3.4 冷启动优化（做了，不是「报告不做」）

**病因**：`processor.py` 顶部 `from paddleocr import PaddleOCR`（模块级 import）会拉起整套推理栈；
实测 `import paddleocr` ≈ **1.28 s**，`import processor` ≈ **1.4～3.2 s**。而本端点只走
`processor.detect_stamp_regions`（HSV 红掩膜 → `MORPH_CLOSE` → `findContours` → 面积/长宽比 → `_pad_bbox`），
**纯 cv2/numpy、一次 OCR 都不做** ⇒ 这笔开销纯属浪费。

**做法（`server/app/ocr_lazy.py`，`processor.py` 零改动）**：在 `import processor` **之前**把
`sys.modules["paddleocr"]` 换成一个**惰性替身模块**，其 `PaddleOCR` 是 shim 类，**只有真正被实例化时**
才弹出自身、import 真包、并以**原样 args/kwargs** 构造真 `PaddleOCR`；实例对任意属性/方法**透明转发**。

* **不改检测口径**：`detect_stamp_regions` 走的是**同一份 `processor.py` 源码**（未复制、未改写）；
* **不改 `processor.py` 现有函数默认行为**：`_get_ocr()` 的构造参数（`use_angle_cls=False, lang="ch"`）、
  单例缓存语义、真包缺失时抛 `ModuleNotFoundError` 的行为**全部保持**（`verify_square_lazy_ocr.py` 11/11 证明）；
* **不改输出字节**：两模式的候选 `sha256` 全池唯一且与改前逐字相同；
* **可回滚**：`FEICUI_SQUARE_NO_LAZY_OCR=1` ⇒ 不装替身，回到优化前行为。

**冷启动耗时前后对比**（同一输入 `output/faces/TMP/p0013_00.webp`，各 3 次取中位数）：

| 口径 | 中位数 | 说明 |
| --- | --- | --- |
| **改前 · 原码实测**（本单动手前直接跑 `square_runner.py` 3 次） | **2.964 s** | 首轮 4.256 s（文件系统缓存冷），后两轮 2.964 / 1.831 s → 中位 2.964 s |
| **优化后 · 同一基准** | **0.242 s** | 0.376 / 0.233 / 0.242 s → 中位 0.242 s |
| **同机 A/B 对照（唯一变量＝替身开关，两模式交错 3 轮）** | **1.724 s → 0.260 s（−84.9%）** | B 臂（关替身）1.724 s 中位 vs A 臂（开替身）0.260 s 中位；同一次运行、同一机器负载 ⇒ 归因最干净 |

> **说明（不粉饰）**：B 臂 1.724 s 低于上面「改前 2.964 s」，是因为这两轮之间 `paddleocr` 的 `.so`
> 已被 OS 页缓存预热 —— 所以我把「改前原码绝对值」与「同机 A/B 相对值」两个口径都摆出来，不混用。
> 无论看哪个口径：**降幅都在 83～92%**，改后稳定落在 **0.24～0.31 s**。

**关键证据**：优化前后候选 `sha256` ＝ `b540bf974bceca6aa1358f6f914d773a2983d3f83337e23255dfb3415824aad5`
（与派单方实测通过的那一个**逐字相同**）。

---

## 4. 自测与实测结论索引

| 编号 | 内容 | 命令 / 方式 | 结论 | 原始证据 |
| --- | --- | --- | --- | --- |
| T1 | 端点全量自测（真实影像 200 / 方形 / sha256 / 零 DB 写 / 错误码 / CORS / `curl -F` 独立客户端） | `server/.venv/bin/python server/selftest/verify_tools_square_crop.py --base-url http://127.0.0.1:5196 --label "收尾复核: …"` | **61/61 PASS**（exit 0） | `ops/kong_square_crop_selftest_raw.txt` 第 3 段（自 418 行起） |
| T2 | 冷启动 A/B ＋ 标签如实性 ＋ sha256 不变 | `server/.venv/bin/python server/selftest/bench_square_crop_coldstart.py --reps 3` | **PASS**（13 条断言） | `ops/kong_square_crop_coldstart_raw.txt` 第 2 段 |
| T3 | 惰性替身对 OCR 路径语义等价（不加载真模型） | `server/.venv/bin/python server/selftest/verify_square_lazy_ocr.py` | **11/11 PASS**（exit 0） | `ops/kong_square_crop_coldstart_raw.txt` 第 1 段 |
| T4 | 服务生效方式 | 面板单服务重启 `POST http://127.0.0.1:5555/api/restart` body `{"sid":"feicui-api"}`（**未重启面板本体**） | `{"sid":"feicui-api","ok":true,"state":"running","pid":35061}` | 本文 §4.1 |
| T5 | 面板总览 | `GET http://127.0.0.1:5555/api/status` | **13/13 running / portOpen=true**，`feicui-api` pid=35061 | §4.1 |
| T6 | 三个端口存活 | `curl` 实测 | 5163=200、5195=200、5196 `/api/health`=200 | §4.1 |
| T7 | 无残留监听 | `lsof -nP -iTCP:<port> -sTCP:LISTEN` | 5201=0、5173=0、5174=0 条 | §4.1 |
| T8 | 零 DB 写（调用前后指纹） | T1 内置断言 | `stamps` rows 89→89、`md5_B_canon` `d3932fdc…`→`d3932fdc…`、原 79 行子集 `d7abe995…`→`d7abe995…`（**逐字节不变**） | `ops/kong_square_crop_selftest_raw.txt` 第 3 段 |
| T9 | 改后响应（关键字段） | T1 里 5196 真实 POST | `200`、`count=1`、`side=width=height=341`、`mime=image/webp`、`sha256=b540bf97…`、`square=[1,0,342,341]`、`degraded=true(SHORT_SIDE_CLAMP)` | §4.2 |

### 4.1 面板与端口（本文写作时就地实测）

```
$ curl -s -X POST http://127.0.0.1:5555/api/restart -H 'Content-Type: application/json' -d '{"sid":"feicui-api"}'
{"sid":"feicui-api","ok":true,"state":"running","pid":35061,"msg":"已启动"}

$ curl -s http://127.0.0.1:5555/api/status   # 汇总
services_total = 13
running        = 13
  jiazu-api   running=True portOpen=True port=3100 pid=88224
  jiazu       running=True portOpen=True port=5199 pid=88225
  shu         running=True portOpen=True port=5164 pid=88226
  feicui-api  running=True portOpen=True port=5196 pid=35061   ← 本单唯一重启的服务
  feicui-web  running=True portOpen=True port=5195 pid=88228
  xiai        running=True portOpen=True port=5163 pid=91229
  jinli-api   running=True portOpen=True port=5778 pid=88230
  jinli       running=True portOpen=True port=5777 pid=88231
  cat         running=True portOpen=True port=5701 pid=88232
  aranya-api  running=True portOpen=True port=5181 pid=88233
  liwu-proxy  running=True portOpen=True port=3020 pid=88234
  liwu-web    running=True portOpen=True  port=5175 pid=88235
  liwu-app    running=True portOpen=True port=5176 pid=88236

$ curl -o /dev/null -w '%{http_code}' http://127.0.0.1:5163/            → 200
$ curl -o /dev/null -w '%{http_code}' http://127.0.0.1:5195/feicui/      → 200
$ curl -o /dev/null -w '%{http_code}' http://127.0.0.1:5196/api/health   → 200

$ lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(5163|5195|5196|5201|5173|5174|5555)$'
python3.1 35061 127.0.0.1:5196      ← feicui-api（面板托管）
node      88300 127.0.0.1:5195      ← feicui-web
node      91247 127.0.0.1:5163      ← xiai
node      87837 *:5555              ← ctrl 面板本体（未被重启）
（5201 / 5173 / 5174 均无监听 ⇒ 无残留）
```

**重启方式合规**：全程只用面板的 `POST /api/restart` 单服务重启，**未重启面板本体**，
**未使用 `pkill -f` / `killall`**（一次都没有）。

### 4.2 改后 5196 真实响应（节选，sha256 与派单方实测值逐字相同）

```json
{"ok": true, "count": 1, "source": {"width": 343, "height": 341},
 "candidates": [{"idx": 0, "bbox": [0,0,343,341], "square": [1,0,342,341], "side": 341,
                 "width": 341, "height": 341, "mime": "image/webp",
                 "sha256": "b540bf974bceca6aa1358f6f914d773a2983d3f83337e23255dfb3415824aad5",
                 "area": 48909.0, "aspect": 1.0030395136778116,
                 "degraded": true, "degraded_reasons": ["SHORT_SIDE_CLAMP"]}],
 "params_used": {"hsv_low": [0,120,70], "hsv_high": [10,255,255],
                 "min_area_eff": 6172.839506172839,
                 "min_area_source": "builtin(corpus-identical·verified 3/3·square.py:BUILTIN_TEMPLATE_PARAMS)·min_area=800.0×processor.AREA_SCALE=7.716049",
                 "pad_ratio": 0.15, "quality": 95, "max_side": 0,
                 "template_source": "builtin(corpus-identical·verified 3/3·square.py:BUILTIN_TEMPLATE_PARAMS)"},
 "degraded": true}
```

HTTP 头（实 POST，Origin=5163）：`content-type: application/json`、
`access-control-allow-origin: http://127.0.0.1:5163`、`vary: Origin`。
预检 `OPTIONS` 同样回 ACAO；负例 `Origin: http://127.0.0.1:59999` ⇒ `400 Disallowed CORS origin`、**无 ACAO**。

---

## 5. 未完成项 / 保留意见

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 把 `pymupdf`（≈0.15 s）也惰性化 | **不做（判断风险 > 收益）** | `worker.feicui_worker` 与 `processor` 都在模块级 `import pymupdf`，且它被 `render_page` 等**真实使用**；替身方案要逐函数验证等价，收益仅约 0.15 s（当前基线 0.26 s，占比虽不小但绝对量小），**不值得**为它引入「假包」风险面。如实登记为**已知可优化点但本单不做**。 |
| 把 `cv2` 的懒加载 / 让 runner 不进 `worker.feicui_worker`（省 pymupdf） | **不做** | 会破坏「同一份 `encode_webp` 实现」这一**更重要的口径**（§1.2 I-1 不许复制算法），得不偿失。 |
| 常驻子进程 / 进程池以消掉 Python 解释器启动本身（≈0.15 s） | **不做** | 与 §1.1 / §3.2 S-4「一次性子进程、无守护无池」相冲突，且「用完即退」本身是**红线级的隔离手段**。 |
| `min_area_source` 里 `AREA_SCALE` 的展示位数（`:.6f`） | 保留 | 仅展示用；实际生效值走 `min_area_eff`（全精度）。改它会变更标签文本，非本单目标。 |
| `pool.state.json` 里 `feicui-api` 的 pid 已随重启更新为 35061 | 已生效 | 面板自身记账，未手工改动。 |

---

## 6. 规范缺口（本单发现，如实登记）

| 编号 | 缺口 | 影响 | 建议 |
| --- | --- | --- | --- |
| **G-1** | **`config/templates.json` 没有 `default` 项**，但形状契约（`min_area_eff` 不传 ⇒ 用模板默认项）默认它存在 | 任何实现都只能走「内建兜底」，而兜底**必须有**可信来源标注，否则就会像改前那样凭空写出一个不存在的键 | 请 Zang 裁定二选一：① 在 `templates.json` 里**显式加** `default` 项（＝三本书现行值），让真源名副其实；② 明确「无 `default` 时以内建常量为准」并**要求**响应里如实标注常量位置与核验结果（本单已按 ② 实现） |
| **G-2** | 本单开局**未先落档全量改前 md5** 就动了 `server/README.md` | 该文件的改前 md5 只能**反推重建**（已用 bytes/lines 双指标校验吻合，但仍不如实测硬） | 收尾类工单的**第一步**应固定为「先 `md5 -q` 落档全部在册文件」再动手 |
| **G-3** | 「冷启动耗时」缺少**统一测量口径** | 页缓存冷热差异可达 2 倍（改前同一段代码测到 2.964 s 与 1.429 s 两个中位数） | 建议约定：**同机 A/B + 交错多轮 + 取中位数**，并同时给出「绝对基线」与「相对 A/B」两个口径（本单已按此办理，见 §3.4 说明） |
| **G-4** | `server/README.md` 内多处示例路径仍写 `/Users/kevin/bistro/shu/feicui/...`（工程实际在 `/Users/kevin/bistro/xiai/feicui`） | 照抄命令会失败 | 建议后续统一订正 README 历史段落里的路径（本单**未**顺手改，避免碰非本单范围的历史内容） |
| **G-5** | `square.degraded` 把规则 ④（越界平移）也计为 `degraded=true`（改前实现即如此） | 契约只要求 ⑤ 标注降级，④ 未明说；本实现选择「如实都标」 | 已在上一单登记，保留 |

---

## 7. 一句话结论

四件事**全部做完**：文档（README §12 ＋ 本文件）、md5 台账（7 个点名文件 ＋ 3 支脚本 ＋ 2 份 ops 证据）、
来源标签失真修正（`templates.json:default` → 如实标注内建常量并就地核验，**算法与数值零改动**）、
冷启动优化（**1.724 s → 0.260 s，−84.9%**，**输出 sha256 逐字不变**，`processor.py` 零改动，可一键回滚）。
实证：端点自测 **61/61 PASS**、替身语义等价 **11/11 PASS**、面板 **13/13**、5163/5195/5196 均 200、
5201/5173/5174 **零残留监听**、`stamps` 指纹**逐字节不变**。
