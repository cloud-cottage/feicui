# local-private/ —— feicui-local-private（创始人私有版）数据源工作面

**形态**：仅 localhost 服务 —— `web/`(:5195) ＋ `server/`(:5196) 本地跑，原生浏览器访问
（页面 title / 顶栏 brand 按 hostname 运行时判断带「 · 本地服务私有版」后缀，见 spec §0.5.4）。

**不复制共用底座**：`web/` ＋ `server/` 是三版本（feicui-web / feicui-local-dist /
feicui-local-private）共用的同一套代码，本目录**不放**其副本。本目录只放数据源与专属配置：

| 路径 | 内容 |
| --- | --- |
| `datasrc/sealbank/` | 真微印網（sealbank.net）数据源工作面（README 取证 ＋ `cookies.txt` ＋ `out/` 抓取产出） |
| `datasrc/fudan/` | 复旦印藏（yin.fudan.edu.cn）数据源要点 |

`datasrc/` 各源**同级独立**，利于将来单一数据源被多版本复用（server 接入时按源名各取所需）。

## 纪律

- `datasrc/*/cookies.txt`（登录态）**绝不入库** —— `.gitignore` 规则接住（`git check-ignore` 实证）。
- `datasrc/*/out/` 抓取产出**不入库**（大件；NDJSON 小件是否入库后续再议）。
- 对外源一律**只读取数**：礼貌间隔、注明来源、不镜像大图、不公开分发（各源 README 内详列）。
