# APA_citation_finder — 排名与评分（scoring）

## 论文质量信号（Stage 7 前置富化）

| 信号 | 计算 | 说明 |
|---|---|---|
| tier_score | OpenAlex source citedness 归一（0.2–0.95）+ 会议白名单 0.8；未知 0.1 | 质量信号，**只是信号** |
| recency_score | ≤2y 1.0 / ≤5y 0.8 / ≤10y 0.5 / ≤20y 0.3 / 更老 0.1 | 与 profile 相关 |
| originality_score | 年代：≥20y 1.0 / ≥10y 0.8 / ≥5y 0.5 / 新 0.3 | FOUNDATIONAL 用 |
| authority_score | log10(citation_count+1)/4，封顶 1.0 | 引用数代理 |
| method_authority | authority×0.7 + tier×0.3 | METHOD 用 |

## 排名 Profile（rank_candidates.py）

| Profile | 权重 | 适用类型 |
|---|---|---|
| CURRENT_EMPIRICAL | support .40 · quality .25 · recency .25 · diversity .10 | EMPIRICAL / STATISTICAL / CONTEXTUAL / CURRENT_STATE |
| FOUNDATIONAL | support .40 · originality .35 · authority .20 · recency .05 | THEORETICAL / HISTORICAL |
| METHOD | support .40 · method_authority .35 · relevance .20 · recency .05 | METHOD |
| DEFINITION | support .50 · originality .30 · authority .20 | DEFINITION |

- **support 永远压过声望**：期刊层级不可弥补支撑不足（排名权重里 support 最高，且阈值闸门在前）。
- diversity（同首作者/同期刊）是软 tiebreak（0.6/0.7 系数），绝不牺牲 support。
- recency 权重由 profile 决定：FOUNDATIONAL 重原创、轻新近。

## 数量控制（禁止引用倾倒）

- 默认每 claim **1** 篇（精挑）。
- 重大/有争议论断：1–2 篇。
- 系统性综述/现状总述（CURRENT_STATE + REQUIRED）：最多 3 篇。
- 可选参数覆盖：--per-claim N。

## 支撑硬阈值（Stage 6 出口）

- 默认 0.60（PARTIAL 以上才可引用）。
- High Rigor 0.75。
- METADATA_ONLY 证据封顶 0.74（除非论断本身是元数据断言）。
- 未过阈值 → 该论文进 rejected 列表并附 reason；不引用。

## 与旧技能对比
- scipilot-cite-skill：无支撑评分，仅 tier/recency 排序 → **升级**为 support 主导。
- citation-finder：composite = tier .3 + support .3 + recency .4 → 反了：支持度 40% 上限之下被 recency 压过。APA_citation_finder 修正为 support 权重 0.40+ 且设硬闸门。
