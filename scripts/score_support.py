"""APA_citation_finder :: score_support.py
Stage 6 — Claim–Evidence support evaluation.

Outputs per (claim, paper):
    support_score: 0.0–1.0
    support_level: DIRECT | PARTIAL | BACKGROUND | CONTRADICTORY | INSUFFICIENT_EVIDENCE

Rubric (spec §24):
    0.90–1.00  DIRECT       — population/variable/relationship/conclusion match
    0.75–0.89  DIRECT(weak) — clear support with population/context/word-strength differences
    0.60–0.74  PARTIAL      — supports only part of the claim
    0.30–0.59  BACKGROUND   — domain background only, not a primary citation
    0.00–0.29  not supported / CONTRADICTORY

Hard thresholds:
    default support < 0.60 → NOT a citation for this claim
    High Rigor support < 0.75 → reject

Evidence caps:
    METADATA_ONLY → max PARTIAL (0.74) unless the claim is itself about
    publication metadata ("this paper was published in 2025").

Engines (in priority order):
  1. LLM API (OpenAI-compatible, .env: USE_LLM_SUPPORT/LLM_API_KEY/LLM_API_ENDPOINT/LLM_MODEL)
  2. Semantic judging — the main conversation model reads the evidence and
     judges directly (any harness; no key, no subagent/tool mechanism).
     Optional helpers: --agent-judge (write pending list + judging
     instruction) and --apply-judgments (merge verdicts back).
  3. Deterministic keyword-overlap + negation fallback when no judge is available.
Writes support_log.jsonl (one record per claim-paper pair).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from utils.http import rate_limited_request
from utils.ids import paper_id_hash
from utils.jsonl import append_jsonl, load_json, write_json, utc_now_iso
from utils.text import keyword_overlap

SKILL_DIR = Path(__file__).resolve().parent.parent

SYSTEM_PROMPT = """\
You are an academic citation support evaluator. Given a research claim and a
paper's title, authors, year, venue and EVIDENCE TEXT (abstract or full-text
passage), decide how well the paper supports the claim.

Judge carefully:
- A REAL paper that is merely topically related does NOT support the claim.
- If the paper contradicts the claim, output CONTRADICTORY.
- If there is no abstract/evidence, do not guess — INSUFFICIENT_EVIDENCE.
- Wording strength matters: a paper finding "may improve" does not directly
  support "significantly improves".

Score bands:
0.90-1.00 DIRECT       paper directly validates the claim's core assertion
0.75-0.89 DIRECT       clear support with minor population/context/wording gaps
0.60-0.74 PARTIAL      supports only part of the claim
0.30-0.59 BACKGROUND   domain background only
0.00-0.29 CONTRADICTORY or unsupported

Respond with ONLY JSON:
{"support_score": 0.0-1.0, "support_level": "DIRECT|PARTIAL|BACKGROUND|CONTRADICTORY|INSUFFICIENT_EVIDENCE", "reasoning": "one sentence"}\
"""


def _load_dotenv() -> None:
    env_path = SKILL_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _config() -> dict:
    _load_dotenv()
    return {
        "use_llm": os.getenv("USE_LLM_SUPPORT", "false").lower() in ("true", "1", "yes"),
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "endpoint": os.getenv("LLM_API_ENDPOINT", "").strip(),
        "model": os.getenv("LLM_MODEL", "").strip(),
    }


def level_from_score(score: float) -> str:
    if score >= 0.90:
        return "DIRECT"
    if score >= 0.75:
        return "DIRECT"
    if score >= 0.60:
        return "PARTIAL"
    if score >= 0.30:
        return "BACKGROUND"
    return "INSUFFICIENT_EVIDENCE"


def cap_metadata_only(score: float, claim_text: str) -> float:
    """METADATA_ONLY evidence cannot justify strong support (cap at PARTIAL)."""
    if re.search(r"\b(published|released|appeared|reported) in (19|20)\d{2}\b",
                 claim_text, re.I):
        return score  # claim itself is about publication metadata
    return min(score, 0.74)


def evaluate_llm(claim: str, paper: dict, cfg: dict) -> dict:
    if not cfg.get("use_llm") or not all(cfg.get(k) for k in ("api_key", "endpoint", "model")):
        return {"available": False}
    evidence = (paper.get("evidence_text") or paper.get("abstract") or "")[:2000]
    user = (
        f"Claim: {claim}\n\n"
        f"Paper Title: {paper.get('title', '')}\n"
        f"Authors: {', '.join((paper.get('authors') or [])[:5])}\n"
        f"Year: {paper.get('year')}\n"
        f"Venue: {paper.get('venue', '')}\n"
        f"Evidence ({paper.get('evidence_level', '?')}):\n"
        f"{evidence or '[no abstract available]'}"
    )
    try:
        resp = rate_limited_request(
            cfg["endpoint"].rstrip("/") + "/chat/completions",
            method="POST",
            json_body={
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": 256,
            },
            headers={"Authorization": f"Bearer {cfg['api_key']}",
                     "Content-Type": "application/json"},
            min_interval=0.5,
            timeout=60,
        )
        if not resp:
            return {"available": False}
        content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
        m = re.search(r"\{.*\}", content or "", re.S)
        if not m:
            return {"available": False}
        data = json_loads(m.group())
        score = max(0.0, min(1.0, float(data.get("support_score", 0.2))))
        level = str(data.get("support_level") or level_from_score(score)).upper()
        return {"available": True, "support_score": round(score, 2),
                "support_level": level,
                "support_reasoning": str(data.get("reasoning", ""))}
    except Exception as e:
        return {"available": False, "error": str(e)}


def json_loads(s: str) -> dict:
    import json
    return json.loads(s)


_NEGATION_RE = re.compile(
    r"\b(does not|do not|did not|no (significant )?(effect|impact|improvement|benefit|"
    r"association|relationship|difference)|fails? to|without (any )?(effect|impact)|"
    r"not (improve|reduce|increase|affect|support)|contradict|refute|undermine|"
    r"challenge (the|this))\b",
    re.I,
)

_POSITIVE_ASSERT_RE = re.compile(
    r"\b(improve|improves|enhance|enhances|increase|increases|reduce|reduces|affect|"
    r"supports?|is (associated with|linked to)|leads? to|predicts?|explains?|"
    r"significantly)\b",
    re.I,
)


def _detect_contradiction(claim: str, abstract: str) -> bool:
    """True when the claim asserts a positive effect and the abstract negates it."""
    claim_positive = bool(_POSITIVE_ASSERT_RE.search(claim or ""))
    evidence_negative = bool(_NEGATION_RE.search(abstract or ""))
    return claim_positive and evidence_negative


def evaluate_heuristic(claim: str, paper: dict) -> dict:
    """Deterministic fallback: overlap-minus-negation of claim vs abstract/title."""
    abstract = paper.get("evidence_text") or paper.get("abstract") or ""
    title = paper.get("title") or ""
    evidence_level = paper.get("evidence_level") or ("ABSTRACT" if abstract else "METADATA_ONLY")

    if not abstract and evidence_level == "METADATA_ONLY":
        return {"support_score": round(keyword_overlap(claim, title) * 0.5, 2),
                "support_level": "INSUFFICIENT_EVIDENCE",
                "support_reasoning": "metadata-only: no abstract available"}

    if _detect_contradiction(claim, abstract):
        return {"support_score": 0.10, "support_level": "CONTRADICTORY",
                "support_reasoning": "heuristic: abstract negates the claim's assertion"}

    a = keyword_overlap(claim, abstract)
    t = keyword_overlap(claim, title)
    score = min(1.0, a * 0.75 + t * 0.25)
    if score < 0.30:
        score = min(score, 0.29)
    level = level_from_score(score)
    return {"support_score": round(score, 2), "support_level": level,
            "support_reasoning": "heuristic overlap fallback (no LLM configured)"}


def score_paper(claim: str, paper: dict, cfg: dict) -> dict:
    out = dict(paper)
    result = evaluate_llm(claim, paper, cfg)
    if result.get("available"):
        out["support_score"] = result["support_score"]
        out["support_level"] = result["support_level"]
        out["support_reasoning"] = result.get("support_reasoning", "")
        out["scoring_method"] = "llm"
    else:
        h = evaluate_heuristic(claim, paper)
        out["support_score"] = h["support_score"]
        out["support_level"] = h["support_level"]
        out["support_reasoning"] = h["support_reasoning"]
        out["scoring_method"] = "heuristic"

    # evidence-level cap: METADATA_ONLY can never justify DIRECT support, so
    # the level is re-derived from the capped score (cap and level stay in sync)
    if paper.get("evidence_level") == "METADATA_ONLY":
        capped = round(cap_metadata(claim, out["support_score"]), 2)
        if capped != out["support_score"]:
            out["support_score"] = capped
            out["support_level"] = level_from_score(capped)
            out["support_reasoning"] = (
                (out.get("support_reasoning") or "") + " [capped: METADATA_ONLY]")
    return out


def cap_metadata(claim: str, score: float) -> float:
    return cap_metadata_only(score, claim)


def score_papers(claim: str, papers: list[dict], delay: float = 0.3,
                 log_path: str | None = "support_log.jsonl",
                 claim_id: str = "") -> list[dict]:
    cfg = _config()
    out = []
    for i, p in enumerate(papers):
        r = score_paper(claim, p, cfg)
        out.append(r)
        if log_path:
            append_jsonl(log_path, {
                "timestamp": utc_now_iso(),
                "event": "support_score",
                "claim_id": claim_id,
                "paper_id": paper_id_hash(r),
                "title": r.get("title"),
                "doi": r.get("doi"),
                "support_score": r.get("support_score"),
                "support_level": r.get("support_level"),
                "evidence_level": r.get("evidence_level"),
                "scoring_method": r.get("scoring_method"),
                "reasoning": r.get("support_reasoning"),
            })
        if i < len(papers) - 1:
            time.sleep(delay)
    return out


AGENT_JUDGE_PROMPT = """You are an independent academic citation support evaluator, running as a
subagent of the main conversation (same model, same reasoning depth).

TASK: For EACH item in the attached judgments JSON, decide how well the
paper's EVIDENCE supports the CLAIM. Read the evidence text carefully; if
an item has an "evidence_path", open and read that file (PDF/text) for the
full text before judging.

RULES (non-negotiable):
- Judge ONLY from the provided evidence. Never invent or guess content.
- A real paper that is merely topically related does NOT support the claim.
- Evidence that contradicts the claim → CONTRADICTORY (never "partial").
- No abstract and no readable evidence → INSUFFICIENT_EVIDENCE.
- Wording strength matters: "may improve" does not support "significantly improves".
- METADATA_ONLY evidence (title/year only) can never score above 0.74.

SCORE BANDS:
0.90-1.00 DIRECT       paper directly validates the claim's core assertion
0.75-0.89 DIRECT       clear support with minor population/context/wording gaps
0.60-0.74 PARTIAL      supports only part of the claim
0.30-0.59 BACKGROUND   domain background only
0.00-0.29 CONTRADICTORY or unsupported

RESPOND WITH ONLY a JSON array (no prose, no markdown fences):
[{"paper_id": "...", "support_score": 0.0-1.0,
  "support_level": "DIRECT|PARTIAL|BACKGROUND|CONTRADICTORY|INSUFFICIENT_EVIDENCE",
  "reasoning": "one sentence citing the evidence"}]
"""


def prepare_agent_judgments(claim: str, papers: list[dict],
                            out_dir: str | Path = ".") -> dict:
    """Stage 6 semantic mode, optional helper: write the pending-judgment
    list plus a ready-to-use judging instruction. The main conversation
    model judges directly (any harness — no subagent/tool mechanism
    required) and writes verdicts back via apply_agent_judgments."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for p in papers:
        items.append({
            "paper_id": paper_id_hash(p),
            "title": p.get("title"),
            "authors": (p.get("authors") or [])[:5],
            "year": p.get("year"),
            "venue": p.get("venue"),
            "doi": p.get("doi"),
            "evidence_level": p.get("evidence_level", "?"),
            "evidence_text": (p.get("evidence_text") or p.get("abstract") or "")[:2000],
            "evidence_path": p.get("evidence_path"),
        })
    jpath = out_dir / "pending_judgments.json"
    write_json(str(jpath), {"claim": claim, "items": items})
    ppath = out_dir / "agent_judge_prompt.md"
    ppath.write_text(
        AGENT_JUDGE_PROMPT
        + f"\n\nCLAIM: {claim}\n\n"
        + f"JUDGMENTS JSON (read {jpath.name} in the same directory):\n"
        + "```json\n" + json.dumps({"claim": claim, "items": items},
                                    ensure_ascii=False, indent=1) + "\n```\n",
        encoding="utf-8")
    return {"pending": str(jpath), "prompt": str(ppath), "count": len(items)}


def apply_agent_judgments(claim: str, papers: list[dict], judgments: list[dict],
                          log_path: str | None = "support_log.jsonl",
                          claim_id: str = "") -> list[dict]:
    """Stage 6 semantic mode, step 2: merge the main model's JSON verdicts
    back into the papers (same caps as the LLM engine: METADATA_ONLY ≤ 0.74,
    level re-derived from the capped score). Verdicts may come from the
    main conversation model directly, a subagent, or any other judge."""
    by_id = {}
    for j in judgments or []:
        pid = j.get("paper_id")
        if pid:
            by_id[pid] = j
    out = []
    for p in papers:
        r = dict(p)
        j = by_id.get(paper_id_hash(p))
        if j:
            score = max(0.0, min(1.0, float(j.get("support_score", 0.2))))
            r["support_score"] = round(score, 2)
            r["support_level"] = str(j.get("support_level") or
                                     level_from_score(score)).upper()
            r["support_reasoning"] = str(j.get("reasoning", ""))
            r["scoring_method"] = "agent_llm"
        else:
            h = evaluate_heuristic(claim, p)
            r["support_score"] = h["support_score"]
            r["support_level"] = h["support_level"]
            r["support_reasoning"] = h["support_reasoning"]
            r["scoring_method"] = "heuristic"
        # METADATA_ONLY cap (same as score_paper)
        if p.get("evidence_level") == "METADATA_ONLY":
            capped = round(cap_metadata(claim, r["support_score"]), 2)
            if capped != r["support_score"]:
                r["support_score"] = capped
                r["support_level"] = level_from_score(capped)
                r["support_reasoning"] = (
                    (r.get("support_reasoning") or "") + " [capped: METADATA_ONLY]")
        out.append(r)
        if log_path:
            append_jsonl(log_path, {
                "timestamp": utc_now_iso(),
                "event": "support_score",
                "claim_id": claim_id,
                "paper_id": paper_id_hash(r),
                "title": r.get("title"),
                "doi": r.get("doi"),
                "support_score": r.get("support_score"),
                "support_level": r.get("support_level"),
                "evidence_level": r.get("evidence_level"),
                "scoring_method": r.get("scoring_method"),
                "reasoning": r.get("support_reasoning"),
            })
    return out


def render_support_report_md(claim: str, scored: list[dict],
                             claim_id: str = "", threshold: float = 0.60,
                             high_rigor: bool = False,
                             out_path: str | Path = "support_report.md") -> str:
    """Render the Stage 6 verdicts as a detailed, fixed-format Markdown
    report. Same format whether the judge was the LLM API, the main
    conversation model (semantic mode) or the heuristic fallback — the
    report is the machine-checkable human record of the support gate."""
    lines: list[str] = []
    A = lines.append
    A(f"# 支撑度评估报告 — {claim_id or 'claim'}")
    A("")
    A("## 论断")
    A("")
    A(f"> {claim}")
    A("")
    A(f"- 评估时间: {utc_now_iso()}")
    A(f"- 硬阈值: {threshold:.2f}" + ("（High Rigor）" if high_rigor else ""))
    A("")
    A("## 判定汇总")
    A("")
    A("| # | 论文 | 年份 | 证据级别 | 分数 | 级别 | 结论 |")
    A("|---|------|------|----------|------|------|------|")
    passed, rejected, contrad, insuff = [], [], [], []
    for i, p in enumerate(scored, 1):
        score = p.get("support_score") or 0.0
        level = p.get("support_level") or ""
        title = (p.get("title") or "")[:60]
        ev = p.get("evidence_level") or "?"
        if level == "CONTRADICTORY":
            verdict, bucket = "⚠️ 矛盾（永不引用）", contrad
        elif level == "INSUFFICIENT_EVIDENCE":
            verdict, bucket = "❌ 证据不足", insuff
        elif score >= threshold:
            verdict, bucket = "✅ 可引用", passed
        else:
            verdict, bucket = "❌ 低于阈值", rejected
        bucket.append(p)
        A(f"| {i} | {title} | {p.get('year') or '?'} | {ev} | "
          f"{score:.2f} | {level} | {verdict} |")
    A("")
    A(f"- 通过（≥{threshold:.2f}）: **{len(passed)}** 篇")
    A(f"- 拒绝: {len(rejected)} 篇（低于阈值）")
    A(f"- 矛盾证据: **{len(contrad)}** 篇（显式标注，永不引用）")
    A(f"- 证据不足: {len(insuff)} 篇")
    A("")
    A("## 逐篇判定")
    A("")
    for i, p in enumerate(scored, 1):
        score = p.get("support_score") or 0.0
        level = p.get("support_level") or ""
        A(f"### {i}. {p.get('title') or '(untitled)'}（{p.get('year') or '?'}）")
        A("")
        A(f"- **元数据**: {', '.join((p.get('authors') or [])[:5])} · "
          f"{p.get('venue') or '?'} · DOI: {p.get('doi') or '—'}")
        A(f"- **证据级别**: {p.get('evidence_level') or '?'}"
          + (f"（来源: {p.get('evidence_source') or '?'}）"
             if p.get('evidence_source') else ""))
        ev_text = (p.get("evidence_text") or p.get("abstract") or "").strip()
        if ev_text:
            A(f"- **证据摘录**（真实获取原文，前 300 字）:")
            A("")
            A(f"  > {ev_text[:300]}")
            A("")
        A(f"- **判定**: **{score:.2f} {level}**"
          + (f"（评分引擎: {p.get('scoring_method') or '?'}）" if p.get("scoring_method") else ""))
        A(f"- **理由**: {p.get('support_reasoning') or '—'}")
        if level == "CONTRADICTORY":
            A("- **结论**: ⚠️ **矛盾证据——永不引用**（即使分数被高估也由硬门禁排除）")
        elif level == "INSUFFICIENT_EVIDENCE":
            A("- **结论**: ❌ 证据不足——不引用；如需支撑请补充证据或弱化论断（需授权）")
        elif score >= threshold:
            A(f"- **结论**: ✅ 可引用（≥{threshold:.2f}）")
        else:
            A(f"- **结论**: ❌ 低于阈值 {threshold:.2f}——不引用")
        A("")
    if contrad:
        A("## 矛盾证据清单（永不引用）")
        A("")
        for p in contrad:
            A(f"- **{p.get('title')}**（{p.get('year')}）: 证据称 "
              f"“{(p.get('evidence_text') or '')[:120]}…”")
        A("")
    if insuff:
        A("## 证据不足清单")
        A("")
        for p in insuff:
            A(f"- **{p.get('title')}**（{p.get('year')}）: 无可用证据文本")
        A("")
    capped = [p for p in scored
              if p.get("evidence_level") == "METADATA_ONLY"
              and (p.get("support_reasoning") or "").find("capped") >= 0]
    if capped:
        A("## 备注")
        A("")
        A("- METADATA_ONLY 上限 0.74 已应用（级别随分数重推）:")
        for p in capped:
            A(f"  - {p.get('title')} → {p.get('support_score'):.2f} {p.get('support_level')}")
        A("")
    md = "\n".join(lines)
    if out_path:
        Path(out_path).write_text(md, encoding="utf-8")
    return md


def _cli() -> int:
    p = argparse.ArgumentParser(description="Score claim-paper support")
    p.add_argument("--claim", required=True)
    p.add_argument("--claim-id", default="")
    p.add_argument("--papers", required=True, help="papers JSON (list)")
    p.add_argument("--log", default="support_log.jsonl", help="'' disables")
    p.add_argument("--output", "-o", default="scored_papers.json")
    p.add_argument("--agent-judge", action="store_true",
                   help="semantic mode helper: write pending_judgments.json + "
                        "agent_judge_prompt.md, do NOT score")
    p.add_argument("--apply-judgments", default=None,
                   help="semantic mode helper: JSON file with the judge's "
                        "verdicts (array of {paper_id, support_score, "
                        "support_level, reasoning})")
    p.add_argument("--report-md", default=None,
                   help="also render support_report.md (detailed verdict report)")
    p.add_argument("--threshold", type=float, default=0.60)
    p.add_argument("--high-rigor", action="store_true")
    args = p.parse_args()

    papers = load_json(args.papers)
    if isinstance(papers, dict) and "kept" in papers:
        papers = papers["kept"]
    if args.agent_judge:
        info = prepare_agent_judgments(args.claim, papers,
                                       out_dir=Path(args.output).parent)
        print(f"Agent-judge pending: {info['count']} items → "
              f"{info['pending']} + {info['prompt']}", file=sys.stderr)
        print("Next: judge the items directly (main model, any harness), "
              "then run --apply-judgments <verdicts.json>", file=sys.stderr)
        return 0
    if args.apply_judgments:
        judgments = load_json(args.apply_judgments)
        if isinstance(judgments, dict):
            judgments = judgments.get("judgments") or judgments.get("items") or []
        scored = apply_agent_judgments(args.claim, papers, judgments,
                                       log_path=args.log or None,
                                       claim_id=args.claim_id)
        write_json(args.output, scored)
        print(f"Applied {len(judgments)} agent verdicts → {args.output}",
              file=sys.stderr)
        return 0
    scored = score_papers(args.claim, papers, log_path=args.log or None,
                          claim_id=args.claim_id)
    write_json(args.output, scored)
    if args.report_md:
        render_support_report_md(args.claim, scored, claim_id=args.claim_id,
                                 threshold=args.threshold,
                                 high_rigor=args.high_rigor,
                                 out_path=args.report_md)
        print(f"Report → {args.report_md}", file=sys.stderr)
    print(f"Scored {len(scored)} papers → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
