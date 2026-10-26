"""Question -> evidence board, using whichever harness version is in editable/.

    python -m research.board "Does blocking H+,K+-ATPase affect planarian head regeneration?"

Stages: Frame (Wonder) decomposes the question into checkable claims and a search query;
Retrieve pulls papers; the editable claim checker verifies each claim against each abstract;
Synthesis (Wonder) writes a short cited brief from verified claims only.

This is the inner loop the outer loop improves. Running it with gen-0 and with the best
generation side by side is the demo's payoff moment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import config, llm  # noqa: E402
from core.schema import Claim  # noqa: E402
from eval.run import load_harness  # noqa: E402
from research import sources  # noqa: E402

FRAME = """You are a research planner for model-organism and materials science questions. Given a QUESTION, produce
2-4 specific, checkable claims that, if true or false, would answer it, plus one literature search query.
Respond with JSON only: {"claims": ["...", "..."], "query": "..."}"""

SYNTH = """You write a short research brief. Use ONLY the verified evidence rows provided; every sentence must cite a
row by its [id]. If evidence conflicts, say so. If evidence is insufficient, say so. End with one line naming the
single experiment that would best resolve the open question. Keep it under 180 words. This is research
exploration in model organisms, not medical advice."""


def run(question: str, editable: Path, max_papers: int = 6) -> dict:
    harness = load_harness(editable)
    f = llm.chat([{"role": "system", "content": FRAME}, {"role": "user", "content": f"QUESTION: {question}"}],
                 role="improver", json_mode=True, max_tokens=400).json()
    claims_text: list[str] = f.get("claims", [])[:4]
    papers = sources.search(f.get("query", question), n=max_papers)[:max_papers]

    claims: list[Claim] = []
    for i, ct in enumerate(claims_text):
        for p in papers:
            claims.append(Claim(id=f"q{i}-{p.id}", claim=ct, source_id=p.id, source_title=p.title,
                                source_text=p.abstract, gold_label="", split="live"))
    verdicts = harness.run_claims(claims, llm.chat)

    rows = []
    for c, v in zip(claims, verdicts):
        rows.append({"id": c.id, "claim": c.claim, "paper": c.source_title, "source": c.source_id,
                     "label": v.label, "quote": v.quote, "quote_found": v.quote_found, "flags": v.flags})
    verified = [r for r in rows if r["label"] in ("SUPPORTS", "REFUTES") and r["quote_found"]]
    brief = llm.chat([{"role": "system", "content": SYNTH},
                      {"role": "user", "content": f"QUESTION: {question}\n\nEVIDENCE:\n{json.dumps(verified, indent=1)}"}],
                     role="improver", max_tokens=500).text if verified else "No verified evidence found."
    return {"question": question, "claims": claims_text, "papers": [p.__dict__ for p in papers],
            "board": rows, "brief": brief, "ledger": llm.LEDGER.snapshot()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--editable", default=str(config.EDITABLE_DIR))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if config.MOCK:
        from core import mock
        mock.install()
    res = run(args.question, Path(args.editable))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=2))
    print(res["brief"])
    print(f"\n{len([r for r in res['board'] if r['quote_found']])} verified rows of {len(res['board'])}; "
          f"cost ${res['ledger']['total_usd']:.3f}")


if __name__ == "__main__":
    main()
