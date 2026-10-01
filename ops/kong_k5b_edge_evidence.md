# K5b · 「重新上传印面图」限定为只对 FACE（印面）呈现 —— 取证（Kong / 工程师）

时点戳：2026-09-20（CST，UTC+08:00）· 工作区 `/Users/kevin/bistro/xiai` · dev 5163（全程未停）

## 1. 改动（唯一一处）

文件：`src/views/SealDetailView.vue`（约 `:632-641`，`.face-block__admin-actions` 内）

```diff
-          <!-- 管理员专属（普通用户 / 游客 ⇒ 不渲染，DOM 零命中）：替换**本印面**的印面图。 -->
+          <!-- 管理员专属（普通用户 / 游客 ⇒ 不渲染，DOM 零命中）：替换**本印面**的印面图。
+               仅印面（FACE）可换；边款（EDGE）不呈现此按钮（数据层未拦 EDGE，见规范登记）。 -->
           <button
-            v-if="canReplaceFaceImage"
+            v-if="canReplaceFaceImage && !face.isEdge"
```

| | md5 |
|---|---|
| 改前 | `5653cebea33cdf2822d23278637d9d86` |
| 改后 | `f202894863cb257ac52195e1d145134e` |

**未改**任何其它字节：按钮文案、`data-admin-action`、`@click`、弹窗、`canReplaceFaceImage` 权限函数、
`utils/image.js`、`services/**`、`data/**`、`components/**`、`router/**`、`docs/**`、`web/**`、
`index.html`、`vite.config.js`、`ctrl/**` 一律未碰（另一并行单在改 `utils/image.js` 与 `services/photos.js`，本单零接触）。

## 2. 真浏览器证明（自建 headless Chrome，独立 profile `/tmp/xiai-kong5b-prof`，端口 9444，`--remote-allow-origins=*`）

脚本：`feicui/ops/kong_k5b_edge_selftest.py`（探针）· 原始输出：
`kong_k5b_edge_selftest_raw.json` / `.txt`（`all_pass=true`）。全程未停 5163、未用 9434、未占 5173/5174。

### ① 管理员 `16601061656`（role=admin，`/seal/XAI-0001`）

| 读数 | 值 |
|---|---|
| `face-block` 总数 | **3** |
| 其中 FACE（印面）块 | **2** |
| 其中 EDGE（边款）块 | **1** |
| `[data-admin-action="replace-face-image"]` 计数 | **2** |
| EDGE 块上该按钮命中 | **0** |
| FACE 块上该按钮命中 | 2 / 2 |

逐块映射（`data-face-id` 与块内印面 id 一致 ⇒ 按钮确属该印面块）：

```
#0 块 kind=印面  faceId=fc-0001-f1  hasReplaceBtn=true   btnFaceId=fc-0001-f1
#1 块 kind=印面  faceId=fc-0001-f2  hasReplaceBtn=true   btnFaceId=fc-0001-f2
#2 块 kind=边款  faceId=fc-0001-e1  hasReplaceBtn=false  btnFaceId=None
```

⇒ 按钮数 **== FACE 块数**（2），**< 修复前基线 3**。

其它含边款样本（管理员同账号逐页量）：

| 印章 | 块数 | FACE | EDGE | 按钮数 | EDGE 块按钮命中 |
|---|---|---|---|---|---|
| XAI-0001 | 3 | 2 | 1 | 2 | 0 |
| XAI-0004 | 2 | 1 | 1 | 1 | 0 |
| XAI-0005 | 2 | 1 | 1 | 1 | 0 |
| XAI-0007 | 2 | 1 | 1 | 1 | 0 |
| **合计** | 9 | **5** | 4 | **5** | **0** |

### ② 边款块 DOM 零命中（真实数据样本，非推断）

上表 4 枚样本各自都含真实 EDGE 印面行（`fc-0001-e1`/`fc-0004-e1`/`fc-0005-e1`/`fc-0007-e1`，
源自 `src/data/seed.js`），逐个 EDGE 块上 `querySelector('[data-admin-action="replace-face-image"]')` 均为 `null`
⇒ **无需退回 node 层渲染断言**，DOM 层已直接证到。

### ③ 修复前基线现场复现（同一探针，临时还原条件后原样写回）

`feicui/ops/kong_k5b_edge_baseline_probe.py` · 输出 `kong_k5b_edge_baseline_raw.json`：

```
baseline_repro: faceBlocks=3 faceCount=2 edgeCount=1
                replaceBtnCount=3  edgeBlocksWithReplaceBtn=1
                #2 块 kind=边款 faceId=fc-0001-e1 hasReplaceBtn=true   ← 缺陷现场
view_md5_with_fix   = f202894863cb257ac52195e1d145134e
view_md5_restored   = f202894863cb257ac52195e1d145134e  (restored_equals_fixed=true)
```

⇒ 缺陷为真、修复有效，且文件已原样还原（md5 复核一致）。

### ④ 普通用户 / 游客：全零

| 角色 | 探针确认 | `replace-face-image` 按钮 | `edit-fixed-attributes` 按钮 | body 文本「重新上传印面图」 |
|---|---|---|---|---|
| 普通用户 `13800000001` | `role=user, isAdmin=false` | **0** | 0 | **0** |
| 游客（未登录） | `loggedIn=false, isAdmin=false` | **0** | 0 | **0** |

如实说明：两态的 `documentElement.outerHTML` 里仍各含 **2 处**「重新上传印面图」字样——经上下文取样确认
**全部落在 Vite 注入的 `<style>` 注释里**（`/* 管理员按钮组（编辑固定属性 / 重新上传印面图）… */`、
`/* ------------------ 重新上传印面图：弹窗与取景框… */`），**不是任何 DOM 元素/按钮**；
按钮选择器与 `body.innerText` 均零命中，弹窗（`v-if="replaceFace"`）未渲染。

### ⑤ `npm run build`

`✓ built in 772ms`，产物含 `dist/assets/SealDetailView-CFhV3t3Q.js`（22.81 kB）——通过。

## 3. 数据层现状（如实登记，本单未改数据层）

对 EDGE 印面 `fc-0001-e1` 从页面内直调真实服务 `services/seals.js#replaceFaceImage('fc-0001-e1', {})`
（**空内容、只读语义、零写入**，`wroteAnything=false`、`face_image_id` 前后均为 `null`）：

```json
{"edgeFaceRowKind":"EDGE","result":{"ok":false,"reason":"EMPTY_CONTENT",
 "message":"印面图内容为空，请重新选择图片文件"},"wroteAnything":false}
```

⇒ 拒绝原因是**内容校验**（`EMPTY_CONTENT`），**不是按 `kind` 拒绝**：数据层**未拦 EDGE**。
这与 Zang 裁定一致（与「编辑固定属性」本就可改边款图片 ID 同口径），故**本单不额外禁止**；
但按裁定需登记缺口：**「边款图替换暂不提供 UI 入口」——仅 UI 层收紧，数据层无 kind 闸门**。

## 4. 自建 Chrome 收尾

主进程 PID **15192**（`--remote-debugging-port=9444 --user-data-dir=/tmp/xiai-kong5b-prof`），
按精确 PID 停止（未用 `pkill`/`killall`，未触及用户自己的 Chrome/9434）。

## 5. 未完成项

无（四条硬要求全部实测通过）。
