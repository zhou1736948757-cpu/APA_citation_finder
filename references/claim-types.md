# APA_citation_finder — 论断类型（claim-types）

`classify_claims.py` 按信号模式分类。类型决定排名 profile 与查询策略。

| 类型 | 含义 | 信号 | 排名 profile | 查询侧重 |
|---|---|---|---|---|
| **EMPIRICAL** | 经验实证断言 | 实验/研究/发现/数据 | CURRENT_EMPIRICAL | precise + broad |
| **THEORETICAL** | 理论命题/框架主张 | 理论/框架/提出/认为（非个人） | FOUNDATIONAL | authoritative + foundational |
| **DEFINITION** | 术语/概念定义 | 定义/指/即/是…的（定义性） | DEFINITION | canonical（原理论文） |
| **METHOD** | 方法/工具/流程声明 | 方法/算法/工具/流程/步骤 | METHOD | method + 应用场景 |
| **STATISTICAL** | 数字/比率/统计断言 | %、数字、比例、统计显著 | CURRENT_EMPIRICAL | precise（含数字） |
| **HISTORICAL** | 历史事实陈述 | 最早/首次/起源于/年代 | FOUNDATIONAL | 原始文献 + 综述 |
| **CONTEXTUAL** | 背景/语境铺垫 | 背景/近年来/传统上 | CURRENT_EMPIRICAL | broad |
| **NORMATIVE** | 应然/规范建议 | 应/应当/必须/建议 | CURRENT_EMPIRICAL | 权威指南/政策 |
| **CURRENT_STATE** | 现状/进展综述 | 目前/当前/最新/研究表明 | CURRENT_EMPIRICAL | recent + 综述 |

### 判定优先级
1. DEFINITION（含"定义/指"）
2. STATISTICAL（含明确数字/百分比）
3. METHOD（含方法类动词）
4. HISTORICAL（含时间锚点 + 首创类词）
5. NORMATIVE（含规范助动词）
6. THEORETICAL（含理论/框架名词）
7. CURRENT_STATE（含现状/最新）
8. EMPIRICAL（默认经验实证）

> 中文信号词与英文信号词均支持；判断不确定时按 EMPIRICAL 兜底并注明。
