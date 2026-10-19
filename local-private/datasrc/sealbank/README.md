# datasrc/sealbank/ —— 真微印網（sealbank.net）数据源工作面

**站点**＝真微印網 www.sealbank.net（台湾）。经典 ASP；**全站 Big5 编码**
（解码一律 `text.decode("big5", errors="replace")`）。
**官方口径**：统合 133,883 笔、印人档 10,487、印章档 81,281、印谱 5,194、论文 8,679、
事迹 5,674、影像 121,796 张。

## URL 地图（2026-10-19 父级一手取证）

- 印人编年列表：`m2MainFind.asp?LM=2&L1=2&L2=2&L3=0&LS=C&SRCHTXT=<印人编号 Q9xxx>&SK=MV`
  （分页参数 `PN=2..N`）
- 印章详情：`m2ImgShow.asp?STOP=M2IMGS&LM=2&L1=2&L2=1&L3=0&LS=C&SRCHTXT=<印章编号「年-序」，如 1799-061>`
  （会员面）
- 缩图直链：`SBYBImg/red80/<印章编号>.gif`（**匿名 200**）
- 公开入口：`m3MainFind.asp`（數位印譜 6 单元 / 537 種 / 41,665 枚）、`m7MainFind.asp`（站主 2,721 笔）
- 会员墙：`mmbLoginPopup.asp`；m1/m2 印库搜寻未登录 302 / 超时

## 权限表

| 等级 | 可见 |
| --- | --- |
| 非会员 | 篆刻年歷**文字全开**（2011 起官方全开）＋ 80px 缩图 |
| 一般会员 | 原始完整图（300DPI 打印＝实际尺寸）＋ 完整事歷 |
| 赞助会员 | 论文 / 序跋全文（8,679 篇 / 291 万字） |

## 印人编号：稠密带洞

Q9899 / Q9900 / Q9903 空；Q9901＝吳熙載（467 则 / 32 页）、Q9902＝何紹基、Q9910＝王聲。

## 登录态（cookies.txt）

- 本目录 `cookies.txt` **绝不入库**（`.gitignore`：`local-private/datasrc/*/cookies.txt`）。
- 2026-10-19 Cookie 实测：账号有效，但「餘點 0、有限度瀏覽」，详情页未出印图
  ⇒ **Layer2 原图待验证**。

## 产出

- 抓取产出落 `out/`：`out/*` 不入库（`.gitkeep` 占位除外）；NDJSON 小件是否入库后续再议。

## 抓取器（2026-10-19 · 本目录 `client.py` / `to_xiai.py`）

`client.py`（纯逻辑层，stdlib urllib，零 GUI；transport 可注入 ⇒ 假层直测）：

| 项 | 值 |
| --- | --- |
| 限速 | 默认 **2.2s/请求**（`--rate` 可配，**硬下限 1.5s**）；跨进程共享（启动读 `out/requests.log` 尾行暖启动） |
| UA | `feicui-research/1.0 (sealbank study; contact: repo issues)` |
| 超时 / 重试 | 40s；429/5xx/超时 指数退避 2→4→8s，**≤3 次**（实测 500 两例：21s→退避→200，无重复写入） |
| 编码 | 全站 Big5（`decode('big5', errors='replace')`） |
| 返回 | 一律结构化 dict（`ok/status/bytes/elapsed_ms/retries/error`），**不抛** |
| cookie | `cookies.txt` 只在请求头；不进日志/报错/产出（`_sanitize` 兜底抹除） |

```bash
python3 client.py scan                              # 编号定界扫描 → out/boundary_scan.json
python3 client.py persons --ids Q9901,Q9902,Q9910   # 编年全分页 → persons/entries.ndjson + PROGRESS
python3 client.py seals --ids 1799-061,...          # 会员面详情样本（带 cookies）
python3 client.py thumb --id Q9901001               # 匿名 80px 缩图（1 张，验尺寸）
python3 client.py report                            # 完整度 + 计数对拍
python3 client.py selftest                          # 假 transport 直测（零网络）
```

断点续传：`out/PROGRESS.json` 记 `pages_done` / `total_pages` / 失败清单；重跑**跳过已完成页**、
失败页补抓（实测：Q9901 限 3 页 → 重跑，3 页 0 新请求、全 32 页补齐）。NDJSON 为 append-only
逐行 flush ⇒ 若手工删 PROGRESS 重跑会重复行，属预期（删行重来即可）。

### 实测结论（2026-10-19）

- **编号定界**（29 请求 / 11 命中）：有效区间 **Q9901–Q9912**（Q9903 空号；Q9900、Q9915+ 全空；
  Q8000–Q9500 与 Q10000–Q15000 全空）。命中：Q9901 吳熙載 467 則/32 頁、Q9902 何紹基 30/2、
  Q9904 張瑜 3、Q9905 劉位坦 2、Q9906 羽倉可亭 5、Q9907 黃世本 2、Q9908 吳珍錫 2、Q9909 劉會和 2、
  Q9910 王聲 2、Q9911 汪昉 6、Q9912 吉村鷲原 2。**注意**：上一人/下一人链接出现 `P5202`/`S0207`
  前缀 ⇒ 印人编号不止 Q 段，全站枚举需另走「依人物瀏覽/姓名搜尋」索引（本单未探）。
- **小样本验收**：Q9901 467/467 则（32/32 页）、Q9902 30/30、Q9910 2/2——**计数对拍全绿**。
  499 条编年条目字段非空率：year 100%、text 100%、entry_no 100%、seal 引用 443/499（88.8%）、
  真微書屋註 18/499。persons 字段：name/years/place/bio_head 3/3（place/bio_head 取首条「生」条目）。
- **Layer 2（餘點 0）**：5 枚详情页（1799-061/1818-027/1822-018/1832-039/1842-032）带 cookies
  均 200 但**只剩站点框架**（≈13.2KB，0 字段、0 图 URL）；页头自述「會員餘點0／目前只能作有限度瀏覽」
  ⇒ **原始图与完整释文/边款/石料/尺寸/出处均不可得**（原始图 1 点/枚，需儲值）。
  匿名 80px 缩图可达：`SBYBImg/red80/Q9901001.gif` 200 / 10,739 B / GIF 292×286（已存
  `out/sample/` 1 张，仅验尺寸）。缩图编号是人内序号（`Q<印人><3位>`），与「年-序」印章编号**两套**。
- **xiai 映射器** `to_xiai.py`：按 xiai `xiai_seal_imports` 封闭键面（seed.js:919-1105 / ops.js:329）
  产出候选；3 枚样本 → `out/xiai_imports_sample.ndjson`（本地形态门 0 违规）。**未写 xiai 主库/未动 xiai 仓**。

### 全量估算（启动权在用户，本单未跑）

官网口径印人 10,487 / 編年 133,883 则 ⇒ 每页 15 则 + 每人页 1 次 ⇒ **≈19,400 请求**；
按 2.2s/请求 ⇒ **≈11.9 小时**（不含重试/失败）。建议**每人一批 500 印人**（≈890 请求、≈33 分钟/批，
共 21 批），PROGRESS 断点续传；每批结束后 `report` 对拍。另需先解决编号枚举（P/S/Q 三段 + 索引页）。

## 可用面与硬边界（2026-10-19 用户决定）

**① 不储值会员点数 ⇒ 原始图与完整释文永久不可得。**
用户已决定**不为会员点数储值**。站点原始图计点（1 点/枚），未储值即无法取得
`SBYBImg/` 下的大图与完整释文（印文 / 边款 / 石料 / 尺寸 / 出处）。
这是**永久边界**，不是待办：**后续任何单子都不得再派「抓原图 / 抓完整释文 / 试详情页」**。
（已实测：餘點 0 时详情页 200 但只剩站点框架，0 字段 0 图 URL；见下「Layer 2」条。）

**② 可用面（公开、匿名可达，可放心全量）**
- **篆刻年歷编年文字**：2011 年起官方全开，与书籍版同文（`m2MainFind.asp` 印人页全分页）；
- **缩图** `SBYBImg/red80/<编号>.gif`：匿名 200，实测 **292×286**（文件名 red80 只是历史命名，
  并**不是** 80px）——可作缩略图引用，**不得镜像大图**；
- **印人索引**：`m2ViewIndex.asp?LM=2&L1=2&L2=2&L3=0&LS=C`（依人物瀏覽＞姓名檢索）——
  按姓氏首字繁體筆劃分组，**400 个 `n1sttxt` 槽**，每槽一页给出该姓氏全部印人
  （`编号 / 姓名 / 字號 / 生卒 / N則`），**无分页**。这是全量印人的唯一可靠入口。

**③ 由此决定 xiai 映射口径**
`material / seal_cc（尺寸）/ seal_ly（出处）` 在 xiai 侧**恒为 null**；`transcription`（釋文）
恒为空串（xiai 既有 8 键允许空串默认）；`seal_ytsw_url`（原图 URL）恒为 null。
这些都是**设计结果**，不是抓取缺陷，也不是待补项。可映射的只有：印人（name/zi_hao/years/
place/bio_head）、编年条目（year/text/entry_no/note/book_ref/seal 引用）、
以及 red80 缩图的引用路径（`seal_yt_url` / `image_status=present`）。

**④ 编号体系是多字母段**
印人编号不止 Q 段：实测命中 `Q / P / R / S / O / N / L / J / A / M` 等前缀
（Q8000–Q15000 大段为空、Q 段仅 Q9901–Q9912 命中即为反证）。
⇒ **禁止再用猜编号的方式枚举印人**（编号定界扫描只作旁证）；全量一律走索引页。

## 礼貌纪律（硬约束）

1. 请求间隔 **≥ 2 秒/请求**；
2. 引用 / 产出**注明来源「真微印網 sealbank.net」**；
3. **不镜像大图**；
4. 数据**仅自用、不公开分发**。

## 书版三索引（sbidxtxt.zip）与 xiai 映射（2026-10-19）

**来源**：站内免费「索引檔下載」`sbidxtxt.zip`（195 KB，2001-06-17 生成，Big5）。
这是《篆刻年歷 1051-1911》**纸书配套索引**，覆盖书范围，**非全库**（全库印章档 81,281 枚）。

| 文件 | 记录数 | 字段 |
|---|---|---|
| 篆刻年歷印文索引 | **5,529** | `年-序／刻印者／印面文字` |
| 篆刻年歷人名索引 | **3,342** | `年-序／人名字號籍貫`（长传） |
| 篆刻年歷書目索引 | **2,264** | `年-序／主題人物／年歷事態／書籍名稱` |

**★ 编码坑**：纯 `big5`／`cp950`／`big5hkscs` 都会在 **ETen 扩展区**字节（如 `0xFCB7`、`0xFE74`）抛错
⇒ 必须 `iconv -f BIG5-ETEN`；16 个私用区字形**不猜**，记 `◎{big5:0xXXXX}`：
`name_plain` 剥除占位、`glyph_notes` 记录原码。

**解析要点**：源文件存在「一行挤两条记录」（印文 3 行、人名 16 行、书目 1 行）⇒ 按 `年-序` 边界拆分，
记录数 ≥ 行数；3 个人名 seq 重复（书内同年异人共用编号）**原样保留不合并**。
字段非空率：印文 seq/year/author/seal_text 100%；人名 name 100%、bio_raw 97.1%、zi 72.9%、
hao 47.7%、place 77.5%、**birth/death 0%**（源文本无显式生卒年写法，恒 null，**未编造**）。

### 与网页数据的关系（JOIN）

三索引与网页印章详情页**同一套 `年-序` 编号**（网页 `SRCHTXT=1799-061` ⇔ 索引 `1799-061`，**3 位补零**）。
实测 JOIN **5/5**（书版 seq → 印人编号 → 网页编年页反查，编号与印文内容双向一致）。
⚠ 直接拿 seq 查 `m2MainFind.asp` 返回「共有 0 則」——该端点只认**印人编号**，故走「印人页反查」。

### ★ xiai 采纳规则（无图能否入库）—— 读代码＋规范实证

**结论：可以，走 `image_status='source_no_image'`，无需入库先行。**

- 提交门 `cloudfunctions/xiai-user-token/lib/ops.js:2117-2121`：
  `faces.length===0 && image_status !== 'source_no_image'` 才拒（`MISSING_REQUIRED`）；
- 采纳门 `buildSealAcceptanceFromImport`（`ops.js:2465-2543`）：影像校验只在遍历 `row.faces` 时发生，
  `faces=[]` 循环零次 ⇒ `{ok:true}`；
- 规范 `docs/versions/xiai.spec.v1.65.md:7907-7909`（AC-552/553/554）。

⚠ **red80 缩图不能当占位图**：`red80` 编号是「印人号 + 人内序号」（如 `R0102001.gif`），
与书中「年-序」是**两套编号**，无法对齐；且站方要求不镜像。

### 字段映射（`to_xiai.py index`）

| xiai 键 | 来源 |
|---|---|
| `source` | 恒 `真微印網 sealbank.net` |
| `source_seal_id` | `年-序`（幂等键 `source+source_seal_id`） |
| `seal_wen`（印面文字） | 印文索引·印面文字 |
| `author` | 印文索引·刻印者 |
| `dynasty` | 由年份推导 ⇒ **必须落 xiai `DYNASTY_OPTIONS` 15 类**（`src/data/db.js:2250`；旧写「清」「明」会被 `INVALID_VALUE` 拒），粗分落 `raw_json.derived.dynasty_coarse` |
| `transcription` | 空串（**不是 null**） |
| `material / seal_cc / seal_ly / seal_ytsw_url` | null |
| `image_status` | `source_no_image` |

**朝代分段规则**：宋 ≤1279、元 1280–1367、明早中期 1368–1521、晚明 1522–1643、
清初 1644–1735、清中期 1736–1820、晚清 1821–1911（更替年归新朝）。
实测分布：宋元 6 / 明早中期 4 / 晚明 135 / 清初 215 / **清中期 1,160** / **晚清 4,009**（合计 5,529）。

### 产出

- `out/idx_seals.ndjson`（5,529）、`out/idx_persons.ndjson`（3,342）、`out/idx_biblio.ndjson`（2,264）
- **`out/xiai_imports_sealbank.ndjson`（5,529 行 / 5.4 MB）** ⇒ xiai imports 候选
- `out/idx_parse_report.json`、`out/idx_join_verify.json`

### 已知残留（不编造，原样保留）

- 印文 4 处、人名 31 处含 `◎{big5:…}` 占位 ⇒ **展示层需能渲染该记法**，否则出现裸码；
- 3 条源文件印文尾部带字面 `腹H`／`均H`（源文件如此，非解码错误）；
- 采纳后正式 `xiai_seals` 行不带 `image_status` ⇒ 下游判「无图」只能靠「零 faces」。
