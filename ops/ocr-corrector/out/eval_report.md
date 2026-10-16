# 248 枚池 · 纠错层评估（描述性读数）

> ★ 无真值 ⇒ 本报告**不含任何准确率 / 准确率提升**读数；`labeling/labels.csv` 的 text_correct 为空，量化准确率的解锁条件见 README。

- 字表：`webui/data/guxi_variant_map.json` v0.2.0-draft（条目 55，verified 1）
- 模式：`suggest`；语料域内字池（`stamps.text` 出现 ≥3 次）= 493 字

## 触发率（**不是准确率**）
- 样本：496（248 枚 × 2 配置；空输出 294）
- 命中任一规则（候选即可）的样本：72 = **14.5%**
- 其中命中 `verified=true` 规则：0；仅命中未验证候选：72
- 含「域外字」（该字不在 `stamps.text` 释文用字域）的样本：78 = **15.7%**
- 本次自动改写处数：0

## 映射命中分布（Top 15）
| from | to | source | verified | count |
|---|---|---|---|---|
| 團 | 图 | cross_engine | False | 8 |
| 团 | 图 | cross_engine | False | 5 |
| 圈 | 图 | cross_engine | False | 3 |
| 街 | 衛 | font_glyph_shape | False | 3 |
| 干 | 千 | cross_engine | False | 2 |
| 歌 | 欣 | font_glyph_shape | False | 2 |
| 衡 | 衛 | font_glyph_shape | False | 2 |
| 創 | 制 | font_glyph_shape | False | 2 |
| 摩 | 庫 | font_glyph_shape | False | 2 |
| 宏 | 宋 | font_glyph_shape | False | 2 |
| 做 | 侯 | font_glyph_shape | False | 2 |
| 鲜 | 鮮 | font_glyph_shape | False | 2 |
| 牌 | 將 | font_glyph_shape | False | 2 |
| 社 | 杜 | font_glyph_shape | False | 1 |
| 业 | 此 | font_glyph_shape | False | 1 |

## 域外字（OCR 报出、但不在释文用字域）Top 15

| char | count |
|---|---|
| 團 | 8 |
| 团 | 5 |
| 圈 | 3 |
| 街 | 3 |
| 干 | 2 |
| 区 | 2 |
| 歌 | 2 |
| 衡 | 2 |
| 創 | 2 |
| 摩 | 2 |
| 宏 | 2 |
| 做 | 2 |
| 鲜 | 2 |
| 牌 | 2 |
| 社 | 1 |

## 跨引擎混淆对（Rapid vs Paddle，逐位对齐；Top 15）

| engine A | char | engine B | char | count |
|---|---|---|---|---|
| rapid:rec_only | 团 | paddle:A | 图 | 4 |
| rapid:rec_only | 國 | paddle:A | 酒 | 2 |
| rapid:rec_only | 國 | paddle:C | 0 | 2 |
| rapid:rec_only | 國 | paddle:A | F | 1 |
| rapid:rec_only | 國 | paddle:C | 8 | 1 |
| rapid:pipeline | 同 | paddle:B | 司 | 1 |
| rapid:pipeline | 号 | paddle:B | 曰 | 1 |
| rapid:rec_only | 0 | paddle:B | 年 | 1 |
| rapid:pipeline | 图 | paddle:A | 面 | 1 |
| rapid:pipeline | 图 | paddle:B | 园 | 1 |
| rapid:pipeline | 图 | paddle:C | 园 | 1 |
| rapid:rec_only | 园 | paddle:A | 面 | 1 |
| rapid:pipeline | 出 | paddle:B | 士 | 1 |
| rapid:rec_only | 图 | paddle:B | 容 | 1 |
| rapid:rec_only | 鑫 | paddle:A | 部 | 1 |

## 已知真值样本冒烟（文本级）
- 输入（实测 OCR 输出）：`左軍丞錄`
- `auto` 输出：`左軍丞鈢`（期望 `左軍丞鈢`，达标 = True）
- `suggest` 模式未改写（n_applied=0）

## 种子标定（唯一有真值的字对在字形代理里的位次）
- 字对 `錄→鈢`；glyph_sim = 0.5128（字体 Heiti TC Light）
- 语料池里字形最像 `錄` 的是 `禄`（0.4134）
- 真值字是否在语料池：False（corpus count = 0）
- 解读：字形代理把**真值字**排在语料池全部候选之前（sim 高于池内最高者） ⇒ 排序启发式站得住；但**真值字本身不在语料池里** ⇒ 候选生成本质上不可能提出它 —— 瓶颈是**语料覆盖**，不是排序。
