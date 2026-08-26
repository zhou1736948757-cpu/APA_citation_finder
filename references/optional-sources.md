# APA_citation_finder — 可选来源（optional-sources）

> 核心流 = OpenAlex + Semantic Scholar + Crossref（免费、无需 key）。
> 以下来源全部**默认关闭**，懒加载；任一失败只记 warning，绝不影响核心流。

## Exa（语义网络发现）
- 用途：找到正式索引之外的高质量内容（博客/技术报告/新预印本）。
- 依赖：`pip install exa-py` + `.env: EXA_API_KEY=...`
- 启用：`search_all.py --sources exa` 或 SKILL.md Stage 0 用户要求。
- 失败处理：无 key / 未安装 / 限流 → 记 warning，返回 []（error-handling.md）。

## Google Scholar（兜底，脆弱）
- 用途：核心源检索不到时的最后兜底；**默认关**。
- 依赖：`pip install scholarly`；可选代理 `SCI_CITE_GS_PROXY` 或自动 FreeProxies。
- 已知问题：CAPTCHA、速率限制、反爬；连续失败自动放弃，**绝不阻塞**。
- 结果无 DOI 居多 → 走 Stage 4 双源交叉验证（LIKELY_REAL 上限）。

## Publish or Perish（pop8query CLI，可选）
- 用途：一个二进制提供 OpenAlex / Crossref / Semantic Scholar / PubMed / Lens /
  Google Scholar 多通道；自带结果缓存与自适应限速。
- 机制：`search_pop.py --query "..." --channel openalex|gscholar|...`，
  经 `search_all.py --sources ...,pop` 接入管线；JSONL 解析为统一 schema。
- 二进制：`tools/pop8query`（macOS arm64，8.19.5300，Harzing 免费个人非商业用途）；
  其他平台下载 `pop8mactools.pkg` / `pop8tools.zip` 解包后放入 tools/ 或 PATH。
- 注意：Google Scholar 通道（--gscholar）遇 CAPTCHA 时 CLI 直接终止（无 GUI 可解），
  该通道默认不启用；OpenAlex 通道 title 字段仅支持单术语，模块自动用
  `--title <首词> --keywords <完整查询>` 组合。
- 无 pop8query → 该源跳过，核心流不变。

## 本地文件（用户提供论文，优先）
- 机制：`search_local.py --paths <文件或目录>` 扫描 PDF/DOCX/TXT/MD。
  PDF 用 PyMuPDF（可选依赖）提取标题/作者/年份；无 PyMuPDF 时退回文件名。
- 本地文件进入候选后**同走全部关卡**（验证→证据→支撑→排名）——本地文件不豁免。
- 用户说"优先使用我提供的论文"时：本地文件作为候选前置，其余流程照常。

## 依赖策略
| 依赖 | 用途 | 必须？ |
|---|---|---|
| requests / python-docx / python-Levenshtein | 核心 | ✅ |
| exa-py | Exa | 否（懒加载） |
| scholarly | Google Scholar | 否（懒加载） |
| PyMuPDF | 本地 PDF 元数据 | 否（懒加载） |
