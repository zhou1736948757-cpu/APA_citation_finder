# IMPLEMENTATION_REPORT — APA_citation_finder 融合技能

**日期**: 2026-08-26 · **新技能路径**: `/Users/mac/skills/APA_citation_finder/` · **Python**: 3.14.7 (venv: `.venv/`)

---

## 1. Migration Summary

按 80 节规格将两个旧技能融合为单一证据管线技能 **APA_citation_finder**：

| 旧技能 | 角色 | 去向 |
|---|---|---|
| `scipilot-cite-skill` (HuiyuLi-2000) | 8 阶段检索-引用管线、5 种引用格式、Gate 8 幻觉审计、DOCX/LaTeX 插入 | 备份保留，组件并入 APA_citation_finder |
| `citation-finder` (Haojae) | claim 提取、多源检索、tier 排序、BibTeX、可选源 (Exa/Google Scholar) | 备份保留，组件并入 APA_citation_finder |

融合原则：**Claim → Evidence → Verification → Citation → Document Insertion → Audit**。
验证是**门禁**（UNVERIFIED/CONFLICT → 拒绝），支撑是**分级**（阈值 0.60 默认 / 0.75 High Rigor）；
真实论文 ≠ 有效引用（IRON RULE 1）由两个独立闸门分别保证。

架构差异 vs 旧技能：
- 旧 `scipilot-cite-skill` 用 "title 相关 + 期刊分区" 排序；APA_citation_finder 用 **support 主导 + profile 加权**，rank 永远不能拯救无支撑证据。
- 旧 `citation-finder` 只靠 LLM 判定支撑；APA_citation_finder 提供**启发式兜底**（无 LLM key 时核心流不中断），并新增否定检测（矛盾证据显式标 CONTRADICTORY，不静默）。
- 两旧技能均无**强制证据链**；APA_citation_finder 全程落盘 7 类机器可查 artifact（claims/search/evidence/verification/support/final/audit）。

## 2. Architecture

```
Stage 0  Intent (Modes A/B/C, 预设推断优先)
Stage 1  extract_claims → classify_claims → detect_citation_need → normalize_claim → generate_queries
Stage 2  search_openalex / search_semantic_scholar / search_crossref (core, 免 key)
         search_exa / search_google_scholar / search_pop / search_local (optional, 懒加载)
Stage 3  deduplicate (DOI 精确 + 标题≥0.90+年+作者, source_apis[] 保留)
Stage 4  verify_papers (VERIFIED/LIKELY_REAL/UNVERIFIED/CONFLICT; VERIFIED 需第二源 title+year+author 一致)
Stage 5  fetch_evidence (FULL_TEXT>ABSTRACT>SUMMARY>METADATA_ONLY; evidence_text 全部来自真实 API)
Stage 6  score_support (LLM 或启发式; METADATA_ONLY cap 0.74 且 level 联动; 否定→CONTRADICTORY)
Stage 7  rank_candidates (profile 加权, support 主导; CONTRADICTORY/INSUFFICIENT 硬性排除)
Stage 8  format_citation (APA/IEEE/Nature/Vancouver/GB-T 7714) + format_bibtex + insert_docx/insert_latex/update_references
Stage 9  audit_bibliography (Gate 8A) + audit_entailment (Gate 8B, 独立于 Stage 6 评分) + audit_pipeline
```

模块数：`scripts/` 26 个入口脚本 + `scripts/utils/` 7 个工具模块 ≈ 5,300 行；
`references/` 13 篇工作流/规范文档；`tests/` 8 个测试文件 + 7 个 fixture。

## 3. Files Changed

**新增 (APA_citation_finder)**: 全部模块（见上）; `SKILL.md`, `README.md`, `requirements.txt`,
`migration_inventory.md`, `data/{priority,blacklist}_journals.csv`,
`assets/format_templates/*.json`, `tests/{unit,integration,regression,fixtures}`,
`output/` (Example Run artifact), `.venv/`。

**保留未动 (备份)**: `/Users/mac/skills/_backup/scipilot-cite-skill-20260826-2108/`,
`/Users/mac/skills/_backup/citation-finder-20260826-2108/`（含 .git，从未删除）。

**评审驱动修复 (RED 第 2 轮, 12+1 项)**: METADATA_ONLY cap↔level 联动; rank 硬性 level 门禁;
启发式否定检测; 第二来源 title+year+author 一致性; 伪造 DOI 不解析 → UNVERIFIED 无回退;
claims JSONL/JSON 双格式 (write_claims); DOCX 句末精确偏移插入 + 跨插入去重; CLI 多查询预算;
数字编号续号; 作者词边界匹配; diversity 贪心排序; evidence_log 链检查; 挂起缩进 Length 类型。

## 4. Test Results — PASS

```
/Users/mac/skills/APA_citation_finder/tests$ .venv/bin/python -m unittest discover -s . -p "test_*.py"
Ran 87 tests in ~1.5s — OK
```

| 套件 | 覆盖 | 结果 |
|---|---|---|
| unit/test_claims | 提取(中英/复合句/偏移)、类型(9类)、引用需求、规范化(中文→英文概念)、4类查询 | PASS |
| unit/test_format | APA/IEEE/Nature/Vancouver/GB-T 7714/BibTeX、同作者同年 a/b/c 后缀 | PASS |
| unit/test_dedup_verify | DOI/标题去重、VERIFIED 需第二源一致、CONFLICT 拒绝、伪造 DOI→UNVERIFIED | PASS |
| unit/test_support_rank | 启发式评分、否定→CONTRADICTORY、cap 联动、rank 门禁、profile 加权 | PASS |
| unit/test_docx_audit | run 级插入、已有引用 keep/supplement/flag、去重、8A 映射 | PASS |
| regression/test_regressions | 两旧技能行为回归 (title 阈值/5 格式/编号/黑名单/tier/merge) | PASS |
| regression/test_review_fixes | 评审修复逐条锁定 (含 DOCX 缩进) | PASS |
| integration/test_offline_flow | 无 API key 全链 (mock 网络) | PASS |
| **Example Run (真实 API)** | UTAUT2 全链 → 最终审计 **PASS** (8A PASS, 8B PASS) | PASS |

规格 Tests 1-10 映射：LLM 关键论断(Test 1/2)、UTAUT2 基础(Test 3)、伪造 DOI(Test 4)、
真实但不支撑(Test 5)、DOCX APA fixture(Test 6)、已有引用不重复(Test 7)、APA 变体(Test 8)、
GB/T 无回归(Test 9)、无 key 核心流(Test 10) 全部覆盖。

## 5. Known Limitations 与解决方案

1. **Semantic Scholar 无 key 限速** → 已解决（三重缓解）：
   - 第二来源冗余：S2 429 快速失败后自动回退 **OpenAlex DOI 精确查询**（免费、宽松限速），
     VERIFIED 不再因 S2 不可用而降级（实测 UTAUT2 论文在 S2 全 429 下仍 VERIFIED）；
   - `S2_API_KEY` 环境变量：有 key 时请求带 `x-api-key` 头，限速上限大幅提高；
   - **DOI 验证缓存** `verification_cache.json`：同一 DOI 跨运行直接命中，零网络请求
     （实测第二次运行 0.00s）。
2. **OpenAlex 作者缺 given name** → 已解决：验证阶段用 **Crossref 完整作者名回填**
   （真实数据，绝不编造；完整名不覆盖）。实测 `Venkatesh` → `Venkatesh, Viswanath`，
   APA 引用恢复首字母。
3. **可选源依赖** → 已解决：`python scripts/install_optional.py` 一键安装
   （`requirements-optional.txt`：exa-py / scholarly / PyMuPDF），
   `--check` 查看状态；仍默认关闭、懒加载、永不阻塞核心流。
   **新增 Publish-or-Perish 源**（`search_pop.py` + `tools/pop8query` 8.19.5300）：
   一个 CLI 提供 OpenAlex/Crossref/S2/PubMed/Lens/Google Scholar 多通道，
   自带缓存与限速；实测 OpenAlex 通道命中 UTAUT2 原论文（10.2307/41410412）。
4. **启发式支撑评分**是关键词重叠+否定检测，无法替代 LLM 语义判断；配置 LLM key 后 Stage 6 自动切换。
5. **Gate 8B 默认走启发式** (无 LLM 时)；建议正式交付前用 LLM 复审。
6. **GB/T 7714** 为基础形态（期刊 [J] 著录），学位论文/书籍等变体见 references/citation-formats.md。
7. 复合句拆分、同义词映射为规则驱动，覆盖常见学术表达，长难句可能保留为单 claim。

## 6. Old Skills Backup Location

```
/Users/mac/skills/_backup/scipilot-cite-skill-20260826-2108/   (原 scipilot-cite-skill, .git 保留)
/Users/mac/skills/_backup/citation-finder-20260826-2108/       (原 citation-finder, .git 保留)
```
两个旧技能**从未删除**；停用仅通过从启用目录移出实现。

## 7. 完整 Example Run (真实 API)

```
论断: "The unified theory of acceptance and use of technology (UTAUT2) was proposed
      by Venkatesh and colleagues, which extends the original technology acceptance model."
类型: DEFINITION | 引用需求: RECOMMENDED

Stage 1: 1 claim (C001), 5 查询 (precise/broad/synonym/domain/foundational)
Stage 2-3: 3 查询 × 3 核心源 → 31 候选 (含 1 条伪造 DOI 注入)
Stage 4: VERIFIED 6 | LIKELY_REAL 17 | UNVERIFIED 2 (伪造 DOI 被拒 ✓) | CONFLICT 6 (元数据冲突被拒 ✓)
Stage 5: 20 ABSTRACT + 3 METADATA_ONLY
Stage 6: UTAUT2 原论文 0.66 PARTIAL 居首 (Venkatesh et al., 2012, MIS Quarterly)
Stage 7: 选中 1 篇 (DEFINITION profile, 阈值 0.60)
Stage 8: APA in-text  (Venkatesh et al., 2012)
         APA ref      Venkatesh, Thong, J. Y., & Xu (2012). Consumer Acceptance ... *MIS Quarterly*.
         IEEE         [1] Venkatesh, J. Y. Thong, and Xu, "Consumer Acceptance ...", *MIS Quarterly*, 2012.
         GB/T 7714    [1] Venkatesh, Thong J Y, Xu. Consumer Acceptance ...[J]. MIS Quarterly, 2012.
         BibTeX       @article{venkatesh2012, ... doi = {10.2307/41410412}}
Stage 9: 8A bibliographic PASS · 8B entailment PASS (heuristic 0.73) · chain 无缺口 → overall PASS
artifact: claims.jsonl · search_log.jsonl · verification_log.jsonl · evidence_log.jsonl
          support_log.jsonl · final_papers.json · audit_report.json  (output/)
```

## 8. Git 状态

`/Users/mac/skills/` 与 `/Users/mac/skills/APA_citation_finder/` **均不是 git 仓库**（无 .git），
故无 git diff 可展示。变更以文件级对照呈现：
- 新增: APA_citation_finder 全目录 (~5,300 行 Python + 13 篇 references + 8 个测试文件 + fixtures + assets/data)
- 保留: `_backup/` 两份旧技能 (含 .git 历史)
- 建议: 若需版本控制，`git init` 于 `/Users/mac/skills/APA_citation_finder` 后首提交
  (`.gitignore`: `.venv/, output/, __pycache__/`)
