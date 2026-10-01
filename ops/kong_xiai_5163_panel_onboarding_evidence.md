# 玺爱（xiai）5163 登记入 ctrl 面板 services 表并启动 · 证据

- 角色：Kong（运维执行）
- 时间：2026-09-20 15:46–15:52（CST）
- 授权（Kevin）：① 把 5163 起起来；② 把玺爱登记进 ctrl 面板
- 唯一被改文件：`/Users/kevin/bistro/ctrl/index.js`（纯加法）
- 本证据文件：`/Users/kevin/bistro/xiai/feicui/ops/kong_xiai_5163_panel_onboarding_evidence.md`（本人新写，未动本目录其它文件）
- **未触碰**：`ctrl/PORTS.md`、`ctrl/public/**`、`xiai/src/**`、`xiai/dist/**`、`xiai/index.html`、`xiai/vite.config.js`、`xiai/package.json`、`xiai/docs/**`、`xiai/yinsuo/**`、`xiai/feicui/**`（本证据文件除外）
- **未使用** `pkill -f` / `killall` / 模糊杀；停服务只用面板自身 `/api/stop`；未占 5173/5174

---

## 1. `ctrl/index.js` 改前 / 改后

| 项 | 改前（pre-image） | 改后 |
| --- | --- | --- |
| md5 | `512d294533042ca054b45a5dd3883b44` | `d488f9cde7de65853b7f6de5a6e4010b` |
| size | `52654` bytes | `53562` bytes（+908） |
| 行数 | 1071 | 1086 |
| mtime | 2026-09-20 15:04:01 | 2026-09-20 15:47:01 |

改前副本：`/tmp/kong_xiai_ops/index.js.before`（md5 `512d294533042ca054b45a5dd3883b44`、52654 B，与改前主文件一致）

### diff（`diff -u /tmp/kong_xiai_ops/index.js.before /Users/kevin/bistro/ctrl/index.js`）

```diff
--- /tmp/kong_xiai_ops/index.js.before	2026-09-20 15:46:56
+++ index.js	2026-09-20 15:47:01
@@ -76,6 +76,21 @@
     // 前端 base = '/feicui/'，故直跳要带前缀（经 5164 的入口是 http://localhost:5164/feicui/）
     directUrl: 'http://localhost:5195/feicui/'
   },
+  // ── 玺爱 xiai H5（Vite dev，本工程专属端口 5163）────────────────────────────
+  // 依据：ctrl/PORTS.md §2「玺爱 H5（Vite dev）」行（v1.13 登记，端口 5163 / 启动命令
+  //   `npm run dev` / cwd `/Users/kevin/bistro/xiai` / 面板 group 拟 `xiai`）；该行明文要求
+  //   「运行时真源 ctrl/index.js 的 services 表由 Kong 在工程可跑后同步落地」（制度 a）。
+  // group 遵 PORTS.md 明文口径 `xiai`（与 shu / feicui-api / feicui-web 同组，不新开分组）。
+  // directUrl 按制度 (d) 写 127.0.0.1（非生产链路引用一律 127.0.0.1，避免 Node18 ::1 解析陷阱）。
+  xiai: {
+    name: '玺爱 xiai',
+    group: 'xiai',
+    port: 5163,
+    cmd: 'npm',
+    args: ['run', 'dev'],
+    cwd: '/Users/kevin/bistro/xiai',
+    directUrl: 'http://127.0.0.1:5163'
+  },
   'jinli-api': {
     name: 'jinli 后端',
     group: 'jinli',
```

### 「既有 12 条一字未改」的机器判据

```
$ diff /tmp/kong_xiai_ops/index.js.before index.js | grep '^<'
（无输出，rc=1）
```

⇒ **删除/修改行为 0 条**；diff 全为 `+` 行（纯插入）。新增条目位置＝`feicui-web` 之后、`jinli-api` 之前（与 xiai 族同组相邻，且不需要改任何既有行的标点）。

### 语法

```
$ node --check index.js
（无输出，rc=0）  ⇒ SYNTAX OK
```

### 命名依据（sid / group）

- **`sid = xiai`**：`PORTS.md` v1.13 表头与 §2 行均以「项目 `xiai`」称之，且 `xiai/package.json` 的 `name = xiai`；PORTS.md 未另立 sid 别名 ⇒ 取 `xiai`（与其它 sid 命名口径一致：sid 用项目名，如 `jiazu` / `jinli` / `cat`）。
- **`group = xiai`**：`PORTS.md` v1.13 §2 明文「**面板 group 拟 `xiai`**」⇒ **遵既有文档口径**，未自创。
- **`directUrl = 'http://127.0.0.1:5163'`**：按 `PORTS.md` 制度 (d)「非生产链路引用一律写 `127.0.0.1`」（既有条目里遗留的 `localhost` 字面属「照录例外」，不属本轮改动范围）。

---

## 2. 五条自测真实输出

### ① 面板 `/api/status` ⇒ **13/13 全 running**

```
count=13  running=13  => 13/13
sid          state      port   pid     group     cwd
jiazu-api    running    3100   88224   jiazu     /Users/kevin/bistro/jiazu
jiazu        running    5199   88225   jiazu     /Users/kevin/bistro/jiazu/frontend
shu          running    5164   88226   xiai      /Users/kevin/bistro/xiai/web
feicui-api   running    5196   88227   xiai      /Users/kevin/bistro/xiai/feicui/server
feicui-web   running    5195   88228   xiai      /Users/kevin/bistro/xiai/feicui/web
xiai         running    5163   91229   xiai      /Users/kevin/bistro/xiai
jinli-api    running    5778   88230   jinli     /Users/kevin/bistro/jinli/backend-ts
jinli        running    5777   88231   jinli     /Users/kevin/bistro/jinli/frontend
cat          running    5701   88232   cat       /Users/kevin/bistro/cat
aranya-api   running    5181   88233   aranya_go /Users/kevin/bistro/aranya_go
liwu-proxy   running    3020   88234   liwu      /Users/kevin/bistro/liwu
liwu-web     running    5175   88235   liwu      /Users/kevin/bistro/liwu
liwu-app     running    5176   88236   liwu      /Users/kevin/bistro/liwu
```

（`xiai` 的 pid 91229 是 `startAll` 后的值；本轮末做了一次 stop/start 往返验证，见 ⑤。）

`/api/self` 同时确认：面板 pid **87837**、node **v20.20.2**、跑的正是 size **53562** / mtime **15:47:01** 的新代码、`pids.json` sids 共 **13** 条（含 `xiai`）。

### ② `lsof -nP -iTCP:5163 -sTCP:LISTEN` ⇒ 有监听，且 cwd 钉到具体 PID

```
$ lsof -nP -iTCP:5163 -sTCP:LISTEN
COMMAND   PID  USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
node    91247 kevin   19u  IPv4 0xe10f3d905bf2988e      0t0  TCP 127.0.0.1:5163 (LISTEN)

$ lsof -a -p 91247 -d cwd
COMMAND   PID  USER   FD   TYPE DEVICE SIZE/OFF     NODE NAME
node    91247 kevin  cwd    DIR   1,18      640 60269443 /Users/kevin/bistro/xiai
```

`cwd = /Users/kevin/bistro/xiai` ⇒ **正是`services.xiai.cwd`**（cwd 填错会「已在运行」但其实是别的实例）。

监听者 `91247` 是面板登记 pid `91229` 的**孙进程**（`npm run dev` 包装 → `vite`），且同进程组：

```
$ ps -o pid,ppid,pgid,command -p 91247
  PID  PPID  PGID COMMAND
91247 91229 91229 node /Users/kevin/bistro/xiai/node_modules/.bin/vite
```

⇒ `pgid == 面板登记 pid`，证 `detached` 生效、面板可按进程组整组停（不会留 orphan）。

### ③ `curl -s -o /dev/null -D - http://127.0.0.1:5163/` ⇒ 真实首行

```
HTTP/1.1 200 OK
```

（**未用** `-w` 格式串；首行是 curl 打印的真实响应行。）

```
$ curl -s http://127.0.0.1:5163/ | grep -o '<title>[^<]*</title>'
<title>玺爱</title>
```

页面本体：

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <script type="module" src="/@vite/client"></script>

    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#f4efe4" />
    <meta name="description" content="玺爱 — 篆刻知识分享平台，印章、印面与边款的数字典藏。" />
    <title>玺爱</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

⇒ 应用＝**玺爱（xiai）Vite dev server**，非白屏、非报错页，HTTP 200 + 正确 title。

### ④ 旧站未受伤害

**4a. 印索 `http://localhost:5164` 的 14 条对外路由全 200**（路由清单取自 `xiai/qa-recheck/m1-p3b-neng/ac88_scan.py` 的 §2.2 口径）

```
/                      -> 200  bytes=578  OK
/pricing               -> 200  bytes=578  OK
/console               -> 200  bytes=448  OK
/console/login         -> 200  bytes=448  OK
/console/register      -> 200  bytes=448  OK
/console/overview      -> 200  bytes=448  OK
/console/keys          -> 200  bytes=448  OK
/console/usage         -> 200  bytes=448  OK
/console/billing       -> 200  bytes=448  OK
/docs                  -> 200  bytes=578  OK
/docs/quickstart       -> 200  bytes=578  OK
/org                   -> 200  bytes=578  OK
/demo                  -> 200  bytes=578  OK
/help                  -> 200  bytes=578  OK
RESULT: 14/14 = 200
```

**4b. 斐萃两条仍活**

```
$ curl -s -o /dev/null -D - http://localhost:5164/feicui/ | head -1
HTTP/1.1 200 OK
$ curl -s http://localhost:5164/feicui/ | grep -o '<title>[^<]*</title>'
<title>斐萃｜印谱解析任务台</title>
```

（标题实际为「**斐萃**｜印谱解析任务台」；任务书里写的是「璽谱解析任务台（或类似）」——**同一任务台，字面为「斐萃」**，HTTP 200 一致。）

```
$ curl -s http://127.0.0.1:5196/api/health
{"ok":true,"api_version":"1c-activate","db_path":"/Users/kevin/bistro/xiai/feicui/yinpu.db","db_exists":true,"prod_db":true,"root":"/Users/kevin/bistro/xiai/feicui","time":"2026-09-20T15:48:33+08:00","tables_present":{"stamps":true,"jobs":true,"job_pages":true},"journal_mode":"wal"}
```

⇒ `ok:true`；另 `http://127.0.0.1:5195/feicui/` ⇒ `HTTP/1.1 200 OK`。

### ⑤ 数据红线：`stamps` 内容指纹未变（**未用库文件 md5**）

```
journal_mode wal
cols=10  rows(id<=79)=79  total_rows_now=89  min/max id=(1, 89)
指纹口径: md5( 逐行 '|' 连接(10 列, NULL->''), 行间 '\n', 末尾 '\n' ) over id<=79 order by id
stamps id<=79 fingerprint = 8a21e57d5bd909fff282214640457c7f
expected                  = 8a21e57d5bd909fff282214640457c7f
REDLINE: PASS (未变)
```

- 复跑命令（只读，`PRAGMA query_only=1`）：
  ```python
  import sqlite3, hashlib
  p='/Users/kevin/bistro/xiai/feicui/yinpu.db'
  con=sqlite3.connect(p); con.execute('PRAGMA query_only=1'); cur=con.cursor()
  cols=['id','pdf_name','page','idx','text','img_path','x1','y1','x2','y2']
  rows=cur.execute(f"select {','.join(cols)} from stamps where id<=79 order by id").fetchall()
  payload="\n".join("|".join('' if v is None else str(v) for v in r) for r in rows)+"\n"
  print(hashlib.md5(payload.encode()).hexdigest())
  ```
- **口径说明**：「原 **79 行**」= `id <= 79` 的 79 行；库里现共 **89 行**，`id 80–89` 共 10 行走**另一条产品线**（feicui 阶段 1c/恢复 23 面）后续新增，不属本轮，也不在本红线口径内（`ops/1c/` 内的既有证据即命名 `..._idmax79...`，与此一致）。
- **踩坑留痕（供复跑者）**：本机该库处于 **WAL** 且 `-wal`/`-shm` 会被 checkpoint 回收；一旦 `-wal`/`-shm` 不在盘上，`sqlite3.connect('file:...?mode=ro', uri=True)` 会直接抛 **`sqlite3.OperationalError: unable to open database file`**（只读连接无法创建 shm）——**这不是「数据被改」**。此时改用**普通连接 + `PRAGMA query_only=1`**（从 15:11 起实测如此）。库文件 md5 口径本次仍得到漂移（制度 (f) 明令禁用，此处不引用其数值作判据）。

---

## 3. 面板可见性与可控性

- **可见**：`/api/status` 新增 `xiai` 键（state `running` / port `5163` / group `xiai` / directUrl `http://127.0.0.1:5163`）；`/api/self` 的 `pids.json` sids 13 条含 `xiai`。
- **可随面板启停（真跑往返）**：
  ```
  $ curl -X POST -d '{"sid":"xiai"}' .../api/stop
  {"ok":true,"state":"stopped","occupier":null,"msg":"已停止"}
  $ lsof -nP -iTCP:5163 -sTCP:LISTEN   → (无输出：端口已释放)
  $ /api/status .xiai → stopped  None  False

  $ curl -X POST -d '{"sid":"xiai"}' .../api/start
  {"sid":"xiai","ok":true,"state":"running","pid":91229,"msg":"已启动"}
  $ lsof -nP -iTCP:5163 -sTCP:LISTEN
  node    91247 ... TCP 127.0.0.1:5163 (LISTEN)
  $ /api/status .xiai → running 91229 True xiai http://127.0.0.1:5163
  ```
- **组级按钮可用**：`group: 'xiai'` 使该卡片落入既有 `xiai` 组，组内「启动该组 / 停止该组 / 重启该组」按 `sidsFor('xiai')` 生效（`POST /api/startAll|stopAll|restartAll` body `{group:'xiai'}`，`groupExists('xiai')` 为真）。

### 分组渲染（**修正任务书的一处预期**）

任务书预期「新建 group ⇒ 面板会多一个分组标题」。**实测不成立，因为既有 3 条已是 `group: 'xiai'`**：

```
$ python3 -c "分组统计"
jiazu      2 ['jiazu-api', 'jiazu']
xiai       4 ['shu', 'feicui-api', 'feicui-web', 'xiai']
jinli      2 ['jinli-api', 'jinli']
cat        1 ['cat']
aranya_go  1 ['aranya-api']
liwu       3 ['liwu-proxy', 'liwu-web', 'liwu-app']
```

- **分组数仍为 6**（jiazu / xiai / jinli / cat / aranya_go / liwu），**没有新增第 7 个分组标题**。
- `xiai` 组卡片 **3 → 4 张**（新增「玺爱 xiai」），卡片顺序＝services 表顺序：`shu → feicui-api → feicui-web → xiai`。
- **真正可见的变化有两个**（详见 §4 风险①）：
  1. 该组标题由「**印索 shu**」变为「**xiai**」（`public/index.html` 的 `GROUP_LABELS` 无 `xiai` 键 ⇒ 回退显示 `group` 原文；`GROUP_COLORS` 亦无 `xiai` ⇒ 用 `GROUP_FALLBACK` 色）；
  2. 组内多一张「玺爱 xiai」卡片。
- `applyRepoState('xiai')` 走 `!info` 分支（`projects` 表无 `xiai`）⇒「提交并推送该项目」按钮**置灰**、tooltip「该项目不是 git 仓库」，**无 JS 异常**（`ctrl/public/index.html` 从未被本轮修改）。

---

## 4. 未完成项 / 风险（如实登记）

1. **`shu` / `feicui-api` / `feicui-web` 的 `group` 从 `'shu'` 变为 `'xiai'` —— 不是本轮改的**。
   本轮改前盘面（15:04:01 的 `index.js`）这三条**已是 `group: 'xiai'`**，而 14:50 启动的面板进程仍加载着旧代码（组名显示 `shu`）。本轮 `pm2 restart` **激活了这处既有的待生效改动** ⇒ 组标题「印索 shu」→「xiai」。**如需保留旧标题，应由 `ctrl/public/index.html` 的 `GROUP_LABELS` 加 `xiai: '印索/斐萃'` 之类（该文件归其它角色，本轮未动）。**
2. `PORTS.md` 的 `xiai` 行状态仍写「**已登记 · 未落地（面板托管未落地）**」——**该文件归 Jing，本轮未动**，需 Jing 下轮按制度 (a) 升为「已登记 · 已托管」。
3. `PORTS.md` §2 的 `shu` / `feicui-api` / `feicui-web` 三行备注仍记 `group: 'shu'`，与盘面（`xiai`）不一致——同属归 Jing 的收口项。
4. **未做**：headless CDP 的 DOM 级 UI 断言（本轮只到 `/api/status` + 静态渲染代码审读；卡片可见性由「服务在 `/api/status` 中 + 分组渲染规则」推出，未截图）。
5. 前端 dev server 侧**无异常输出**（HTTP 200、title 正确），故未触发「如实贴 vite 报错日志尾」分支；`ctrl/logs/xiai.log` 为面板侧日志。

---

## 附：本轮命令与产物

- 改前副本：`/tmp/kong_xiai_ops/index.js.before`
- 原始输出：`/tmp/kong_xiai_ops/evidence_raw.txt`、`evidence_raw2.txt`
- 面板最终快照：`/tmp/kong_xiai_ops/status_final.json`
- `pm2 restart bistro-ctrl`（**未带 `--update-env`**）：面板 pid 54242 → **87837**，restart 计数 29 → 30
- 未重启/未改动其它任何 service 的配置；未动 `pm2` 其它进程
- orphan 巡检：`ps -eo pid,ppid,command | awk '$2==1 && /nodemon|ts-node|vite/'` ⇒ **0 条**
