# webp 退场 · 独立质检证据（Neng / 2026-10-11）

本轮：**全量出图（7272 枚 TIFF）＋ webp 退场（删除 15,247 件）＋ E6 改优先 `img_path_tiff`→PIL 回 PNG
＋ worker 停写 webp（只出 TIFF）** 的独立质检。**六项逐项独立读数**（工具：`feicui/venv` 图像栈 /
`server/.venv` 接口层 / 真浏览器 / 系统 `sqlite3`；**只核验，未改任何产物 / 库列值 / 文件，未建 job**）。
机器读数见同目录 `verify_20261011_104700.json`。

## 环境事实

- 仓 `/Users/kevin/bistro/xiai/feicui`，分支 `main`，HEAD `58c879f`；库 `/Users/kevin/bistro/xiai/data/yinpu.db`。
- API pid 28067（`./.venv/bin/python -m app.main`，启动 10:40:47 > 源文件 mtime）；5196＝API、5195＝前端 dev、5164＝对外入口（**必须 `localhost`**，`127.0.0.1:5164` 实测 connection refused）、5555＝ctrl 面板。
- `stamps` 现 **7472 行** = 回填 **7272**（`img_path_tiff` 非空）＋ **200**（黄牧甫印谱 live-job，`img_path_tiff` 全 NULL；见 F1）。

## ① worker 单页运行态（不建 job，输出指向 scratch）—— **PASS**

直调 `process_page(doc, 13, tmpl, "TMP", "tmp.pdf")`，`FEICUI_BOOKS_DIR/FACES_DIR` 指向 scratch。
对比 `git show f9be1d4:server/worker/feicui_worker.py`（TIFF+webp 双份，＝改造前）与 HEAD（只 TIFF）。

| 项 | 改造前 f9be1d4 | 改造后 HEAD |
| --- | --- | --- |
| 产出文件 | 18（6 TIFF ＋ **12 webp**：6 faces ＋ 6 named） | 6（**只 6 TIFF**） |
| 新写 webp | 12 | **0** |
| 旧 faces webp 重建 | 6 | **0**（scratch faces 目录 0 件） |
| 命名正则 `^P\d+-C\d+-R\d+\.tiff$` | — | 6/6 命中，**补零 0** |
| 页内 (C,R) 唯一 | — | 6 枚 6 唯一 |
| 返回 col/row/img_path_tiff | — | 齐（`img_path_tiff` 指新落点、`img_path` 仍回旧 webp 串） |
| 单页耗时（预热后 min×3） | 1158.5 ms | 944.3 ms（**−214.1 ms / −18.5%**） |

> 新 worker 少编一份 webp ⇒ 反而更快。页 13 六枚 (C,R) ＝ `C1R1 C2R1 C3R1 C4R1 C4R2 C4R3`。

## ② E6 双 origin 真浏览器实测 —— **PASS**

- **curl**（同一 job `job-502016dd…`，page 13/idx 0）：三 origin（`127.0.0.1:5196` / `127.0.0.1:5195` / `localhost:5164/feicui`）**均 `200`**，`content-type: image/png`、`content-length: 347`、magic `89504e470d0a1a0a`（PNG）、`x-feicui-img-path: output/books/tmp.pdf/P13-C1-R1.tiff`（来源＝`img_path_tiff`）。
- **真浏览器**：`localhost:5164/feicui/jobs/<jid>/results` 与 `127.0.0.1:5195/feicui/jobs/<jid>/results` 均渲染结果页 → 点「**取裁图**」→ `<img class="stampimg" src="/feicui/api/jobs/<jid>/stamps/13/0/image">` **naturalWidth=123 / naturalHeight=122 / complete=true**（两 origin 一致）。
- **像素无损**：E6 回吐 PNG 解码像素 ≡ 源 TIFF（`123×122 RGB`，逐字节相等）。
- **404 原因码未改**（探不存在的 page/idx）：`JOB_NOT_FOUND` / `STAMP_NOT_FOUND` / `IMAGE_UNAVAILABLE` 三类同 404，`BAD_PARAM` 仍 400；验证 (#3 用黄牧甫 job 探到 `IMAGE_UNAVAILABLE`)。

## ③ 删除后果对账 —— **PASS（4 本口径）／存量另见 F1**

- `img_path_tiff` **在盘率 7272/7272**；`stamps.img_path` 指向文件**缺失 7239/7272**（webp 已删，**预期**）。
- **无一行因删除失去影像**：7272 行 scoped 全部仍有 TIFF 可依（`img_path` 回退面丢、`img_path_tiff` 兜住）。
- **孤儿 webp 清算**：删除前盘面观测 output 下 `webp 14698 / 未派生 184`；现 output 下 webp **仅剩 3 件样本**、**未派生 0** ⇒ 孤儿已清。qa-recheck/** 0、exports/** 0。
- **保留件**：`server/selftest/evidence/**` **475 件** webp ＋ 3 件手写样本（`output/秦汉印典 …/田用海厦.webp`、`右馬廐將右馬廐.webp`、`p8_7.webp`）**均在盘**。
- **印章线一字未动**：`var/seal_images` **6348 件 JPEG**（mtime Oct 10 17:26）、`var/seal_images_tiff` **6347 件 TIFF/deflate**（mtime Oct 10 18:25）——均早于本轮删除（Oct 11 10:37），且删除清单**零命中** `var/` / `seal_images`。
- **删除清单**：`~/.hermes/profiles/zang/cache/scratch/webp_deleted_manifest.txt`，**15247 行 / sha256 `44d40aab74d19109870045efc1860c3975e4f385a76b07ec0f7e0ba3574b37e2`**；原始字节和 **252,962,670 B（241.24 MiB）**，4K 块对齐和 **284,192,768 B（271.03 MiB）**（「271 MB」＝ du 口径）。

## ④ retire_webp.py 现跑 dry-run —— **★ 与期望不符（3 待删 / 0 豁免）**

现跑（`server/.venv/bin/python -m app.retire_webp`）：

```
stamps 行数：7472
将删：3 件 / 3 行 / 55850 B（0.05 MB）   · 将删[other]：3 件
豁免：0 件 / 0 行
盘面观测：output 下 webp 3 件；未被任何行派生到（不删）0 件
```

**与删除前历史读数（`retire_webp_dryrun_20261011_103822.json`：14514 件 / 213.51 MB，books 7272 + faces 7193 + other 49；census on_disk 14698 / 未派生 184）的差异**——父级已**先一步手动删**，且删得**比脚本口径更宽**：

- 手动删 **15247** = 脚本会删的 **14514** − **3 件样本**（脚本会删、父级保留）＋ **184 孤儿**（脚本不动、父级删了；其中 faces 161 / other 20 落在 output）＋ `qa-recheck/**` **434** ＋ `exports/**` **118**（**脚本只走 output/，本就不在处置面**）。核算完全闭合。

**★ 关键出入**：期望「**0 待删 / 0 豁免**」，实际 **3 待删 / 0 豁免**——那 3 件「保留的手写样本」**由库行 66/72/79 派生**（`img_path` 直指它们、且 `img_path_tiff` 非空＋TIFF 在盘 ⇒ **过安全闸**）。⇒ 脚本口径与「保留 3 件样本」的意图**冲突**（脚本无「手写名样本」豁免分支）——见 F2。

## ⑤ AC-97〜AC-104 抽查（每项一条独立读数）

| AC | 读数 | 判 |
| --- | --- | --- |
| **AC-97** 名字形/不补零 | 7272 枚逐一匹配 `^P[0-9]+-C[0-9]+-R[0-9]+\.(tiff\|webp)$`，**不合形 0 / 补零 0** | PASS |
| **AC-98** 页内 (C,R) 唯一 | 779 页，**重复 (C,R) 0 页**；页级 `count(*) = count(distinct (c,r))` **0 页不符** | PASS |
| **AC-99** `P`＝`stamps.page` | 7272 枚文件名 P **≠** 库 page **0**；文件名 C/R **≠** 库 col/row **0** | PASS |
| **AC-100** 双向无孤儿无缺失 | 库行 7272 ↔ 盘上 TIFF 7272（4 本口径），**missing 0 / orphan 0**，两侧计数相等 | PASS |
| **AC-101** 目录键可溯源 | 5 本 `dir_key_source` ∈ {ISBN,chinese_title,pdf_name_unconfirmed}；`_` 兜底目录**不存在** | PASS |
| **AC-102** 红线指纹 | `stamps` 前 10 列**逐字未改**、只增 `col/row/img_path_tiff`（`PRAGMA table_info`）；**但** output/faces 既有 7354 件 webp 已删 ⇒ 与 AC-102「文件数不减」**冲突**（见 F4） | **矛盾** |
| **AC-103** 幂等（**按解码像素**） | 同页两次 worker 跑：6/6 **解码像素逐字节相同**；文件 `sha256` 6 枚中 **1 枚不同**（P13-C2-R1，＝Pillow tiff_deflate 非确定，作观察）。**未按文件 sha256 判**。 | PASS |
| **AC-104** V3 前景保真 | 页 13 六枚：**IoU 全 1.0（≥0.98）**；`other` 桶逐像素不变率**全 1.0**；背景（paper 桶）**纯白像素占比 1.0**；`delta_e_after` 11.4〜12.4（**仅读数**，AC-104 不设该阈） | PASS |

## 复跑命令

```bash
cd /Users/kevin/bistro/xiai/feicui

# ① worker 单页运行态（图像栈）
SCRATCH=/tmp/neng SCRATCH=... ./venv/bin/python <本地质检脚本 wq_worker_page.py>

# ② E6 三 origin（入口必须 localhost）
JID=job-502016dd118a4bc6b7d73b5e0313d1b4
for h in 127.0.0.1:5196 127.0.0.1:5195; do curl -s -D- -o/dev/null http://$h/api/jobs/$JID/stamps/13/0/image; done
curl -s -D- -o/dev/null "http://localhost:5164/feicui/api/jobs/$JID/stamps/13/0/image"
# 404 三类
curl -s "http://127.0.0.1:5196/api/jobs/job-nonexistent/stamps/13/0/image"
curl -s "http://127.0.0.1:5196/api/jobs/$JID/stamps/999/0/image"

# ③ 删除清单哈希
shasum -a 256 ~/.hermes/profiles/zang/cache/scratch/webp_deleted_manifest.txt

# ④ retire dry-run（接口层）
cd server && ../server/.venv/bin/python -m app.retire_webp --report-dir /tmp/retire_now

# ⑤ AC 对账（图像栈）
./venv/bin/python <本地质检脚本 wq_reconcile.py / wq_ac.py>
```

## 结论汇总

- **PASS**：①（worker 单页：只 TIFF / 新 webp=0 / faces 不重建 / 命名 / 返回字段 / 更快）、②（E6 三 origin 真浏览器出图 + 404 三码未改）、③（4 本 7272/7272 在盘、无失影像、孤儿已清、样本+证据在、印章线未动）、⑤ 的 AC-97/98/99/100/101/103/104。
- **FAIL/不符**：④（dry-run 实报 **3 待删**，非 0 —— F2）；⑤ AC-102 与删除**冲突**（F4）。
- **HIGH 缺陷（旁路发现，需父级裁）**：**F1** 池写库未落 `col/row/img_path_tiff` ⇒ **新 job 的 E6 取图不可达**。
- **旧证据矛盾**：**F3** `ops/worker-naming/verify_worker_naming.py` 断言「三份并存」＝ 旧双份口径，与本轮「只出 TIFF」矛盾（且其 `git show HEAD:` 现在取到新版本，跑它必误判）。
