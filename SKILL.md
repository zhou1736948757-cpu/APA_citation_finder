---
name: APA_citation_finder
description: 学术引用的完整证据管线——论断提取、多源检索、论文真实性验证、论断-证据支撑度评估、排名、格式化和文档插入、最终审计。用于添加引用、插入引用、找文献、文献支撑、引用验证、citation、reference、加引用、补充参考文献、找论文支撑观点、APA/IEEE/GB-T-7714 引用格式、论文引用。触发概念：citation, reference, academic evidence, 文献支撑, 加引用, 找论文, citation verification, claim support, APA, 论文引用, 引文审计。
---

# APA_citation_finder — Claim → Evidence → Verification → Citation → Insertion → Audit

APA_citation_finder 是一个**九阶段证据管线**，把用户文档/论断变成经过验证、可审计的引用。
它不是"更大号的搜索工具"——每一篇被引用的论文都必须通过：真实性验证（Gate）→
支撑度评分（阈值）→ 排名 → 独立审计。

**IRON RULES（违反任何一条 = 交付失败）：**
1. 绝不编造论文/DOI/作者；2. 绝不只凭标题相关性给引用；3. 真实论文 ≠ 论断支撑（两个独立关卡）；4. 证据不足绝不硬塞引用；5. 验证先于支撑评分；6. 支撑评分先于排名；7. 排名永不拯救未过支撑阈值的论文；8. 基础性论断优先原始出处；9. 不静默改写不支持的论断；10. 每条引用可回溯证据链；11. 最终审计是插入的强制关卡；12. 证据文本只来自真实获取内容，模型永不生成引文。

---

## 1. 何时使用

- 用户要求给文档/段落/论断添加学术引用（docx、tex、md、txt）
- 用户给出论断，要求"找文献支撑这个观点"
- 用户要求审计已有引用是否真实、是否支撑对应论断
- 触发词：citation / reference / 加引用 / 找论文 / 文献支撑 / 论文引用 / citation verification / claim support / APA / GB-T-7714 / 引文

## 2. 先做的事：Stage 0 意图与偏好

**先推断，能推断就不问**；只有真正歧义时用**一个问题**确认。

| Mode | 判定信号 | 工作流 |
|---|---|---|
| A 文档引用 | 用户给了 .docx/.tex/.md 文档 | 全文提取 claim → 检索 → 插入 + 更新参考文献 |
| B 论断支撑 | 用户给一句话/一段话 | 提取 → 检索 → 评分 → 输出候选列表（不修改文档） |
| C 引用审计 | 用户给已有引用/已引用文档 | 逐条验证真实性 + 支撑度 → 审计报告 |

预设（可组合）：**Academic Standard**（默认） / **Recent Evidence** / **Foundational Theory** / **High Rigor** / **Fast**。

推断并应用（不逐条问）：引用风格（跟随文档既有风格；无则 APA）、每论断篇数（默认 1）、
年份范围（无硬限；Recent Evidence 近 5 年）、预印本（默认优先同行评审）、must_cite 列表、
本地文献路径、可选源（默认关）。

## 3. 九阶段执行

### Stage 1 论断提取（scripts/extract_claims.py, classify_claims.py, detect_citation_need.py, normalize_claim.py, generate_queries.py）

1. 输入粒度：句子/段落/章节/全文（默认句子级；文档模式按全文）。
2. 复合句拆分：`and/but/while/whereas/which` 且每分句 ≥6 词 → 拆独立论断；不拆枚举。中文按句读拆。
3. 判定引用需求 REQUIRED/RECOMMENDED/OPTIONAL/NOT_NEEDED；分类 9 种类型。
4. 规范化：**original_text 逐字保留（含中文）**；normalized_claim 用于检索。
5. 每论断生成 4 类查询：precise / broad / synonym / domain（理论类加 authoritative/foundational）。
   查询 ≠ 论断原文。
6. 产出 `claims.jsonl`。

```bash
cd scripts
python extract_claims.py --input ../output/paper.docx --output ../output/claims.jsonl
python classify_claims.py --input ../output/claims.jsonl --output ../output/claims.jsonl
python detect_citation_need.py --input ../output/claims.jsonl --output ../output/claims.jsonl
python normalize_claim.py --input ../output/claims.jsonl --output ../output/claims.jsonl
python generate_queries.py --input ../output/claims.jsonl --output-dir ../output
```

### Stage 2–3 检索与去重（scripts/search_all.py, deduplicate.py）

- 每条查询并行跑核心 3 源：**OpenAlex**（发现）、**Semantic Scholar**（发现+摘要）、**Crossref**（元数据权威）。
- 可选源（懒加载，默认关）：exa / google_scholar / pop（Publish-or-Perish CLI）/ local。
- 结果统一 schema，DOI 精确去重 + 标题≥0.90 模糊去重，黑名单期刊过滤，tier/recency 富化。

```bash
python search_all.py --claim-json ../output/claim_C001.json \
  --output-dir ../output --from-year 2015 --email your@email.org
```

### Stage 3 去重（deduplicate.py，已并入 search_all）

### Stage 4 论文真实性验证 —— 硬闸门（scripts/verify_papers.py）

| 判定 | 含义 | 处置 |
|---|---|---|
| VERIFIED | Crossref DOI + 标题≥0.85 + 年份 + 首作者 + 第二来源同意 | ✅ 进入支撑评估 |
| LIKELY_REAL | 无 DOI 双源交叉一致 | fallback（默认可用） |
| UNVERIFIED | 无法确认 | ❌ 拒绝 |
| CONFLICT | DOI 解析但元数据冲突 | ❌ 拒绝 |

```bash
.venv/bin/python verify_papers.py ../output/candidates.json --log ../output/verification_log.jsonl -o ../output/verified.json
```

### Stage 5 证据检索（scripts/fetch_evidence.py）

FULL_TEXT > ABSTRACT > SUMMARY > METADATA_ONLY；摘要按 OpenAlex→S2→arXiv 顺序补取；
**evidence_text 只来自真实内容**；METADATA_ONLY 封顶 0.74。

### Stage 6 支撑度评估（scripts/score_support.py）

- 证据分级：FULL_TEXT > ABSTRACT > SUMMARY > METADATA_ONLY；evidence_text 只来自真实获取内容。
- Rubric：≥0.90 DIRECT / ≥0.75 DIRECT / ≥0.60 PARTIAL / ≥0.30 BACKGROUND / 低 CONTRADICTORY 或 INSUFFICIENT。
- **硬阈值 0.60（High Rigor 0.75）**；矛盾证据必须列出；不足 → NO SUFFICIENT EVIDENCE FOUND + 三选项
  （引用标记 / 弱化论断需授权 / 删除论断需授权），改写必须记录 claim_rewritten。

**三种引擎（按优先级）**：

1. **LLM API 引擎**（无人值守批量）：`.env` 配置 USE_LLM_SUPPORT/LLM_API_KEY/LLM_API_ENDPOINT/LLM_MODEL 后，
   `score_support.py --claim "..." --papers evidenced.json -o scored.json` 自动调用。

2. **语义判定模式（默认，跨 harness 通用，无需任何 key/脚本）**：主对话模型自己就是判定者。
   对每篇论文：读取 evidence_text（或 evidence_path 指向的 PDF 全文）→ 按上述 rubric 判定 →
   把判定写入 `support_log.jsonl`（event: support_score，scoring_method: "agent_llm"，
   字段：claim_id/paper_id/title/doi/support_score/support_level/evidence_level/reasoning）
   并更新 scored JSON。铁律：只依据证据文本，绝不编造；证据与论断相反 → CONTRADICTORY；
   无证据 → INSUFFICIENT_EVIDENCE；METADATA_ONLY 上限 0.74（级别随分数重推）。
   此模式不依赖任何特定 harness 的 subagent/工具机制——任何能读写文件的 agent 均可执行。
   判定结果必须同时产出 **`support_report.md`**（详细 MD 报告，格式见下）。

3. **启发式兜底**（完全离线/无人值守）：`score_support.py` 无 key 时自动用关键词覆盖 + 否定检测。

```bash
# 引擎 1/3（脚本路径）
.venv/bin/python score_support.py --claim "Generative AI significantly improves learning" --claim-id C001 --papers ../output/verified.json -o ../output/scored_C001.json
# 引擎 1/3 加 --report-md 产出统一格式报告
.venv/bin/python score_support.py --claim "..." --papers evidenced.json -o scored.json --report-md support_report.md
# 引擎 2（语义路径）：主对话直接读 evidenced.json → 逐篇判定 → 写 support_log.jsonl + scored JSON + support_report.md
```

**`support_report.md` 固定格式**（无论哪种引擎，报告结构一致，机器可查）：
```markdown
# 支撑度评估报告 — <claim_id>
## 论断
> <论断原文>
- 评估时间 / 硬阈值（0.60，High Rigor 0.75）

## 判定汇总
| # | 论文 | 年份 | 证据级别 | 分数 | 级别 | 结论 |
（结论列：✅ 可引用 / ❌ 低于阈值 / ⚠️ 矛盾（永不引用）/ ❌ 证据不足）
- 通过 N 篇 · 拒绝 M 篇 · 矛盾 K 篇（显式标注）· 证据不足 L 篇

## 逐篇判定
### N. <标题>（<年份>）
- 元数据: 作者 · 期刊 · DOI
- 证据级别: ABSTRACT（来源: openalex）
- 证据摘录: > 真实获取原文前 300 字（绝不模型生成）
- 判定: 0.66 PARTIAL（评分引擎: agent_llm）
- 理由: <一句话，引用证据>
- 结论: ✅/❌/⚠️ + 说明

## 矛盾证据清单（永不引用）      ← 有矛盾时必出
## 证据不足清单                  ← 有不足时必出
## 备注                          ← METADATA_ONLY 上限应用记录等
```

### Stage 7 排名（scripts/rank_candidates.py）

只排通过验证+阈值的论文。Profile：CURRENT_EMPIRICAL（support .40 quality .25 recency .25 diversity .10）、
FOUNDATIONAL（support .40 originality .35 authority .20 recency .05）、METHOD、DEFINITION。
**support 永远压过声望**；默认每 claim 1 篇（contested 2、systematic 3）。

### Stage 8 格式化 + 插入（scripts/format_citation.py, format_bibtex.py, insert_docx.py, insert_latex.py, update_references.py）

- APA 7 / IEEE / Nature / Vancouver / GB-T-7714-2015 / BibTeX。
- DOCX：run 级插入保留格式；已有引用检测（keep/supplement/replace/flag）；不破坏表格/脚注。
- LaTeX：`\cite/\parencite/\textcite` 自动适配；参考文献/refs.bib 去重更新。

### Stage 9 最终审计（scripts/audit_bibliography.py, audit_entailment.py, audit_pipeline.py）

- **Gate 8A**：文档引用 ↔ 参考文献 ↔ final_papers ↔ verification_log ↔ DOI 一致。
- **Gate 8B**：独立评审（不暴露 Stage 6 分数）→ PASS/WEAK/FAIL；FAIL 移除；WEAK High Rigor 拒绝。
- **总判定**：PASS 交付 / WEAK 标记交付 / FAIL 拒绝交付。

```bash
.venv/bin/python audit_pipeline.py ../output --docx ../output/cited.docx --references ../output/references.txt -o ../output/audit_report.json
```

## 7. 证据链产物（全部写入 output/ 或指定目录）

`claims.jsonl` · `search_log.jsonl` · `evidence_log.jsonl` · `verification_log.jsonl` ·
`support_log.jsonl` · `final_papers.json` · `audit_report.json` —— 缺失即审计 FAIL。

## 8. 常用命令速查（scripts/ 内）

| 任务 | 命令 |
|---|---|
| 提取论断 | `extract_claims.py --input paper.md --output claims.jsonl` |
| 分类/需求/规范化 | `classify_claims.py` / `detect_citation_need.py` / `normalize_claim.py` |
| 生成查询 | `generate_queries.py --input claims.jsonl --output-dir .` |
| 检索 | `search_all.py --claim-json claim_C001.json --output-dir . --email you@x.org` |
| 验证 | `verify_papers.py candidates.json -o verified.json` |
| 证据 | `fetch_evidence.py verified.json -o evidenced.json` |
| 评分 | `score_support.py --claim "..." --claim-id C001 --papers evidenced.json -o scored.json` |
| 排名 | `rank_candidates.py --claims claims.json --candidates-dir . -o final_papers.json` |
| 格式化 | `format_citation.py --style apa --input paper.json` / `format_bibtex.py --input final_papers.json --output refs.bib` |
| 插入 docx | `insert_docx.py in.docx plan.json --output out.docx` |
| 插入 latex | `insert_latex.py in.tex plan.json --output out.tex` |
| 更新参考文献 | `update_references.py --mode docx --papers final_papers.json --style apa --docx out.docx` |
| 审计 | `audit_pipeline.py output/ --docx out.docx --report output/audit_report.json` |

## 9. 环境与依赖

- venv：`/Users/mac/skills/APA_citation_finder/.venv`（核心依赖已装）；`pip install -r requirements.txt`。
- 可选：exa-py / scholarly / PyMuPDF / pop8query（tools/ 已内置）—— 懒加载，缺失不影响核心流。
- Stage 6 支撑评分三种引擎：① LLM API（.env 配置，无人值守批量）；
  ② **语义判定模式**（默认，跨 harness 通用）：主对话模型直接读证据、按 rubric 判定、
  写 support_log.jsonl（scoring_method="agent_llm"），不依赖任何 subagent/工具机制；
  ③ 启发式兜底（关键词覆盖 + 否定检测）。
- 无 key：核心 3 源免费无需 key。LLM 评分可选（.env）。

## 10. 已知限制

- 无官方 Google Scholar API：兜底源，CAPTCHA 风险，默认关。
- S2 限速 1 rps：大文档检索耗时随论断数线性增长。
- 元数据级证据（无摘要）只能给 PARTIAL 上限；无法获取全文时不能给强引用。
- 启发式回退评分低于 LLM 精度（support_log 记录方法，审计可见）。
- 中文文献：OpenAlex/Crossref 覆盖有限，建议本地文献补充。
- BibTeX 只追加不重写（防损坏用户文件）。

## 参考资料

references/workflow.md · data-schema.md · claim-types.md · citation-need.md ·
search-strategy.md · scoring.md · verification.md · support-grading.md ·
journal-quality.md · citation-formats.md · anti-hallucination.md ·
optional-sources.md · error-handling.md
