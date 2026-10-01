# 23 个缺失印面影像复原取证（角色：Kong / 运维执行）

> 状态：**已完成** ✅　`stamps` 影像缺失 **23/79 → 0/79**
> 授权：Kevin 明确授权本单——从 `exports/fb_20260920_XGXHB_*/images/` 按正式库 `stamps.img_path`
> 期望的**目录名与文件名**（逐字，含空格与中文）拷回 23 个印面 webp。
> **未写数据库一行、未改/删 exports 任何文件、未动 output 下其它内容、未启停服务/未占端口/未执行任何 kill。**
> 逐条映射与 md5 清单：`ops/restore_23_faces_list.txt`

---

## 1. 命名映射规则（先读代码，不猜）

### 1.1 导出侧（`export.py`）—— 决定 `images/` 内的文件名

**代码行 `export.py:819`**（落包时的影像拷贝循环 815-821 行内）：

```python
dst_name = f"p{int(rec['sourcePageNo'] or 0):04d}_{int(rec['feicui']['stampIdx']):02d}_{asset['kind']}{src.suffix}"
```

```python
815  for rec in records:
816      asset = rec["assets"][0]
817      src = ROOT / asset["sourceImgPath"] if not os.path.isabs(asset["sourceImgPath"]) else Path(asset["sourceImgPath"])
818      if asset["fileExists"]:
819          dst_name = f"p{int(rec['sourcePageNo'] or 0):04d}_{int(rec['feicui']['stampIdx']):02d}_{asset['kind']}{src.suffix}"
820          dst = images_dir / dst_name
821          shutil.copyfile(src, dst)
```

**据以确认的关键代码行**：

| 行 | 内容 | 作用 |
|---|---|---|
| `export.py:409` | `img_rel = stamp_row["img_path"]` | 取 DB 的 `stamps.img_path` |
| `export.py:513` | `"sourceImgPath": img_rel` | 把它记进 asset |
| `export.py:817` | `src = ROOT / asset["sourceImgPath"]` | **源 = DB `img_path` 指向的文件** |
| `export.py:448` | `asset_kind = "FACE"` | kind 段恒为 `FACE` |
| `export.py:819` | `dst_name = f"p{page:04d}_{idx:02d}_{kind}{src.suffix}"` | **导出名** |
| `export.py:821` | `shutil.copyfile(src, dst)` | 纯字节拷贝，不改内容 |

⇒ 导出名 = **`p{page:04d}_{idx:02d}_FACE{suffix}`**（`page` 取自 `sourcePageNo`，`idx` 取自 `feicui.stampIdx`）。

### 1.2 DB 侧（`processor.py`）—— DB 期望的文件名

`stamps.img_path` 形态为 `output/{书名去 .pdf}/p{page}_{idx}.webp`：**十进制无补零、无 `_FACE` 段**。

### 1.3 确切映射规则（1:1、可逆、无歧义）

| | 形态 |
|---|---|
| **DB 期望（目标）** | `output/古玺汇编 文物出版社 罗福颐  ok/p{page}_{idx}.webp` |
| **exports 源** | `exports/fb_20260920_XGXHB_04/images/p{page:04d}_{idx:02d}_FACE.webp` |
| **规则** | 由 DB 行的 `(page, idx)` **直接计算**源名（不依赖 exports 内排序/序号）：`p{page:04d}_{idx:02d}_FACE.webp`；目标 = `stamps.img_path` **逐字** |

**独立第二证据（非我推导）**：批次包自带的 `exports/fb_20260920_XGXHB_04/draft.jsonl` 每条记录里
同时存了 `assets[0].sourceImgPath`（= DB `img_path`）与 `assets[0].imgPath`（= 包内路径），
23 条两两对应，与上表规则**逐条一致**（例：`output/.../p24_0.webp` ←→ `exports/.../images/p0024_00_FACE.webp`）。

---

## 2. 目标清单（DB 只读取出）

`sqlite3` 以 `mode=ro` 打开，`SELECT id,pdf_name,page,idx,img_path FROM stamps WHERE pdf_name LIKE '古玺汇编 文物出版社 罗福颐%'`
⇒ **23 条**，全部指向唯一目录：

```
output/古玺汇编 文物出版社 罗福颐  ok        (repr: 'output/古玺汇编 文物出版社 罗福颐  ok'，注意“罗福颐”与“ok”之间是两个空格)
```

页面分布：p24 → idx 0-5（6 个）、p25 → idx 0-6（7 个）、p26 → idx 0-9（10 个）= 23。

**基线（拷前）**：`stamps` 全库逐条 `os.path.exists` ⇒ **缺失 23/79**（恰为这 23 条）。

## 3. 源批次选择与校验

`exports/` 下 4 个批次 `fb_20260920_XGXHB_01..04` 的 `images/` 各含同名 23 个文件。

* **逐名跨批次 md5 比对：4 个批次 23 个文件全部字节相同（differing = 0）**。
* **选用 `_04`（最新，10:08 生成）**，理由：内容与其余批次完全一致，取最新已验收产物，时间序最靠后。
* 逐个校验：**23/23 文件存在、非空、magic = `RIFF....WEBP`**（`h[:4]==b'RIFF' and h[8:12]==b'WEBP'`），**0 个不通过**。

## 4. 拷贝

* 目标目录按 DB `os.path.dirname(img_path)` **逐字（字节级）** 拼绝对路径，`os.path.isdir` 不存在 ⇒ `os.makedirs` 新建（父目录 `output/` 已存在）。
* 源→目标用 **`cp -p`**（`subprocess.run(['cp','-p',src,dst])`）逐个拷贝 —— 只读源，不移动/不改/不删 exports。
* 结果：**成功 23，失败 0，未找到 0**（不存在"缺源"项，故无任何替代/冒充）。
* `cp -p` 时间戳保留已核：源 `p0024_00_FACE.webp` mtime `2026-09-20T10:08:36` = 目标 `p24_0.webp` mtime `2026-09-20T10:08:36`。

## 5. 映射表与 md5（23 条，源 → 目标）

完整机读清单见 `ops/restore_23_faces_list.txt`（列：`stamp_id | page | idx | source(rel) | target(=img_path) | size | md5 | webp`）。

| id | page | idx | 源（exports/fb_20260920_XGXHB_04/images/） | 目标（= stamps.img_path） | size | md5 |
|---|---|---|---|---|---|---|
| 43 | 24 | 0 | p0024_00_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p24_0.webp | 82496 | 118700b82ac965054e3b035a5d8ccbcd |
| 44 | 24 | 1 | p0024_01_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p24_1.webp | 69612 | 59902df8c05b5e95d72ab95a9e3484a6 |
| 45 | 24 | 2 | p0024_02_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p24_2.webp | 45292 | 95c99fdcdb5fd974285a8abe6e69d4d9 |
| 46 | 24 | 3 | p0024_03_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p24_3.webp | 115794 | a8d001e7fb400611f9975b7fcfb6f493 |
| 47 | 24 | 4 | p0024_04_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p24_4.webp | 69474 | 611a110bb17b977922bc010efe5d78f2 |
| 48 | 24 | 5 | p0024_05_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p24_5.webp | 65980 | 3ee36a644771be0cc9b4c237ccadb6dc |
| 49 | 25 | 0 | p0025_00_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p25_0.webp | 59292 | 9fbc5fa010c47fec4c75d1db2a604b52 |
| 50 | 25 | 1 | p0025_01_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p25_1.webp | 72138 | 3bf04a0ef2d4e45075a66d586dcfd97c |
| 51 | 25 | 2 | p0025_02_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p25_2.webp | 57628 | 8a838e2a36e4709a77027502b8f3c521 |
| 52 | 25 | 3 | p0025_03_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p25_3.webp | 87826 | 2c49de73e67d03013587bb7a869088ec |
| 53 | 25 | 4 | p0025_04_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p25_4.webp | 66868 | 58c83c04429b19ae01db23b003909b93 |
| 54 | 25 | 5 | p0025_05_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p25_5.webp | 39402 | d7fbde55b173e95d5412c116c3de01c3 |
| 55 | 25 | 6 | p0025_06_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p25_6.webp | 39216 | fa837f07c6bbda6869b2f65af811dd15 |
| 56 | 26 | 0 | p0026_00_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p26_0.webp | 73670 | 0bc8994ea395a9a028c381407e5f686d |
| 57 | 26 | 1 | p0026_01_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p26_1.webp | 81860 | fc812b8f5cf83d4e4f347cc6647313a7 |
| 58 | 26 | 2 | p0026_02_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p26_2.webp | 67954 | 3f153aec3f5e66764e70ddd67a3970ef |
| 59 | 26 | 3 | p0026_03_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p26_3.webp | 79610 | 15103c0b25a19a7c6addc186f00c4757 |
| 60 | 26 | 4 | p0026_04_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p26_4.webp | 64728 | d241335cbb17291d3eb7e64091692b90 |
| 61 | 26 | 5 | p0026_05_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p26_5.webp | 60952 | bc126b4f9f282d192419b7fab4212273 |
| 62 | 26 | 6 | p0026_06_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p26_6.webp | 64568 | 9ec090eeee33594b277865f329525de8 |
| 63 | 26 | 7 | p0026_07_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p26_7.webp | 68084 | 01ced5fbe46c963ab0472024cb617ecb |
| 64 | 26 | 8 | p0026_08_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p26_8.webp | 83878 | b45230a590b263d8721e5a719fa24c3c |
| 65 | 26 | 9 | p0026_09_FACE.webp | output/古玺汇编 文物出版社 罗福颐  ok/p26_9.webp | 67894 | c237eebce3fb43e2cf4c4d49f6dcf0e8 |

**拷后逐条校验（23 条）**：全部 `os.path.exists` ✅、大小 > 0 ✅、magic `RIFF/WEBP` ✅、
**目标 md5 == 源 md5** ✅（0 条不一致）。总字节 1 584 216。

## 6. 拷后全库缺失检查

```
POST missing = 0 / 79
missing by book: {}
```

**由 23/79 归零到 0/79** ✅（同一次只读遍历 `stamps` 全部 79 行逐条 `exists + size>0`）。

## 7. 未污染确认

| 项 | 期望 | 实测 |
|---|---|---|
| `stamps` 列数 | 10 | **10** ✅ |
| `stamps` 行数 | 79 | **79** ✅ |
| 指纹 A raw md5 | `8a21e57d5bd909fff282214640457c7f` | **一致** ✅ |
| 指纹 B canon md5 | `d7abe995bff62761c27052dfc2bdf7bb` | **一致** ✅ |
| 指纹 C free md5 | `22bdc0a794382b6e6dab7855aaee456f` | **一致** ✅ |
| A/B/C sha256 | 见 `prod_migrate_evidence.md` §2.3 | **全部一致** ✅ |
| 逐列非空 | id/pdf_name/page/idx/img_path/x1/y1/x2/y2=79，text=2 | **一致** ✅ |
| `stamps` 是否被写 | — | **一行未改写**（只 `mode=ro` 打开；三口径指纹与迁移取证逐字相同）✅ |
| `exports/**` | 只读 | 197 个文件；**10:30 后改动数 = 0** ✅ |
| `output/faces/TMP/` | 136，不动 | **136** ✅ |
| `output/pairs/` | 30，不动 | **30** ✅ |
| `output/古玺汇编_文物出版社/`（另一代产物） | 23，不动 | **23** ✅ |
| `output/秦汉印典 上海书画 金怀英  1997 ok/` | 26，不动 | **26** ✅ |
| 服务/端口/进程 | 不启停、不 kill | **未启动/未停止任何服务、未占任何端口、未执行 pkill/killall/kill** ✅（注：`5195`/`5196` 上确有监听，但均为 **13:16 就已在跑**的既有进程——`python3.1` PID 35232（`app.main`，13:16:16 启动）、`node` PID 35350（vite，13:16:17 启动）；本单全程未触碰、未重启、未 kill，我开工时间为 14:01 之后） |

```text
output/ (拷后)
  FILE .DS_Store                                 6148        (原有)
  DIR  faces            -> TMP 136 个                          (未动)
  DIR  pairs            -> 30 个                               (未动)
  DIR  古玺汇编 文物出版社 罗福颐  ok  -> 23 个                (本单新建：DB 期望目录)
  DIR  古玺汇编_文物出版社             -> 23 个                 (另一代产物，未动)
  DIR  秦汉印典 上海书画 金怀英  1997 ok -> 26 个               (未动)
```

## 8. 未找到项 / 异常

* **未找到的源：无（0 项）**。23 个 `(page, idx)` 在 `_04` 批次中全部存在，无需任何替代或猜测。
* **异常：无**。无权限问题、无拷贝失败、无 md5 不一致、无 webp 校验失败。

## 9. 本次新增/改动文件（仅这些）

| 文件 | 性质 |
|---|---|
| `ops/restore_23_faces_evidence.md` | 新建（本文件） |
| `ops/restore_23_faces_list.txt` | 新建（23 条源→目标+md5 清单） |
| `output/古玺汇编 文物出版社 罗福颐  ok/` + 内 23 个 `.webp` | **新建目录 + 拷入 23 个影像**（本单唯一复原目标） |

未新增任何脚本文件；探索期临时脚本落在 `/tmp`（`/tmp/restore23.json`），未写入仓库。
`yinpu.db`：**零字节写入**（全程 `mode=ro`）。注意 WAL 下库文件 md5 会漂，故按 §2.3 三口径内容指纹验证，已逐字一致。
