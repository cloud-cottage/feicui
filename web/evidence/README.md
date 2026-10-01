# feicui/web 阶段 1a 自测证据

全部命令在 `/Users/kevin/bistro/shu/feicui/web` 下执行；**证据文件均为命令原始输出**，未改写。

| 文件 | 内容 |
| --- | --- |
| `build.log` | `npm run build` 完整输出（vite 6.4.3，`✓ built in 554ms`，exit 0） |
| `final-selfcheck.txt` | **交付态**（无 `FEICUI_API_TARGET` 覆盖）：`lsof -nP -iTCP:5195 -sTCP:LISTEN`（**`127.0.0.1:5195` IPv4**）、`curl -s -o /dev/null -D - http://127.0.0.1:5195/` **首行 `HTTP/1.1 200 OK`**、`localhost:5195` 对照同为首行 200、后端探测、`/api/jobs` 代理 503、5164/5173/5174/5196/5555 现况、进程溯源（`ps -o pid,ppid,lstart,command`） |
| `curl-firstline.txt` | 早期一次 5195 首行记录（含 `127.0.0.1` 与 `localhost` 两行） |
| `selfcheck.txt` | 首次自测（含端口纪律与绑定形态） |
| `dom-jobs.txt` / `dom-job-detail.txt` / `dom-job-results.txt` / `dom-job-missing.txt` | **后端未启动**（5196 无监听）时四页的 `document.body.innerText`：四页均含「**后端未启动 / 未连接**」+ 启动提示，`table tbody tr` 行数 **0**，无任何示例/估算数据 |
| `dom-summary.json` | 上列四页的 CDP 探针结构化结果（`hasDown` / `hasNotImpl` / `hasFixture` / `hasFakeData` / `rows`） |
| `dom-stub-jobs-409.txt` | 场景①：**E1 409 如实展示** —— 面板显示 `HTTP 409`、后端给出的既有 `job_id`（`stub-job-0007`）可点跳转、原始 body 折叠区原样保存；同页「job 列表（后端）」显示「后端尚未提供该接口 HTTP 404」 |
| `dom-stub-job-detail.txt` | 场景②：**E2 进度全部来自后端值** —— `done_pages / total_pages = 136 / 544`、进度条 `width: 25%`、cursor / counters / failed_pages 原表展示、S-1 标注在页内 |
| `dom-stub-job-results.txt` / `dom-stub-job-missing.txt` | 场景③：E3 / E5 返回 404 ⇒ 页面显示「**后端尚未提供该接口**」（非空白、非假数据） |
| `dom-stub-summary.json` | 上列 stub 场景探针结果（`{"job-detail":{"done":"136 / 544","barWidth":"25%",...}}`） |
| `dom-realbackend-404-e2.txt` | **真实观测**（2026-09-20 11:53:13）：并行开发的后端当时短暂监听 5196，对 `GET /api/jobs/demo-job-id` 回 **404** ⇒ 页面如实显示「后端尚未提供该接口（E2）」（非 stub 造数；随后 5196 又无监听，见 `final-selfcheck.txt`） |

## stub 说明（**非交付物**）

场景 ①②③ 使用一次性 stub `/tmp/feicui-stub.py`（`127.0.0.1:5271`，**不占 5196/5195/5164**），
以 `FEICUI_API_TARGET=http://127.0.0.1:5271 npm run dev` 启动 —— 该环境变量**默认不设置**，
交付态目标恒为登记口径 `http://127.0.0.1:5196`。stub 与 CDP 探针脚本均位于 `/tmp`，**未入工程**。
stub 只做「返回后端形状的响应 / 返回 404」两件事，**不含任何被前端当作真值的库存数据**；
页面上显示的每个数值都来自响应体本身。

## 复现

```bash
cd /Users/kevin/bistro/shu/feicui/web
npm install && npm run build
npm run dev                                        # → http://127.0.0.1:5195/
curl -s -o /dev/null -D - http://127.0.0.1:5195/ | head -1
curl -s http://127.0.0.1:5195/__feicui/backend-probe    # {"reachable":false,...} 当 5196 未启动
```
