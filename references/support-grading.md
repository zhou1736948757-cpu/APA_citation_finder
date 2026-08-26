# APA_citation_finder — 支撑度分级（support-grading）

## Rubric（score_support.py）

| 分数 | 等级 | 标准 |
|---|---|---|
| 0.90–1.00 | **DIRECT** | 人群/变量/关系/结论与论断直接匹配，证据明确验证核心断言 |
| 0.75–0.89 | **DIRECT** | 明确支持，但人群、语境或措辞强度有可见差距（如"可能提升"vs"显著提升"） |
| 0.60–0.74 | **PARTIAL** | 只支撑论断的一部分（如支持机制但未证方向） |
| 0.30–0.59 | **BACKGROUND** | 领域背景相关，不能作为该论断的主引用 |
| 0.00–0.29 | **CONTRADICTORY / 不支持** | 证据与论断矛盾，或毫无实质关联 |

## 硬规则

1. **硬阈值**：默认 0.60；High Rigor 0.75。低于阈值 → 不引用。
2. **METADATA_ONLY 封顶**：证据只有元数据（无摘要/全文）→ 分数上限 0.74（最多 PARTIAL）；
   例外：论断本身是出版元数据断言（"该文发表于 2020"）。
3. **矛盾不得静默**：LLM 判 CONTRADICTORY → 论文不入选，**在报告与 support_log 中列出**（注明证据文本）。
4. **不给证据硬打分**：无摘要且无法获取 → INSUFFICIENT_EVIDENCE（不是低分直接当不支持）。
5. **不做暗示性生成**：evidence_text 永不模型合成；评分依据必须可追溯。

## 评分引擎
- LLM（OpenAI 兼容，.env：USE_LLM_SUPPORT / LLM_API_KEY / LLM_API_ENDPOINT / LLM_MODEL）：
  温度 0.1，JSON 输出 {support_score, support_level, reasoning}。
- 无 LLM → 确定性启发式：论断↔摘要关键词重叠（a）×0.75 + 论断↔标题（t）×0.25，封顶。
- `scoring_method` 记录在 support_log.jsonl —— 审计可见评分可靠性。

## 论断改写（rewrite_permission）
- 无足够证据时：**禁止硬塞引用** → 输出「NO SUFFICIENT EVIDENCE FOUND」+ 三选项：
  ① 在论断处加"citation needed"标记（不做）② 弱化论断（须授权）③ 删除/移出论断（须授权）。
- rewrite_permission：false（默认谨慎）→ 只报告不改写；cautious → 弱化需用户确认；
  allowed → 可主动弱化，但每次改写记录 `claim_rewritten` 事件（原句 → 新句 → 理由）。
