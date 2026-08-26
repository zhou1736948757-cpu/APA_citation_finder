# APA_citation_finder — 错误处理（error-handling）

> 原则：任何源/步骤失败 → 记录 warning → 降级继续；绝不让可选故障阻断核心流。
> 唯一硬失败：最终审计 FAIL（拒绝交付）。

| 场景 | 处理 | 结果 |
|---|---|---|
| Crossref 超时/5xx | 重试 2 次（退避 2s/5s）后放弃该请求 | 降级为双源交叉验证 |
| OpenAlex 限流（429） | 退避重试（尊重 Retry-After） | 该源暂停，其他源继续 |
| Semantic Scholar 429 | 退避 ≥1s 重试；连续 3 次失败 | 该源跳过，记 warning |
| DOI 缺失 | 走双源交叉验证 → LIKELY_REAL/UNVERIFIED | UNVERIFIED → 拒绝 |
| 摘要缺失 | 按 OpenAlex → S2 → arXiv 顺序补取 | 全失败 → METADATA_ONLY（封顶 0.74） |
| Google CAPTCHA/限速 | scholarly 重试窗口 20–60s；仍失败则放弃 | Google 源跳过（可选源） |
| Exa key 缺失/未安装 | 懒加载抛 RuntimeError → 捕获记 warning | 返回 []，核心流不变 |
| DOCX 被锁定/损坏 | python-docx 打开失败 | 报错退出（不可降级的输入错误） |
| 已有重复引用 | find_existing_citation_spans 检测 | keep/supplement/flag 策略 |
| 参考文献重复 | DOI + 标题去重 | 只保留一条 |
| BibTeX 损坏 | 仅追加模式（不重写整文件）；解析失败记 warning | 保留原文件 |
| LaTeX 解析失败 | 只按 section/sentence 定位；定位失败 | 该项 skip + 报告 |
| 证据矛盾 | LLM CONTRADICTORY | 论文不入选 + 报告列出 |
| 无证据/无足够支撑 | NO SUFFICIENT EVIDENCE FOUND | 三选项（见 support-grading.md） |
| LLM 评分不可用 | 启发式回退（scoring_method=heuristic 记录） | 流程继续 |
| 网络整体不可用 | 三源全失败 | 明确报错；绝不静默给空结果当"没找到" |

## 审计失败处置
- **Gate 8A FAIL**（文献完整性）→ 阻断交付；列出 findings 修复后重跑。
- **Gate 8B FAIL**（蕴含失败）→ 对应引用**必须移除**，重新审计。
- **Gate 8B WEAK** → High Rigor 拒绝；Academic Standard 标记或替换后再审计。
- 审计可操作性错误（文件缺失）→ exit 3，报告缺什么。
