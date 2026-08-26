# APA_citation_finder — Workflow（9 阶段管线）

**核心原则（IRON RULES）**：
1. 绝不编造论文/DOI；每篇论文必须有来源。
2. 论文"真实" ≠ "能支撑论断"——真实性与支撑度是两个独立关卡，永不合并。
3. 证据不足时绝不硬塞引用 → 输出「NO SUFFICIENT EVIDENCE FOUND」+ 三选项。
4. 先验证论文真实性（Stage 4 GATE），再评支撑（Stage 6），再排名（Stage 7）。
5. 排名权重永不拯救未过支撑阈值的论文。
6. 每条插入的引用必须可回溯到证据链（claims → search → evidence → verification → support → audit）。

---

## Stage 0 — 意图与偏好（Modes A/B/C + Presets）

先推断用户意图，**能推断就不问**；只有真正歧义才用**一个**问题确认。

| Mode | 意图 | 输出 |
|---|---|---|
| **A 文档引用** | 用户提供 .docx / .tex 文档 | 正文插入引用 + 参考文献更新 |
| **B 论断支撑** | 用户给一段话/观点 | 候选文献列表 + 支撑评分 |
| **C 引用审计** | 用户给已有文档/引用 | 引用真实性 + 支撑度审计报告 |

Preset 预设（可叠加偏好覆盖）：
- **Academic Standard**（默认）：阈值 0.60，可 WEAK 替换
- **Recent Evidence**：年限权重↑（近 5 年优先）
- **Foundational Theory**：FOUNDATIONAL 排名 profile
- **High Rigor**：阈值 0.75，WEAK 一律拒绝
- **Fast**：跳过可选源，只跑核心 3 源

偏好项（默认值 + 推断，不逐条询问）：citation_style（默认按文档既有风格）、per_claim 篇数（默认 1）、year_range（默认无硬限）、preprint 策略（默认首选同行评审）、must_cite 列表、目标章节、本地文献路径。

## Stage 1 — 论断提取（extract_claims.py + classify_claims.py + detect_citation_need.py + normalize_claim.py + generate_queries.py）

1. 输入粒度：句子 / 段落 / 章节 / 全文（用户指定；默认句子级）。
2. 复合句拆分：`and / but / while / whereas / which` 连接、且每个分句 ≥6 词 → 拆为独立 claim（不拆枚举列表）。含中文时按中文句读拆分。
3. 引用需求判定：REQUIRED（强断言、实证数字、定义）/ RECOMMENDED / OPTIONAL / NOT_NEEDED（常识、自证、个人观察）。
4. 类型分类：EMPIRICAL / THEORETICAL / DEFINITION / METHOD / STATISTICAL / HISTORICAL / CONTEXTUAL / NORMATIVE / CURRENT_STATE。
5. 规范化：original_text 逐字保留（含中文原文）；normalized_claim 用于检索与评分；提取 search_concepts + synonyms。
6. 多查询生成：每条 claim 生成 4 类查询 —— broad（宽）、precise（窄）、synonym（同义替换）、domain（领域限定）；理论/方法类附加 authoritative / foundational 查询。**查询 ≠ 论断原文**。
7. 产出 `claims.jsonl`（每条：claim_id, original_text, normalized_claim, claim_type, citation_need, section, paragraph_id, sentence_id, char_start, char_end, rewrite_permission）。

## Stage 2 — 检索（search_all.py）

- 核心 3 源并行（每条查询）：OpenAlex（语义发现）、Semantic Scholar（发现+摘要）、Crossref（DOI/元数据权威）。
- 可选源（默认关，不破坏核心流）：Exa、Google Scholar、本地文件。
- 每条查询 × 每源限速（OpenAlex 10 rps / S2 1 rps / Crossref 礼貌池）。
- 每 claim 的候选写入 `claim_<claim_id>.json`；全部检索写入 `search_log.jsonl`。

## Stage 3 — 去重（deduplicate.py）

- DOI 精确/规范化匹配（去前缀、小写）→ 同组。
- 无 DOI：title_similarity ≥ 0.90 且年份差 ≤1 且首作者姓一致。
- 合并保留 `source_apis[]` 全部来源；记录 `source_layer`。
- 黑名单期刊（data/blacklist_journals.csv）过滤。

## Stage 4 — 论文真实性验证（verify_papers.py）——HARD GATE

| 判定 | 条件 | 处置 |
|---|---|---|
| VERIFIED | Crossref DOI 解析 + 标题≥0.85 + 年份精确 + 首作者姓一致 + ≥1 个第二来源（S2/OpenAlex）同意 | 进入 Stage 6 |
| LIKELY_REAL | 无 DOI，但 S2 与 OpenAlex 双源标题≥0.85 + 年份 + 作者一致 | 仅作 fallback（默认可用，--strict 拒绝） |
| UNVERIFIED | 无法可靠确认 | **REJECT** |
| CONFLICT | DOI 解析但标题/年份/作者冲突 | **REJECT** |

- 验证是**闸门**，绝不当作排名权重（永远不是 composite × 0.1）。
- 每次尝试（含拒绝）写入 `verification_log.jsonl`。

## Stage 5 — 证据检索（fetch_evidence.py）

- 偏好：FULL_TEXT 片段 > ABSTRACT > SUMMARY > METADATA_ONLY。
- 摘要补齐顺序：候选自带摘要 → OpenAlex（倒排索引重建）→ Semantic Scholar → arXiv 摘要（仅 arXiv id）。
- **evidence_text 必须来自实际获取的内容，模型永不生成证据引文**。
- METADATA_ONLY 证据上限 0.74（除非论断本身是关于出版元数据）。
- 写 `evidence_log.jsonl`。

## Stage 6 — 论断-证据支撑评估（score_support.py）

- 引擎：LLM（.env 配置，OpenAI 兼容）→ 失败/未配置时确定性启发式（关键词重叠）。
- 评分 rubric：
  | 区间 | level |
  |---|---|
  | 0.90–1.00 | DIRECT（人群/变量/关系/结论匹配） |
  | 0.75–0.89 | DIRECT（明确支持但人群/语境/措辞强度有差距） |
  | 0.60–0.74 | PARTIAL（仅支撑论断一部分） |
  | 0.30–0.59 | BACKGROUND（领域背景，不作主引用） |
  | 0.00–0.29 | CONTRADICTORY / 不支持 |
- 硬阈值：默认 0.60；High Rigor 0.75。**低于阈值不引用**。
- 矛盾证据**不得静默忽略**：LLM 判 CONTRADICTORY 时该论文不入选并在报告中列出。
- 无足够证据 → 「NO SUFFICIENT EVIDENCE FOUND」+ 选项：加引文标记 / 弱化论断（须授权）/ 删除论断（须授权）。
- 论断改写权限：`rewrite_permission` = false / cautious（默认）/ allowed；任何改写必须记录 `claim_rewritten` 事件。
- 写 `support_log.jsonl`（claim_id, paper_id, score, level, evidence_level, reasoning）。

## Stage 7 — 排名（rank_candidates.py）

只对**通过 Stage 4 验证 + 超过 Stage 6 阈值**的论文排名：

| Profile | 权重 | 适用 |
|---|---|---|
| CURRENT_EMPIRICAL | support .40 quality .25 recency .25 diversity .10 | 经验类/现状类 |
| FOUNDATIONAL | support .40 originality .35 authority .20 recency .05 | 理论/历史 |
| METHOD | support .40 method_authority .35 relevance .20 recency .05 | 方法类 |
| DEFINITION | support .50 originality .30 authority .20 | 定义类（原理论文/权威手册优先） |

- 期刊层级（tier_score）只是质量信号；**support 永远压过声望**。
- 多样性（同作者/同期刊）是软 tiebreak，绝不牺牲 support。
- 数量控制：默认每 claim 1 篇；重大/有争议论断 1–2；系统性综述最多 3；禁止引用倾倒。
- 输出 `final_papers.json`（papers + links：claim_id ↔ paper_id ↔ support ↔ evidence ↔ selection_status ↔ reason）。

## Stage 8 — 格式化 + 插入

- 风格：APA 7 / IEEE / Nature / Vancouver / GB-T-7714-2015 / BibTeX。
  - APA in-text：1 作者 `(Author, Year)`；2 作者 `(A & B, Year)`；3+ `(First et al., Year)`；同作者同年 `2020a/b`；多篇 `(A, 2020; B, 2021)`。
- DOCX：**paragraph/sentence/run 级插入**，保留原有格式；不破坏表格/脚注/标题；已有引用解析 → keep/supplement/replace/flag；同文不重复引用；不重编号已有 [N]。
- LaTeX：`\cite` / `\parencite` / `\textcite` 自动适配环境；不重复已引 key。
- 参考文献：References 章节 / thebibliography / references.bib 更新，DOI 不重复。
- 编号风格按首次出现顺序；与已有引用不冲突。

## Stage 9 — 最终审计（audit_bibliography.py + audit_entailment.py + audit_pipeline.py）

- **Gate 8A 文献完整性**：文档中引用 ↔ 参考文献条目 ↔ final_papers ↔ verification_log ↔ DOI 一致。
- **Gate 8B 论断-引用蕴含**：独立评审（**绝不暴露 Stage 6 分数给评审者**），输出 PASS/WEAK/FAIL；FAIL → 不插入；WEAK → High Rigor 拒绝 / Academic Standard 标记或替换。
- 证据链完整性：7 个产物（claims / search_log / evidence_log / verification_log / support_log / final_papers / audit_report）齐全且内部一致。
- `audit_report.json` 总判定：PASS（交付）/ WEAK（仅限标记交付）/ FAIL（拒绝交付）。

---

## 数据产物（output/ 目录）

| 文件 | 内容 |
|---|---|
| claims.jsonl | Stage 1 提取的论断 |
| search_log.jsonl | 全部检索请求+结果事件 |
| evidence_log.jsonl | 证据获取记录 |
| verification_log.jsonl | 论文真实性验证记录 |
| support_log.jsonl | 支撑度评分记录 |
| final_papers.json | 最终选定论文 + links |
| audit_report.json | 最终审计报告 |
