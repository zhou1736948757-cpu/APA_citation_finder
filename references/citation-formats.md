# APA_citation_finder — 引用格式（citation-formats）

## 支持的风格（format_citation.py）

| 风格 | 正文标记 | 参考文献条目 |
|---|---|---|
| **APA 7** | (Author, Year) / (A & B, Year) / (First et al., Year) | Author, A. B., & Author, C. (Year). Title. *Venue*. https://doi.org/xxx |
| **IEEE** | [1], [2], [1], [3] | [n] A. First, B. Second, and C. Third, "Title," *Venue*, year, doi: xxx |
| **Nature** | 上标 ¹²³ | 1. Author et al. Title. *Venue* (Year). |
| **Vancouver** | [1], [2-3] | 1. Authors. Title. Venue. Year. |
| **GB/T 7714-2015** | [1] | [1] 作者. 标题[J]. 期刊, 年份. DOI: xxx |
| **BibTeX** | \cite{key} | @article{key, title, author, journal, year, doi} |

## APA 细节规则（已实现）
- 1 作者：`(Maslow, 1943)`；narrative：`Maslow (1943)`
- 2 作者：`(LeCun & Bengio, 2015)`；narrative：`LeCun and Bengio (2015)`
- 3+ 作者：`(Vaswani et al., 2017)`（引用时全部 3+ 都用 et al.）
- **同作者同年**：`(Smith, 2020a; Smith, 2020b)`——apa_year_suffixes 自动分配 a/b/c
- 多篇合并：`(A, 2020; B, 2021)` —— apa_combine_in_text
- 参考文献按首作者姓氏字母序（apa_reference_list）
- 7+ 作者参考文献条目用 `...` 省略（第 6 作者后）

## 编号风格（IEEE/Nature/Vancouver/GB-T）
- **首次出现顺序编号**（assign_citation_numbers），与已有引用合并时从已有最大编号继续。
- 绝不重编号已有 [N]。

## LaTeX 适配（insert_latex.py）
- 自动探测文档使用的命令族：`\cite` / `\parencite`（apa）/ `\textcite` / `\citet`
- 新引用沿用该命令族；`STYLE_TO_COMMAND` 提供默认映射
- 已引 key 不重复；thebibliography / \bibliography 模式由 update_references.py 处理

## 参考文献去重
- docx References 章节：DOI 与标题片段双重去重
- .bib：DOI 去重（extract_dois_from_bib）+ bibtex key 去重（key_2, key_3...）
- 同一论文无论被多少 claim 引用，参考文献只出现一次

## 模板文件
- assets/format_templates/{apa7, ieee, nature, vancouver, gb-t-7714}.json —— 格式模板占位
- 格式化输出遵循模板字段顺序；脚本内为权威实现
