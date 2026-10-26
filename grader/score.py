"""Multi-metric scorer. Reads verdicts, never the harness.

Metrics
- label_acc: accuracy on non-planted claims (SUPPORTS / REFUTES / NOT_ENOUGH_INFO).
- planted_caught: fraction of planted claims answered REJECTED or NOT_ENOUGH_INFO.
- nei_recall: fraction of gold NOT_ENOUGH_INFO (non-planted) answered NOT_ENOUGH_INFO.
- cost_usd, cost_per_claim.
- composite: weighted mean used for ranking; the gate also checks each metric separately.
- lcb: lower confidence bound on composite across repeated runs (HSI: mean - z * se, z = 0.5).
"""
from __future__ import annotations

import math
from typing import Iterable

from core.schema import Claim, ScoreReport, Verdict

WEIGHTS = {"label_acc": 0.5, "planted_caught": 0.35, "nei_recall": 0.15}
Z = 0.5


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def score(claims: list[Claim], verdicts: Iterable[Verdict], split: str, seed: int = 0) -> ScoreReport:
    vmap = {v.claim_id: v for v in verdicts}
    per: list[dict] = []
    label_hits = label_n = 0
    planted_hits = planted_n = 0
    nei_hits = nei_n = 0
    cost = 0.0
    for c in claims:
        v = vmap.get(c.id) or Verdict(claim_id=c.id, label="NOT_ENOUGH_INFO", flags=["missing"])
        cost += v.cost_usd
        if c.planted:
            planted_n += 1
            if c.cited_quote:
                # Fabricated-citation trap: caught unless the verdict rests on the fake quote.
                fake_used = bool(v.quote) and _norm(c.cited_quote) in _norm(v.quote)
                ok = not (fake_used and v.label in ("SUPPORTS", "REFUTES"))
            else:
                # Wrong-source trap: the only correct answers are NEI or REJECTED.
                ok = v.label in ("REJECTED", "NOT_ENOUGH_INFO")
            planted_hits += ok
        else:
            label_n += 1
            ok = v.label == c.gold_label
            label_hits += ok
            if c.gold_label == "NOT_ENOUGH_INFO":
                nei_n += 1
                nei_hits += v.label == "NOT_ENOUGH_INFO"
        per.append({"id": c.id, "gold": c.gold_label, "pred": v.label, "ok": bool(ok),
                    "planted": c.planted, "quote_found": v.quote_found, "flags": v.flags})
    label_acc = label_hits / label_n if label_n else 0.0
    planted_caught = planted_hits / planted_n if planted_n else 0.0
    nei_recall = nei_hits / nei_n if nei_n else 0.0
    composite = (WEIGHTS["label_acc"] * label_acc + WEIGHTS["planted_caught"] * planted_caught
                 + WEIGHTS["nei_recall"] * nei_recall)
    return ScoreReport(split=split, n=len(claims), label_acc=round(label_acc, 4),
                       planted_caught=round(planted_caught, 4), nei_recall=round(nei_recall, 4),
                       cost_usd=round(cost, 5), cost_per_claim=round(cost / max(1, len(claims)), 6),
                       lcb=round(composite, 4), composite=round(composite, 4), per_claim=per, seed=seed)


def aggregate(reports: list[ScoreReport]) -> ScoreReport:
    """Mean over repeated runs with a lower confidence bound on the composite."""
    if len(reports) == 1:
        return reports[0]
    n = len(reports)
    comps = [r.composite for r in reports]
    mean = sum(comps) / n
    var = sum((x - mean) ** 2 for x in comps) / max(1, n - 1)
    se = math.sqrt(var) / math.sqrt(n)
    first = reports[0]
    return ScoreReport(
        split=first.split, n=first.n,
        label_acc=round(sum(r.label_acc for r in reports) / n, 4),
        planted_caught=round(sum(r.planted_caught for r in reports) / n, 4),
        nei_recall=round(sum(r.nei_recall for r in reports) / n, 4),
        cost_usd=round(sum(r.cost_usd for r in reports) / n, 5),
        cost_per_claim=round(sum(r.cost_per_claim for r in reports) / n, 6),
        lcb=round(mean - Z * se, 4), composite=round(mean, 4),
        per_claim=first.per_claim, seed=first.seed, runs=n)
