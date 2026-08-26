# APA_citation_finder — 反幻觉（anti-hallucination）

## 12 条 IRON RULES

1. **绝不编造论文/DOI/作者**——每篇论文必须有真实来源 API 记录。
2. **绝不只凭标题相关性给引用**——标题相关 ≠ 支撑论断。
3. **真实论文 ≠ 论断支撑**——Stage 4（真实性）与 Stage 6（支撑度）永不合并。
4. **证据不足绝不硬塞引用**——输出 NO SUFFICIENT EVIDENCE FOUND + 选项。
5. **验证先于支撑评分**（Stage 4 → Stage 6 顺序不可交换）。
6. **支撑评分先于排名**（Stage 6 → Stage 7）。
7. **排名永不拯救未过支撑阈值的论文**。
8. **基础性论断优先引用原始出处**（FOUNDATIONAL/DEFINITION profile）。
9. **不静默改写不支持的论断**——改写须授权并记录。
10. **每条插入的引用可回溯证据链**。
11. **最终审计（Gate 8A + 8B）是文档插入的强制关卡**——FAIL 拒绝交付。
12. **证据文本只来自真实获取内容**，模型永不生成引文。

## 证据链（机器可查）

```
claims.jsonl ──→ search_log.jsonl ──→ evidence_log.jsonl
     │                                       │
     └──→ verification_log.jsonl ←── evidence_level
                 │
                 └──→ support_log.jsonl ──→ final_papers.json ──→ audit_report.json
```

任何环节缺失/不一致 → 审计 FAIL。

## 具体防线

| 幻觉场景 | 防线 |
|---|---|
| 编造 DOI | DOI 必须来自 API 响应；format 层只格式化已有字段 |
| 编造摘要/证据 | evidence_text 只取 API 返回内容；FULL_TEXT/ABSTRACT/SUMMARY 分级记录 |
| 标题相关即引用 | Stage 6 支撑评分 + 硬阈值；Gate 8B 独立评审 |
| DOI 与元数据错配 | Stage 4 CONFLICT 判定 + 第二来源 |
| 证据不足硬引用 | NO SUFFICIENT EVIDENCE FOUND 路径 + 选项 |
| 重复/倾倒引用 | 每 claim 数量上限；参考文献去重 |
| 未知年份/作者 | 格式层输出 n.d. / Unknown，绝不猜测 |
| 引用已存在却重插 | docx/latex 插入前已有引用检测（keep/supplement/flag） |

## Gate 8B 防确认偏误
评审者**看不到 Stage 6 的 support_score/support_level**——只给 claim 原文 + 证据文本，
独立判定 PASS/WEAK/FAIL（audit_entailment.py 强制剥离评分字段）。
