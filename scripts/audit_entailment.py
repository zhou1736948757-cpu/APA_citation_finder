"""APA_citation_finder :: audit_entailment.py
Gate 8B — Claim–Citation Entailment Audit (independent reviewer pass).

SPEC RULES (§47/§74):
  * The reviewer NEVER sees Stage 6 support_score / support_level — only the
    claim text and the retrieved evidence text. This prevents confirmation
    bias ("already scored 0.85 → pass").
  * Verdict per claim-paper pair: PASS | WEAK | FAIL
        FAIL → the citation must NOT be inserted
        WEAK → reject under High Rigor; flag-or-replace under Academic Standard
  * output: audit_entailment.json with per-link verdicts + reasons.

Engine: LLM (OpenAI-compatible, .env config) with deterministic fallback.
Exit codes: 0 = all PASS, 2 = FAIL/WEAK present (caller decides policy).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from utils.jsonl import read_claims, load_json, write_json

SKILL_DIR = Path(__file__).resolve().parent.parent

REVIEW_PROMPT = """\
You are an independent academic citation reviewer. Decide whether the EVIDENCE
below actually supports the CLAIM.

Rules:
- Title-only relevance is NOT support. The evidence must say something about
  the claim's core assertion.
- If the evidence contradicts the claim → FAIL.
- If the evidence is about the same topic but does not substantiate the
  specific assertion → WEAK.
- If the evidence directly substantiates the assertion (population, variables,
  finding, direction) → PASS.
- If there is no real evidence text → FAIL.

Respond with ONLY JSON:
{"verdict": "PASS|WEAK|FAIL", "reason": "one sentence"}"""


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


def _llm_verdict(claim: str, evidence_text: str) -> dict | None:
    _load_dotenv()
    if os.getenv("USE_LLM_SUPPORT", "false").lower() not in ("true", "1", "yes"):
        return None
    key = os.getenv("LLM_API_KEY", "").strip()
    endpoint = os.getenv("LLM_API_ENDPOINT", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    if not (key and endpoint and model):
        return None
    try:
        from utils.http import rate_limited_request
        resp = rate_limited_request(
            endpoint.rstrip("/") + "/chat/completions",
            method="POST",
            json_body={
                "model": model,
                "messages": [
                    {"role": "system", "content": REVIEW_PROMPT},
                    {"role": "user", "content": f"Claim: {claim}\n\nEvidence:\n{evidence_text[:2000]}"},
                ],
                "temperature": 0.1,
                "max_tokens": 128,
            },
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            min_interval=0.5,
            timeout=60,
        )
        if not resp:
            return None
        content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
        m = re.search(r"\{.*\}", content or "", re.S)
        if not m:
            return None
        data = json.loads(m.group())
        verdict = str(data.get("verdict", "WEAK")).upper()
        if verdict not in ("PASS", "WEAK", "FAIL"):
            verdict = "WEAK"
        return {"verdict": verdict, "reason": str(data.get("reason", ""))}
    except Exception:
        return None


def _heuristic_verdict(claim: str, evidence_text: str) -> dict:
    """Deterministic fallback: keyword overlap of claim vs evidence."""
    from utils.text import keyword_overlap
    if not evidence_text or len(evidence_text.strip()) < 40:
        return {"verdict": "FAIL",
                "reason": "no usable evidence text to review"}
    score = keyword_overlap(claim, evidence_text)
    if score >= 0.30:
        return {"verdict": "PASS", "reason": f"heuristic overlap {score:.2f}"}
    if score >= 0.15:
        return {"verdict": "WEAK", "reason": f"heuristic overlap {score:.2f} — weak topical link"}
    return {"verdict": "FAIL", "reason": f"heuristic overlap {score:.2f} — no substantive link"}


def audit_links(claims: list[dict], links: list[dict], papers: list[dict],
                dry_run_llm: bool = False) -> dict:
    """Review each claim-paper link WITHOUT exposing support scores.

    links may carry evidence_text; papers provide it if missing.
    """
    paper_by_id = {p.get("paper_id") or _pid(p): p for p in papers}
    claim_by_id = {c.get("claim_id"): c for c in claims}

    reviewed = []
    for link in links:
        claim = claim_by_id.get(link.get("claim_id"), {})
        claim_text = claim.get("original_text") or claim.get("normalized_claim") or ""
        paper = paper_by_id.get(link.get("paper_id")) or {}
        evidence = link.get("evidence_text") or paper.get("evidence_text") or paper.get("abstract") or ""
        # strip any prior scoring fields — reviewer must judge independently
        clean_link = {k: v for k, v in link.items()
                      if k not in ("support_score", "support_level")}

        verdict = None
        method = "llm"
        if not dry_run_llm:
            verdict = _llm_verdict(claim_text, evidence)
        if not verdict:
            verdict = _heuristic_verdict(claim_text, evidence)
            method = "heuristic"
        reviewed.append({
            **clean_link,
            "claim_text": claim_text[:500],
            "entailment_verdict": verdict["verdict"],
            "entailment_reason": verdict["reason"],
            "review_method": method,
        })

    passes = [r for r in reviewed if r["entailment_verdict"] == "PASS"]
    weaks = [r for r in reviewed if r["entailment_verdict"] == "WEAK"]
    fails = [r for r in reviewed if r["entailment_verdict"] == "FAIL"]
    return {"overall": "FAIL" if fails else ("WEAK" if weaks else "PASS"),
            "counts": {"PASS": len(passes), "WEAK": len(weaks), "FAIL": len(fails)},
            "links": reviewed,
            "policy": {
                "FAIL": "citation must NOT be inserted",
                "WEAK": "reject under High Rigor; flag-or-replace under Academic Standard",
            },
        }


def _pid(p: dict) -> str:
    from utils.ids import paper_id_hash
    return paper_id_hash(p)


def _cli() -> int:
    p = argparse.ArgumentParser(description="Gate 8B claim-citation entailment audit")
    p.add_argument("--claims", required=True, help="claims.json")
    p.add_argument("--links", required=True, help="final_papers links JSON "
                                                  "(support scores are stripped)")
    p.add_argument("--papers", default=None, help="papers JSON (for evidence fallback)")
    p.add_argument("--no-llm", action="store_true", help="heuristic review only")
    p.add_argument("--report", "-o", default="audit_entailment.json")
    args = p.parse_args()

    claims = read_claims(args.claims)
    if isinstance(claims, dict):
        claims = claims.get("claims", [])
    data = load_json(args.links)
    if isinstance(data, dict) and "links" in data:
        links = data["links"]
    elif isinstance(data, list):
        links = data
    else:
        links = []
    papers = []
    if args.papers:
        papers_data = load_json(args.papers)
        papers = papers_data.get("papers", []) if isinstance(papers_data, dict) else papers_data

    report = audit_links(claims, links, papers, dry_run_llm=args.no_llm)
    write_json(args.report, report)
    print(json.dumps({k: report[k] for k in ("overall", "counts", "policy")},
                     ensure_ascii=False, indent=2))
    return 0 if report["overall"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(_cli())
