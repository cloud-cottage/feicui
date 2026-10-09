# 证据⑨ 交付缝修复（批 1 · 印人采集）：字 / 号 / 别名改「真 JSON 数组」＋ 两条如实登记

时点＝2026-10-10（CST）｜范围＝`feicui` 仓（main）｜**不联网、不重采、不碰 `yinpu.db` / `xiai/**` / `ctrl/**`**

## 1. 缺陷（Zang 独立复算裁定的真缺陷）

`courtesy_names` / `courtesy_names_chs` / `art_names` / `art_names_chs` / `alias_names` /
`alias_names_chs` 六个字段在**批次包 `persons.jsonl`** 里是 **JSON 字符串**（`type=str`，值形如
`"[{\"value\":\"容光\",…}]"`），而**交付缝 §3.15.10** 与 **xiai §3.54.3**（`courtesy_names[]` /
`art_names[]` / `alias_names[]` ＝ `string[]`）要求的是**数组**。批 2 消费方按数组取用 ⇒ **真互操作缺陷**。

- 根因：`write_package` 直接 `json.dumps({k: 库值})`，而库内六字段是「规范 JSON 数组**文本**」，
  被再次 `dumps` ⇒ JSONL 里成了字符串。
- 修复前实测（本次留存的旧形态）：
  `{courtesy_names: 'str', courtesy_names_chs: 'str', art_names: 'str', art_names_chs: 'str', alias_names: 'str', alias_names_chs: 'str'}`

## 2. 修法（最小改动，不重采）

- **库内**：六字段在 `persons` 表仍以**规范 JSON 数组文本**存储（SQLite 无原生数组类型；空＝`'[]'`，**非** `''`）。
  采集/归一化路径（`normalize_person` → `_json_list`）**未改**，无需重采即可重建。
- **读取缝**：新增 `decode_name_list(value)`（`server/app/persons.py`），
  **幂等**（已是 `list` 原样返回；`None`/空串/坏 JSON ⇒ `[]`，绝不回退字符串）。所有对外读取缝一律解码为真 `list`：
  - 批次包：`write_package` 对 `persons` 行逐字段解码 ⇒ `persons.jsonl` 输出真数组；
  - API：`get_person`（`GET /api/persons/{grbsm}`）对六字段解码 ⇒ 回真数组。
- **前端兼容**：`web/src/pages/PersonsPage.vue::parseJsonList` 由「只吃 JSON 字符串」改为
  「数组与 JSON 字符串**两形态都吃**」（回退兼容历史形态）。
- **coverage**：`_coverage` 的 `alias_names` 判据由「非 `'[]'` 字符串」改为 `bool(...)`（真数组下 `[]` 即空）。

## 3. 重建后实测（行数与字段类型）

| 项 | 读数 |
| --- | --- |
| `persons.jsonl` 行数 | **570** |
| `relations.jsonl` 行数 | **1650** |
| 六字段类型（570×6 全量） | **全部 `list`**（0 个 `str`） |
| 空值形态 | `[]`（空串形态 0 个）：alias 123 / art 121 / courtesy 82（各含 `_chs` 同数） |
| 数组元素总数 | 7715（`extraction` 全 `rule-based`；`from` ∈ {`personBm`,`personBmChs`}；`value` 无空） |

真实样例（`exports/person_20261010_01/persons.jsonl` 首行节选；`source_person_id=900289963`）：

```json
{
  "source_person_id": "900289963",
  "name_full": "郭照",
  "name_full_chs": null,
  "courtesy_names": [{"value": "容光", "kind": "字", "extraction": "rule-based", "from": "personBm"}, {"value": "子青", "kind": "字", "extraction": "rule-based", "from": "personBm"}, {"value": "鳴之", "kind": "字", "extraction": "rule-based", "from": "personBm"}, {"value": "飴之", "kind": "字", "extraction": "rule-based", "from": "personBm"}],
  "alias_names": [{"value": "郭容光", "kind": "名", "extraction": "rule-based", "from": "personBm"}, {"value": "隱吾草堂", "kind": "齋名", "extraction": "rule-based", "from": "personBm"}]
}
```

## 4. 自检改成能判负旧形态（证据⑧）

`ops/person-ingest/verify_delivery_seam.py` 新增：

- `AC22.name_lists_are_arrays`：六字段须 `isinstance(v, list)`；元素须 `isinstance(dict)` 且
  `element['extraction']=='rule-based'` 且 `element['value']` 非空；**任一不满足 ⇒ FAIL**。
- `AC22.regression_selftest_detects_old_string_form`：同判据对**旧形态**（六字段＝JSON 字符串 / `''` / `'[]'` / `null`）
  跑 ⇒ 须判 **FAIL**。

**旧形态 FAIL 样例（对照）**——用修复前的「JSON 字符串」形态重建一份 `persons.jsonl` 再跑同一自检：

```
OK= False
[FAIL] AC22.name_lists_are_arrays   violation_count= 3420        # 570 行 × 6 字段
violations[0] = {"kind":"not_a_list","id":"900289963","field":"courtesy_names","got_type":"str",
                 "sample":"[{\"value\": \"容光\", \"kind\": \"字\", \"extraction\": \"rule-based\", \"from\": \"personBm\"}, {"}
```

**新形态**（当前批次包）跑同一自检：`AC22.name_lists_are_arrays = PASS（violation_count=0）`。

## 5. 两条如实登记（已写入 `manifest.json` 与 `report.json`）

1. **`name_full_chs` 恒空** ⇒ `name_full_chs_note`：**源侧根本没有简体姓名字段**——实测 `raw_json` 的 `*Chs` 键
   恰 4 个（`personBmChs` / `personJjChs` / `personJgChs` / `personZzChs`，570/570 行），**无**姓名对应 `personGrsxmcChs`。
   ⇒ 该字段恒 `null` **属预期、非缺陷**；沿「不自行转繁简」纪律；**字段键保留、不删**。
2. **采集 run 与本次重放计数分离** ⇒ `run_provenance`：
   - `acquisition_run`（**本单之前已完成**）：`fetched_requests_cumulative=570` / `failed_count=0`；
     末片读数 `fetched_requests=178 / skipped_resume=392 / persons_ok=570 / relations_ok=539 / elapsed_s=301.615`
     （证据 `01_full_ingest.txt`）。
   - `this_package_write`（**本次幂等重放**）：`kind=idempotent_replay_no_network` / `fetched_requests=0` /
     `skipped_resume=570`；明文：**`0` 是重放读数，不得据此判「未采集」**。
     库内 `person_import_batches` 行（`fetched=0 / relations_ok=0 / elapsed_s≈1.5`）同理。

## 6. 幂等与红线复验

- **幂等（证据③b，`03b_rebuild_idempotency.txt`）**：同批次离线重建两次——
  `persons.jsonl` / `relations.jsonl` **逐字节相同**；`manifest.json` / `report.json` 仅生成时点键（`created_at`/`generated_at`）变，
  去该键后结构相同；库内 `persons=570 / person_relations=1650`、**内容指纹恒 `d520c07b…c427ca4`**（前后一致）。
- **红线（证据④，`04_scope_diff.txt`）＝IDENTICAL**：`yinpu.db` 的 `stamps`(89) / `jobs`(5) / `job_pages`(32)
  内容指纹逐字未变；`exports/fb_*` 12 目录 / 196 文件 sha256 全等。**用内容指纹、禁用库文件 md5**。

## 7. 修改 / 新增文件（本单）

| 文件 | 动作 |
| --- | --- |
| `server/app/persons.py` | 加 `NAME_LIST_FIELDS` / `decode_name_list`；`write_package` 解码六字段＋新增 `provenance` 形参＋登记两条；`get_person` 解码；`_coverage` 判据 |
| `web/src/pages/PersonsPage.vue` | `parseJsonList` 兼容真数组 |
| `ops/person-ingest/verify_delivery_seam.py` | 新增数组断言 ＋ 旧形态回归自证 |
| `ops/person-ingest/rebuild_delivery_seam.py` | **新增**：离线幂等重建脚本（不联网、不入库） |
| `exports/person_20261010_01/{persons.jsonl,relations.jsonl,manifest.json,report.json}` | 重写（gitignored 运行时产物） |
| `ops/person-ingest/08_delivery_seam.{json,txt}` | 刷新 |
| `ops/person-ingest/03b_rebuild_idempotency.txt` | **新增** 幂等证据 |
| `ops/person-ingest/04_scope_after.json` / `04_scope_diff.txt` | 刷新（红线复验） |
| `ops/person-ingest/05_routes.txt` / `06_build.txt` | 加注 / 刷新构建证据 |

## 8. 未完成 / 未验证项

- **联机 API 回包未复跑**：`GET /api/persons/{grbsm}` 的**真数组**形态需重启 `feicui-api` 才反映到联机端点；
  本单不 `pkill` / 不重启服务 ⇒ 联机端点回包（证据⑤）仍为修复前快照，已在文件头加注，待运维重启后复跑刷新。
- **未联网复核**：本单按约束不重采；`02_relations.txt`（关联锚点，需实时 `graph/person`）**未复跑**，沿用历史读数（关联数据未动）。
- **库内原始单元格仍为 TEXT 文本**：SQLite 无原生数组类型，`persons` 表六字段物理存储为规范 JSON 数组文本
  （`json.loads(单元格)` 即得 `list`）；「真数组」落在**所有读取缝**（批次包 / `get_person`）。
  若要求「裸 SQLite 直读即 `list`」需引入列转换器 / 表重建，**本单按最小改动与既有纪律未做**。
