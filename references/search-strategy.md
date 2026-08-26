# APA_citation_finder — 检索策略（search-strategy）

## 源角色（core 3，免费无 key）

| 源 | 角色 | API | 限速 |
|---|---|---|---|
| **OpenAlex** | 语义发现（标题/摘要检索，文献计量） | api.openalex.org | ~10 rps（推荐 mailto 礼貌池） |
| **Semantic Scholar** | 发现 + 摘要（S2 摘要质量高） | api.semanticscholar.org/graph/v1 | 1 rps（429 退避） |
| **Crossref** | **DOI/元数据权威 + 真实性验证第一站** | api.crossref.org/works | 礼貌池（+mailto） |

> Crossref 不是主要语义检索引擎——它是验证引擎。发现交给 OpenAlex + S2。

## 可选源（默认关，懒加载）

| 源 | 角色 | 依赖 | 备注 |
|---|---|---|---|
| Exa | 网络/难以找到的内容 | exa-py + EXA_API_KEY | 语义 web 发现 |
| Google Scholar | 兜底（脆弱） | scholarly | CAPTCHA/限速/代理；**默认关** |
| 本地文件 | 用户提供论文优先 | PyMuPDF（可选） | "优先使用我提供的论文" |

## 多查询生成（generate_queries.py）

每条 claim（normalized）生成：
1. **precise** — 完整断言（保持核心术语顺序）
2. **broad** — 去掉修饰词、保留主干概念
3. **synonym** — 同义词替换（_SYNONYM_MAP，如 LLM↔large language model↔生成式 AI）
4. **domain** — 追加领域限定词（如 "in education" / "in medical imaging"）

类型附加：
- THEORETICAL/FOUNDATIONAL → `authoritative`（原理论文名/作者）、`foundational`（最早出处）
- METHOD → `method`（方法名 + 应用领域）

规则：
- 查询 ≤ 30 词；中文论断内部翻译为英文查询（原文保留在 claim 中）。
- **查询 ≠ 论断**：绝不把整段论断当查询（召回差 + 污染评分）。
- 每条查询 × 每源结果去重后合并；`search_log.jsonl` 记录 query 与来源。

## 检索循环

1. 每 claim 并行跑核心 3 源（ThreadPoolExecutor）。
2. 可选源按配置（exa / google_scholar / local）追加；任一个失败只记 warning，不中断。
3. 结果统一 schema（data-schema.md §2）→ deduplicate.py → 黑名单过滤 → tier/recency 富化。
4. 每 claim 写 `claim_<claim_id>.json`；全部写 `search_log.jsonl`。

## 已知限制
- Google Scholar 无官方 API：重试窗口 20–60s，连续失败自动放弃（错误表见 error-handling.md）。
- S2 限 1 rps：批量检索时长可接受（每 claim ≤5 查询 × 1s）。
- Crossref 搜索偶发超时：重试 2 次，退避 2s/5s。
