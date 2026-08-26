# Migration Inventory — scipilot-cite-skill × citation-finder → APA_citation_finder

> Generated from a full source audit (scripts + references + data) performed before any code was written.
> Audit date: 2026-08-26. Source of truth: actual code, not README descriptions.

## A. scipilot-cite-skill

| Existing Component | Source Skill | Keep | Modify | Replace | Notes |
| ------------------ | ------------ | ---- | ------ | ------- | ----- |
| SKILL.md 8-Stage workflow | scipilot | ✅ | ✅ | | Stage 0 preference collection → become Stage 0 (infer-first, ask-only-when-needed); Stage 7 Gate 8 → split into Gate 8A/8B; new claim pipeline stages inserted |
| `scripts/utils.py` (title_similarity, rate_limited_request, extract_keywords, assign_citation_numbers, make_bibtex_key, paper_id_hash, append_jsonl, author helpers) | scipilot | ✅ | ✅ | | Core of new `utils/` package; keep rate-limit/retry, similarity, ID hashing, JSONL appends; add normalized-DOI + claim-id helpers |
| `scripts/search_papers.py` — 3-source parallel search (S2/OpenAlex/Crossref), per-api ×3 fetch, DOI dedupe, preprint filter, evidence_log writing | scipilot | ✅ | ✅ | | Logic split into `search_openalex.py` / `search_semantic_scholar.py` / `search_crossref.py` + orchestrator `search_all.py`; S2 source is the new default core source |
| `scripts/verify_paper.py` — DOI via Crossref, cross-check S2+OpenAlex, VERIFIED/LIKELY_REAL/UNVERIFIED, batch_verify + verification_log | scipilot | ✅ | ✅ | | Becomes `verify_papers.py`; add CONFLICT verdict for DOI/title/year/author mismatch; LIKELY_REAL → fallback-only policy |
| `scripts/format_citation.py` — IEEE/APA7/Nature/Vancouver/GB-T-7714 + bibtex entry | scipilot | ✅ | ✅ | | `format_citation.py` keeps all 5 styles; APA gains 1/2/3+ author in-text variants + same-author-same-year suffix; BibTeX moved to `format_bibtex.py` |
| `scripts/insert_citations_docx.py` — parse docx, section detection, insertion plan, [N] markers, References section | scipilot | ✅ | ✅ | | `insert_docx.py`: paragraph/run-level insertion, existing-citation parse (APA/[/[\]] forms), keep/supplement/replace decision, claim_id linkage |
| `scripts/insert_citations_latex.py` — thebibliography + bibtex modes, \cite insertion | scipilot | ✅ | ✅ | | `insert_latex.py`: \cite/\parencite/\textcite adaptation; existing-citation awareness |
| `scripts/audit_no_hallucination.py` — Gate 8 100% re-verify + verification-log reconciliation | scipilot | ✅ | ✅ | | Split into `audit_bibliography.py` (Gate 8a) + `audit_entailment.py` (Gate 8b, reviewer pass) + `audit_pipeline.py` (orchestrator) |
| `scripts/evidence_log.jsonl / verification_log.jsonl / final_papers.json / audit_report.json` contract | scipilot | ✅ | ✅ | | Expanded to full evidence chain: claims.jsonl, search_log, evidence_log, verification_log, support_log, final_papers, audit_report |
| `references/citation-formats.md` | scipilot | ✅ | ✅ | | Merged into `references/citation-formats.md` (+ APA in-text rules) |
| `references/api-reference.md` | scipilot | ✅ | ✅ | | Merged into `references/search-strategy.md` + `references/api-reference.md` |
| `references/workflow.md` | scipilot | ✅ | ✅ | | Replaced by `references/workflow.md` describing the 9-stage pipeline |
| `assets/format_templates/*.json` | scipilot | ✅ | — | | Copied as `assets/format_templates/` (used by format_citation.py loader) |
| IRON RULES / Stage 0 question battery | scipilot | ✅ | ✅ | | 12 IRON RULES; Stage 0 infer-first, ask-only-if-needed |
| Search budget (per-API ×3, retry/backoff) | scipilot | ✅ | — | | preserved in `search_all.py` + `utils/http.py` |
| IRON RULE numbering order | scipilot | ✅ | ✅ | | First-appearance numbering for numeric styles, existing-citation continuation |

## B. citation-finder

| Existing Component | Source Skill | Keep | Modify | Replace | Notes |
| ------------------ | ------------ | ------ | ------ | ------- | ----- |
| SKILL.md — 4-step claim pipeline | citation-finder | ✅ | ✅ | | Claim pipeline becomes Stages 1–6 core architecture |
| `scripts/claim_extractor.py` — sentence split, filter, 30-word truncation | citation-finder | ✅ | ✅ | | `extract_claims.py`: + compound-sentence split (C001/C002), position tracking (char offsets), paragraph/section metadata, keep Chinese originals |
| `scripts/citation_finder.py` — OpenAlex+Crossref search, year_normalize, merge, enrich-tiers | citation-finder | ✅ | ✅ | | year_normalize → utils; merge/enrich split into `deduplicate.py` + `rank_candidates.py`; `search` CLI subcommands merged into `search_all.py` |
| `scripts/dedup.py` — source-priority field merge | citation-finder | ✅ | ✅ | | `deduplicate.py`: + normalized-DOI, title-similarity ≥0.90 + year-close fuzzy match, records source_apis[] |
| `scripts/support_llm.py` — LLM support scoring, .env config | citation-finder | ✅ | ✅ | | `score_support.py`: LLM path + heuristic fallback; DIRECT/PARTIAL/BACKGROUND/CONTRADICTORY/INSUFFICIENT_EVIDENCE; hard thresholds; metadata-only cap |
| `scripts/rank_and_filter.py` — composite rank + ≤10/unverified≤3 rules | citation-finder | ✅ | ✅ | | `rank_candidates.py`: profile-based weights (CURRENT_EMPIRICAL/FOUNDATIONAL/METHOD/DEFINITION), support-threshold-first, diversity tiebreak |
| `scripts/format_bibtex.py` — bibtex generation, key dedupe | citation-finder | ✅ | ✅ | | `format_bibtex.py` (merged with scipilot bibtex entry builder) |
| `scripts/exa_search.py` — Exa optional source | citation-finder | ✅ | ✅ | | lazy-import; off by default; needs EXA_API_KEY |
| `scripts/search_google_scholar.py` — scholarly, proxy option | citation-finder | ✅ | ✅ | | lazy-import; off by default; CAPTCHA/rate-limit fallback role |
| `scripts/journal_tier_lookup.py` + `tier_utils.py` — OpenAlex source tier + conference CSV + blacklist | citation-finder | ✅ | ✅ | | `utils/journal.py`: tier as quality signal only, never dominant over support |
| `data/priority_journals.csv`, `data/blacklist_journals.csv` | citation-finder | ✅ | — | | copied |
| Zotero MCP flow (`citation_finder.py merge`) | citation-finder | ✅ | ✅ | | `search_zotero.py` + agent MCP flow; optional, auto-if-available |
| local-file search (agent step) | citation-finder | ✅ | ✅ | | `search_local.py` (PDF via PyMuPDF if available, TXT/MD native) |
| `references/claim-types.md` | citation-finder | ✅ | ✅ | | + citation-need classification |
| `references/data-schema.md` | citation-finder | ✅ | ✅ | | + paper_id/verification fields, claim/paper/link schemas |
| `references/search-strategy.md` | citation-finder | ✅ | ✅ | | + source roles (Crossref = verification-first), source tiers |
| `references/support-grading.md` | citation-finder | ✅ | ✅ | | + new 0–1 rubric bands, evidence-level caps, contradiction handling |
| `references/journal-tiers.md` | citation-finder | ✅ | ✅ | | `journal-quality.md` — quality signal only |
| `references/api-reference.md` | citation-finder | ✅ | ✅ | | merged + Semantic Scholar/Crossref DOI endpoints |
| `.env` (LLM/Exa config) convention | citation-finder | ✅ | — | | documented; all optional, lazy-loaded |

## C. New implementations (neither skill had these)

| Component | New in APA_citation_finder | Notes |
| --------- | --------------- | ----- |
| `classify_claims.py` | ✅ | claim type: EMPIRICAL/THEORETICAL/DEFINITION/METHOD/STATISTICAL/HISTORICAL/CONTEXTUAL/NORMATIVE/CURRENT_STATE |
| `detect_citation_need.py` | ✅ | REQUIRED/RECOMMENDED/OPTIONAL/NOT_NEEDED + density control |
| `normalize_claim.py` | ✅ | original/normalized/concepts/synonyms/population/context/outcome/time/geography |
| `generate_queries.py` | ✅ | broad/precise/synonym/domain + authoritative/systematic-review/foundational |
| `fetch_evidence.py` | ✅ | evidence_level FULL_TEXT/ABSTRACT/SUMMARY/METADATA_ONLY; abstract from OpenAlex inverted index, S2; full-text best-effort |
| `audit_entailment.py` | ✅ | Gate 8b independent reviewer pass (claim→citation→evidence→PASS/WEAK/FAIL) |
| `audit_pipeline.py` | ✅ | runs Gates 8a+8b + evidence-chain integrity, writes audit_report.json |
| `presets` (Academic Standard / Recent Evidence / Foundational Theory / High Rigor / Fast) | ✅ | in SKILL.md + `references/workflow.md` |
| `tests/` (unit/integration/fixtures/regression) | ✅ | RED→GREEN→REFACTOR, 10 acceptance scenarios |
| `output/` run workspace | ✅ | per-run evidence chain artifacts |

## D. Components intentionally dropped / not migrated

| Component | Reason |
| --------- | ------ |
| `search_all.py` printing raw results to stderr/stdout intermixed with progress | replaced by clean orchestrator + JSONL logs |
| citation-finder implicit "search everything" default | replaced by source roles (Crossref = verification-first) |
| scipilot unconditional Stage 0 question battery | replaced by Stage 0 infer-first (ask only un-inferable) |
| composite weight formula `tier*0.3+support*0.3+recency*0.4` (citation-finder) | replaced by per-profile weights; verification is a gate, not a weight |
| `unverified ≤3 papers` pass-through rule | replaced by hard support threshold (default 0.60) + verification gate |
