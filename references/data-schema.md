# APA_citation_finder — 数据模式（data-schema）

## 1. Claim（论断）— claims.jsonl

```json
{
  "claim_id": "C001",
  "original_text": "生成式 AI 显著提升了学生的学习效果。",
  "normalized_claim": "Generative AI significantly improves student learning outcomes.",
  "claim_type": "EMPIRICAL",            // EMPIRICAL|THEORETICAL|DEFINITION|METHOD|STATISTICAL|HISTORICAL|CONTEXTUAL|NORMATIVE|CURRENT_STATE
  "citation_need": "REQUIRED",         // REQUIRED|RECOMMENDED|OPTIONAL|NOT_NEEDED
  "section": "引言",
  "paragraph_id": 3,
  "sentence_id": 1,                    // 0-based
  "char_start": 120,
  "char_end": 180,
  "rewrite_permission": "cautious"     // false|cautious|allowed
}
```
规则：`original_text` 逐字保留原文（含中文）；`normalized_claim` 用于检索；`query != claim`（查询由 Stage 2 单独生成）。

## 2. Paper（统一论文记录）— 44

| 字段 | 说明 |
|---|---|
| paper_id | sha256(title|year|first-author) 16 hex |
| title / authors[] / year / journal / doi / url / abstract | 核心元数据；authors 统一 "Last, First" |
| venue / venue_type | journal / conference / preprint / book / thesis / other |
| issn_l / volume / issue / pages / publisher | 细节 |
| citation_count | 引用数（发现时） |
| open_access_pdf / is_oa / oa_status | 开放获取 |
| keywords / language | 分类 |
| source_layer | api / local / web |
| source_apis | ["openalex", "semantic_scholar", "crossref"] 全路径 |
| source | 主来源 |
| tier_score / recency_score | 质量信号 |
| support_score / support_level / composite_score | Stage 6/7 填充 |

## 3. Claim–Paper 关系 — 45

```
{ claim_id, paper_id, support_score, support_level,
  evidence_source, evidence_text, selection_status, reason }
```
- evidence_text 只来自实际检索内容，绝不模型生成。
- selection_status ∈ SELECTED / REJECTED_LOW_SUPPORT / REJECTED_UNVERIFIED / REJECTED_CONTRADICTORY / REJECTED_DUPLICATE。

## 4. 验证记录（verification_log.jsonl）

```
{ event:"verification", paper_id, title_claimed, doi_claimed, year_claimed,
  first_author_claimed, verdict, details }
verdict ∈ VERIFIED | LIKELY_REAL | UNVERIFIED | CONFLICT
```

## 5. 证据记录（evidence_log.jsonl）

```
{ event:"evidence", paper_id, title, doi, evidence_level, evidence_source, evidence_text }
evidence_level ∈ FULL_TEXT | ABSTRACT | SUMMARY | METADATA_ONLY
```

## 6. 支撑记录（support_log.jsonl）

```
{ event:"support_score", claim_id, paper_id, support_score, support_level,
  evidence_level, scoring_method, reasoning }
scoring_method ∈ llm | heuristic
```

## 7. 审计（audit_report.json）

```
{ overall: PASS|WEAK|FAIL,
  gates: { 8A_bibliographic: {...}, 8B_entailment: {...} },
  chain: { present: {...}, findings: [...] } }
```
