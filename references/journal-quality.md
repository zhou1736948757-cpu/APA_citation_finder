# APA_citation_finder — 期刊质量（journal-quality）

## tier_score（utils/journal.py）

| 情形 | 分数 |
|---|---|
| 会议白名单（data/priority_journals.csv 内） | 0.8 |
| OpenAlex source 有 citedness（期刊被引百分位） | 0.2–0.95 归一 |
| 未知期刊/无数据 | 0.1 |

- 黑名单期刊（data/blacklist_journals.csv）：**检索阶段即过滤**（filter_blacklisted）。
- 中科院分区/JCR 数据仅当用户提供或 OpenAlex 可查时作为补充信号。

## 质量信号的使用边界
- tier_score 只是 **quality 信号**，进入排名 profile 的 quality/method_authority 权重；
- **support 永远压过声望**（scoring.md）：高分期刊论文支撑不足照样被阈值挡下；
- 不可用 tier 替换或补足支撑度（无"声望折扣"）。

## 预印本策略（默认）
- 默认**首选同行评审**（journal / conference 记录优先）；
- preprint（arXiv 等）仅在以下情况接受：
  ① 用户明确允许；② 该领域最新进展无同行评审版；③ 评审记录中注明 preprint 状态。
- 记录中保留 `oa_status` / 来源标注，审计可见。
