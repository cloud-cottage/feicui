# 7 本对照表（收口后复算 · Kong）

数据源：`var/biblio_ingest.db`（Zang 逐书跑）＋ 收口后 `server/app/biblio.py` 复算。
**只给建议：不切目录键、不改名、不改路径。**

| 书（PDF 名） | 现目录键 | 识别 ISBN（直读） | 识别出版社 | 自证态 | 建议目录键 | 建议来源 | 需切键 | 旧（收口前）建议 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tmp.pdf | tmp.pdf | — | 印刷厂印刷浙江省新华书店 | unverified | tmp.pdf | pdf_name_unconfirmed | 否 | tmp.pdf |
| 古玺汇编 文物出版社 罗福颐  ok.pdf | 7501007985 | 7501007985 | 文物出版社 | ok | 7501007985 | ISBN | 否 | 7501007985 |
| 吴颐人篆刻作品展示.pdf | 吴颐人篆刻作品展示 | — | — | unverified | 吴颐人篆刻作品展示 | chinese_title | 否 | 吴颐人篆刻作品展示 |
| 福庵印缀 原版 高清.pdf | 福庵印缀 原版 高清 | — | 中國藝術家出版社 | unverified | 福庵印缀 原版 高清 | chinese_title | 否 | 2321978988 |
| 秦印类编 检索版.pdf | 秦印类编 检索版 | 9787550847224 | 西泠印社出版社 | ok | 9787550847224 | ISBN | 是 | 2478755084 |
| 秦汉印典 上海书画 金怀英  1997 ok.pdf | 7806350950 | 7806350950 | 上海节画出版社 | conflict | 7806350950 | ISBN | 否 | 7806350950 |
| 黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk).pdf | 黄牧甫印谱 | — | 印刷厂印刷浙江省新华书店 | unverified | 黄牧甫印谱 | chinese_title | 否 | 黄牧甫印谱_(西泠印社)_(z-library.sk,_1lib.sk,_z-lib.sk) |
