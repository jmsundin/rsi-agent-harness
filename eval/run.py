"""Score one harness version on one split.

    python -m eval.run --split train [--editable PATH] [--runs 1] [--seed 0] [--out report.json]

Loads `run_claims` from the given editable tree (default: ./editable), runs it on the split
plus its planted errors, scores it, and writes a report. The sandbox calls this inside a
candidate's worktree; the loop calls it for the incumbent. The grader is imported from the
main checkout, never from the candidate tree, so a candidate cannot change its own scorer.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import config, llm  # noqa: E402
from core.schema import Claim  # noqa: E402
from grader import data, planted, score  # noqa: E402


def load_harness(editable: Path):
    spec = importlib.util.spec_from_file_location("candidate_harness", editable / "harness" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    if not hasattr(mod, "run_claims"):
        raise RuntimeError("harness/run.py must define run_claims(claims, llm)")
    return mod


def evaluate(editable: Path, split: str, runs: int = 1, seed: int = 0, limit: int | None = None,
             cap: float | None = None) -> score.ScoreReport:
    if config.MOCK:
        from core import mock
        mock.install()
    mod = load_harness(editable)
    claims: list[Claim] = planted.with_planted(data.load_split(split), split)
    if limit:
        claims = claims[:limit]
    reports = []
    for i in range(runs):
        llm.LEDGER.begin_scope(f"eval:{split}:{i}", cap or config.CAP_PER_RUN)
        verdicts = mod.run_claims(claims, lambda msgs, **kw: llm.chat(msgs, seed=seed + i, **kw))
        reports.append(score.score(claims, verdicts, split, seed=seed + i))
    return score.aggregate(reports)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train", choices=["train", "heldout", "ood"])
    ap.add_argument("--editable", default=str(config.EDITABLE_DIR))
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    rep = evaluate(Path(args.editable), args.split, args.runs, args.seed, args.limit)
    out = rep.to_json()
    out["ledger"] = llm.LEDGER.snapshot()
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=2))
    print(json.dumps(rep.summary(), indent=2))


if __name__ == "__main__":
    main()
