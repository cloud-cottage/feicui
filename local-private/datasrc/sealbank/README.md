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

## 礼貌纪律（硬约束）

1. 请求间隔 **≥ 2 秒/请求**；
2. 引用 / 产出**注明来源「真微印網 sealbank.net」**；
3. **不镜像大图**；
4. 数据**仅自用、不公开分发**。
