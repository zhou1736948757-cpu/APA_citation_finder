# APA_citation_finder — 论文真实性验证（verification）

> **真实论文 ≠ 有效引用**（IRON RULE 1）。本关只回答「这篇论文真实存在且元数据一致」，
> 支撑度由 Stage 6 单独判定。**验证是闸门，不是排名权重。**

## 判定标准（verify_papers.py）

| 判定 | 条件 | 处置 |
|---|---|---|
| **VERIFIED** | ① DOI 在 Crossref 解析成功 ② 标题相似度 ≥ 0.85 ③ 年份精确匹配 ④ 首作者姓匹配 ⑤ **≥1 个独立第二来源**（S2 或 OpenAlex）同意 | 进入支撑评估 |
| **LIKELY_REAL** | 无 DOI，但 Semantic Scholar 与 OpenAlex **双源**标题 ≥ 0.85 + 年份 + 首作者一致 | fallback（默认接受；--strict 拒绝） |
| **UNVERIFIED** | 任一源命中但证据不足 / 全部源无结果 | **REJECT** |
| **CONFLICT** | DOI 解析成功但标题/年份/首作者**冲突** | **REJECT**（元数据冲突=重大红旗，不降级） |

## 流程
1. 有 DOI → Crossref `/works/{doi}` 验证（主闸门）。
2. Crossref 无记录 → 降级双源交叉验证（S2 title search + OpenAlex title search），给 LIKELY_REAL/UNVERIFIED。
3. 无 DOI → 直接双源交叉验证。
4. 每次尝试（含 UNVERIFIED/CONFLICT 拒绝）**必须写 verification_log.jsonl**——审计可证明每篇入选论文都过了闸门。

## 为什么需要第二来源
单源（哪怕 Crossref）记录可能被误配或 DOI 复用。第二来源同意把误配率压到可忽略水平；
同时把「DOI 能解析但元数据错配」的 CONFLICT 显式暴露出来，而不是默默接受。

## 阈值
- TITLE_THRESHOLD = 0.85（标题相似度，Levenshtein 归一）。
- 年份：精确相等（claimed None 时跳过该检查）。
- 首作者：姓氏一致（大小写不敏感；未提供作者时跳过）。

## 反模式（禁止）
- ❌ 把 verification 当 ranking feature：`composite += verified * 0.1`。
- ❌ DOI 解析成功就直接 VERIFIED（漏掉标题冲突）。
- ❌ UNVERIFIED 论文偷偷以"可能是真的"混入。
