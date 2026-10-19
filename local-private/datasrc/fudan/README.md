# datasrc/fudan/ —— 复旦印藏（yin.fudan.edu.cn）数据源工作面

**源**＝复旦印藏 yin.fudan.edu.cn。接入已实现于 `server/app/`，本目录登记其口径要点
（下述均已在仓内代码核对，行号为 2026-10-19 时点）：

- **三个 base**（`server/app/config.py` L124/L132/L142）：`person_source_base` /
  `items_source_base` / `seals_source_base`，默认 `https://yin.fudan.edu.cn/service_yinpu`；
  env 可覆盖：`FEICUI_PERSON_SOURCE_BASE` / `FEICUI_ITEMS_SOURCE_BASE` / `FEICUI_SEALS_SOURCE_BASE`。
- **影像**走 IIIF 代理：`<host>/iiif_proxy/api/char_proxy/<ref>` ⇒ **302** 跟跳转得 image/jpeg
  （`server/app/seals.py::iiif_host` / 取图 URL 构造；裁切图缓存落 `var/seal_images/<kind>/<seqid>.jpg`）。
- **只读纪律**：对源站只发 GET / POST 取数，**不上传任何数据**。
- **落库口径**：`source_kind='fudan_api'`（`server/app/seals.py` 建表列默认值；既有行不回填）。
- **展示名**：「复旦印藏（yin.fudan.edu.cn）」，persons / items / seals 三处
  （`server/app/persons.py` / `server/app/items.py` / `server/app/seals.py` 的 `"source": ...` 字段；
  relations 线另见 `server/app/relations.py` 的联立来源标注）。

## 未来 sealbank 接入的复用口径

若将来把真微印網（sealbank.net）接进 server：**复用同一 imports / 落库 / 展示名结构**；
source 字段标「真微印網（sealbank.net）」、`source_kind` 用独立值（不与 `fudan_api` 混写）；
新增 base 同样走 `config.py` ＋ `FEICUI_*_SOURCE_BASE` env 覆盖模式。
