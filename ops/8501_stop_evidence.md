# 8501 孤儿 Streamlit 进程停止 — 运维执行证据

**角色**：Kong（运维执行·短单）
**授权**：Kevin
**执行时间**：Sun Sep 20 2026, 10:57:50 CST（停）→ 10:57:51 CST（核实）
**目标进程**：PID 71267（PGID 71267，PPID 1，孤儿进程）
**主机**：macOS 15.7.4
**原始输出留档**：`ops/8501_stop_before_after.txt`（md5 `cc07f93f30af4bf0af7bb91c8f12cf58`）

---

## 1. 结论（TL;DR）

| 检查项 | 结果 |
|---|---|
| 8501 是否已彻底释放 | ✅ **是**（无 LISTEN，无任何 socket，nc 连接被拒） |
| 进程组 71267 是否已消失 | ✅ **是**（`kill -0 -- -71267` → No such process） |
| 是否仅停 71267（无邻接误伤） | ✅ **是**（27 个无关 node/vite 进程全数存活） |
| ctrl 面板 5555 是否仍在 | ✅ **是**（LISTEN + HTTP 200 + 2 条 ESTABLISHED） |
| 是否需要升级 SIGKILL | ❌ 不需要（SIGTERM 进程组 1 秒内生效） |
| `qa-baseline/` 是否被动过 | ❌ 未动（md5 前后一致） |
| 异常 | **无** |

**一句话**：**8501 已彻底释放**，PID 71267 及其进程组已完全消失，ctrl 面板与所有其它服务零误伤。

---

## 2. 停前取证（Sun Sep 20 10:57:46 CST 2026）

**进程身份**（`ps -p 71267 -o pid,ppid,pgid,lstart,command`）：

```
  PID  PPID  PGID STARTED                      COMMAND
71267     1 71267 Fri Sep 18 09:51:16 2026     .../Python -m streamlit run app.py --server.port 8501 --server.headless false
```

- PPID = 1 → **孤儿进程**（自愈不可能）
- PGID = 71267 = PID → **自己成独立进程组** → 适用进程组停止口径
- 启动于 Fri Sep 18 09:51:16 2026（已挂 >2 天）

**端口占用**（`lsof -nP -iTCP:8501 -sTCP:LISTEN`）：

```
COMMAND   PID  USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
Python  71267 kevin    6u  IPv6 0xe018df0d840788bc      0t0  TCP *:8501 (LISTEN)
```

**活跃连接**：`lsof -nP -iTCP:8501 | grep -c ESTABLISHED` → **0**
（无活跃会话，停机对用户零影响）
**端口可达性**：`nc -z 127.0.0.1 8501` → succeeded（exit=0），确认停前端口确实在服务。
**全机 streamlit 进程数**：`pgrep -fl streamlit` → 仅 71267 一条 → 它确实是孤例。
**ctrl 面板基线**：`lsof -nP -iTCP:5555 -sTCP:LISTEN` → node PID 93417 在听。

---

## 3. 停止动作（进程组口径）

**为什么用进程组**：PGID=71267 自己成组，`kill -TERM -- -PGID` 可一次性覆盖该组内全部进程，同时**完全规避 `pkill -f streamlit` 这类宽匹配误伤**（会打到 ctrl 面板及其它会话）。

```
$ /bin/kill -TERM -- -71267        # Sun Sep 20 10:57:50 CST 2026
kill TERM exit=0

$ # 轮询端口释放（1s 间隔，上限 5s）
t=1s: PGID gone AND 8501 released
released=yes
done at Sun Sep 20 10:57:51 CST 2026
```

**SIGTERM 进程组 1 秒内生效 → 未使用 SIGKILL。**

---

## 4. 停后核实（Sun Sep 20 10:57:51 CST 2026）

| 命令 | 输出 | 判定 |
|---|---|---|
| `ps -p 71267` | 空（exit=1，无此进程） | ✅ PASS |
| `/bin/kill -0 -- -71267` | `kill: -71267: No such process`（exit=1） | ✅ 进程组已消失 |
| `lsof -nP -iTCP:8501 -sTCP:LISTEN` | 无输出（exit=1） | ✅ 无监听 |
| `lsof -nP -iTCP:8501` | 无输出（exit=1） | ✅ 该端口**完全**无 socket |
| `lsof -nP -iTCP:8501 \| grep -c ESTABLISHED` | `0` | ✅ 无残留连接 |
| `nc -z 127.0.0.1 8501` | 失败（exit=1） | ✅ CLOSED |
| `pgrep -fl streamlit` | 无输出（exit=1） | ✅ 全机无 streamlit |

---

## 5. 邻接检查 / 防误伤

**ctrl 面板 5555**：

```
$ lsof -nP -iTCP:5555 -sTCP:LISTEN
node    93417 kevin   17u  IPv6 0x7e9da640fe9fee17      0t0  TCP *:5555 (LISTEN)

$ ps -p 93417 -o pid,ppid,pgid,lstart,command
93417 97415 93417 Sat Sep 19 20:56:40 2026   node /Users/kevin/bistro/ctrl/index.js
  → 启动时间仍为 Sep 19 20:56:40，未被重启

$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5555/
200                                    → 面板响应正常

$ lsof -nP -iTCP:5555 | grep -c ESTABLISHED
2                                      → 面板仍在服务活跃会话
```

**全机相关进程前后对比**（`ps -eo pid,ppid,pgid,command | grep -E "streamlit|vite|node" | grep -v grep`）：

停前 28 条（含 71267）→ 停后 27 条。**唯一消失的就是 PID 71267 那一行**。
其余 27 个进程（含 `bistro/ctrl/index.js`、`shu/web` vite、`jiazu` uni、`jinli`/`cat`/`liwu` vite、各 esbuild、Photoshop Generator node、agent-browser 等）PID/PPID/PGID **逐一比对完全一致**，无新增、无消失。

---

## 6. 硬约束合规声明

- ✅ 只停 PGID 71267；**全程未使用 `pkill` / `-f` 宽匹配**。
- ✅ **未启动/重启任何服务**；8501 未被重新拉起（本轮仅停）。
- ✅ 未触碰 5164。
- ✅ 未写 `yinpu.db` / `output/`（71267 未持有其句柄，停它无数据风险）。
- ✅ 未改 `shu/web/**`、`shu/docs/**`、`shu/mockups/**`、`shu/index.html`、`ctrl/**`（**含 PORTS.md**）。
- ✅ **未修改/删除 `feicui/qa-baseline/` 任何文件** — 前后 md5 比对：

  | 文件 | 停前 md5 | 停后 md5 | 一致 |
  |---|---|---|---|
  | `qa-baseline/8501_evidence.md` | `1146415d72a9bfec4dff903f7397e04c` | `1146415d72a9bfec4dff903f7397e04c` | ✅ |
  | `qa-baseline/baseline.json` | `b0b2f48a13d3ecb8678dbcc2445adb39` | `b0b2f48a13d3ecb8678dbcc2445adb39` | ✅ |
  | `qa-baseline/baseline_report.md` | `5df9b5872a67591f0ac20f68ee60981a` | `5df9b5872a67591f0ac20f68ee60981a` | ✅ |

- ✅ 全部写入仅限新建目录 `feicui/ops/`。

---

## 7. 交付物

| 文件 | md5 |
|---|---|
| `feicui/ops/8501_stop_evidence.md`（本文件） | 见下方执行回执 |
| `feicui/ops/8501_stop_before_after.txt` | `cc07f93f30af4bf0af7bb91c8f12cf58` |

**无异常。8501 已彻底释放，进程组 71267 已完全消失，ctrl 面板及全部邻接服务完好。**
