# APA_citation_finder

**Claim → Evidence → Verification → Citation → Insertion → Audit**
学术引用的完整证据管线：论断提取 → 多源检索 → 论文真实性验证（硬闸门）→ 论断-证据
支撑度评估 → 排名 → 格式化插入 → 最终审计。替代并融合 `scipilot-cite-skill` 与
`citation-finder`（原技能已备份至 `/Users/mac/skills/_backup/`）。

## 结构

```
APA_citation_finder/
├── SKILL.md                  # 技能入口（9 阶段工作流 + IRON RULES）
├── requirements.txt           # 核心依赖 + 可选依赖说明
├── migration_inventory.md     # 双旧技能逐组件审计清单
├── scripts/                   # 28 个可执行脚本 + utils/ 包
├── references/                # 12 份规范文档
├── assets/format_templates/   # 5 种引用格式模板
├── data/                      # priority_journals.csv / blacklist_journals.csv
├── tests/                     # unit / integration / fixtures / regression
├── output/                    # 运行产物（证据链）
└── .venv/                     # 虚拟环境（requests, python-docx, python-Levenshtein）
```

## 快速开始

```bash
cd /Users/mac/skills/APA_citation_finder/scripts

# Stage 1: 提取论断
python extract_claims.py --input ../output/paper.docx --output ../output/claims.jsonl
python classify_claims.py --input ../output/claims.jsonl --output ../output/claims.jsonl
python detect_citation_need.py --input ../output/claims.jsonl --output ../output/claims.jsonl
python normalize_claim.py --input ../output/claims.jsonl --output ../output/claims.jsonl
python generate_queries.py --input ../output/claims.jsonl --output-dir ../output

# Stage 2–3: 检索 + 去重
python search_all.py --claim-json ../output/claim_C001.json --output-dir ../output --email you@example.org

# Stage 4–6: 验证 → 证据 → 支撑评分
python verify_papers.py ../output/candidates.json --log ../output/verification_log.jsonl -o ../output/verified.json
python fetch_evidence.py ../output/verified.json -o ../output/evidenced.json
python score_support.py --claim "..." --claim-id C001 --papers ../output/evidenced.json -o ../output/scored_C001.json

# Stage 7–9: 排名 → 格式化/插入 → 审计
python rank_candidates.py --claims ../output/claims.json --candidates-dir ../output -o ../output/final_papers.json
python insert_docx.py paper.docx plan.json --output paper_cited.docx
python update_references.py --mode docx --papers ../output/final_papers.json --style apa --docx paper_cited.docx
python audit_pipeline.py ../output --docx paper_cited.docx -o ../output/audit_report.json
```

## 安装 Publish-or-Perish CLI（可选源）

`tools/pop8query` 二进制（8.1MB）**不随仓库分发**（Harzing EULA 限个人非商业用途）。
启用该源：

```bash
# macOS（arm64/x86_64）：下载官方 CLI 工具包并解包
curl -L -o /tmp/pop8mactools.pkg https://harzing.com/download/pop8mactools.pkg
cd /tmp && xar -xf pop8mactools.pkg && gzip -dc Payload | cpio -id
# 把解出的 pop8query / pop8metrics / pop8error 放入本仓库 tools/ 目录
# 其他平台：https://harzing.com/resources/publish-or-perish/command-line
```

验证：`tools/pop8query --info`；`python scripts/install_optional.py --check` 应显示 `[OK] pop8query`。

## 运行测试

```bash
cd tests && ../.venv/bin/python -m unittest discover -s . -p "test_*.py"
# 99 tests OK
```

## 设计要点

- **IRON RULE 1**：真实论文 ≠ 有效引用——Stage 4 验证与 Stage 6 支撑评估是独立关卡。
- 核心 3 源免费无 key：OpenAlex / Semantic Scholar / Crossref；可选：Exa / Google Scholar /
  本地文献、Publish-or-Perish CLI（全部懒加载、默认关、失败不影响核心流）。
- 可选源一键启用：`python scripts/install_optional.py`（或 `--check` 查看状态），
  依赖清单见 `requirements-optional.txt`。
- 硬阈值：支撑度 ≥ 0.60（High Rigor ≥ 0.75），METADATA_ONLY 封顶 0.74。
- 每论断默认 1 篇引用（contested 2 / systematic 3），禁止引用倾倒。
- 每条插入引用可回溯证据链（7 个 JSONL/JSON 产物）。
- 最终审计 Gate 8A（文献完整性）+ Gate 8B（蕴含独立评审）强制通过才交付。

## 测试

```bash
cd /Users/mac/skills/APA_citation_finder/tests
.venv/bin/python -m pytest unit/ -q        # 单元测试（无网络）
.venv/bin/python -m pytest integration/ -q # 集成测试（需网络/API）
```

## 许可证 / 来源

融合自 [Haojae/scipilot-cite-skill](https://github.com/Haojae/scipilot-cite-skill) 与
[HuiyuLi-2000/citation-finder](https://github.com/HuiyuLi-2000/citation-finder)
（原仓库见备份 `_backup/`），按用户 80 节规格重构。数据源 API 各自版权归其所有者。
