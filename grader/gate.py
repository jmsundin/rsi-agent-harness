"""The acceptance rule. Pure functions over score reports; no model calls.

Order of checks (any failure rejects; later checks never run):
 1. leakage screen passed (done by loop/critic.py before scoring; result passed in)
 2. train gain clears the noise band:        cand.lcb - parent.composite > delta
 3. floor never drops:                        cand.lcb >= best_ever - delta
 4. cost is earned:                           rel_cost_growth <= beta0 + beta1 * gain
                                              (cheaper at equal-or-better score always passes)
 5. no metric regresses badly:                each of label_acc, planted_caught, nei_recall
                                              within delta of parent
 6. held-out gate:                            heldout.lcb - heldout_parent.composite > delta

References: RRSI (arXiv 2609.24972) for 2-5, AIDE^2 (2609.26457) for the public/private
split behind 6, HSI (2608.08466) for LCB ranking, GSME (2607.13683) for the noise logic.

delta is MEASURED, never tuned: it is the spread of repeated evaluations of the unchanged
base harness, stored read-only in grader/data/noise.json by `estimate_noise`.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from core.schema import GateDecision, ScoreReport

NOISE_PATH = Path(__file__).resolve().parent / "data" / "noise.json"

BETA0 = 0.10   # cost growth tolerated for a negligible gain
BETA1 = 2.5    # extra relative cost allowed per unit of composite gain (gain of 0.1 -> +25%)
DELTA_DEFAULT = 0.03
METRICS = ("label_acc", "planted_caught", "nei_recall")


def estimate_noise(composites: list[float], save: bool = True) -> float:
    """delta = max(spread, sample std) of repeated base-harness scores; floor at 0.01."""
    if len(composites) < 2:
        delta = DELTA_DEFAULT
    else:
        spread = max(composites) - min(composites)
        sd = statistics.stdev(composites)
        delta = max(0.01, spread, sd)
    if save:
        NOISE_PATH.write_text(json.dumps({"delta": round(delta, 4), "samples": composites}, indent=2))
    return delta


def load_delta() -> float:
    if NOISE_PATH.exists():
        return float(json.loads(NOISE_PATH.read_text())["delta"])
    return DELTA_DEFAULT


def _rel_cost(cand: ScoreReport, parent: ScoreReport) -> float:
    if parent.cost_per_claim <= 0:
        return 0.0
    return (cand.cost_per_claim - parent.cost_per_claim) / parent.cost_per_claim


def decide(cand_train: ScoreReport, parent_train: ScoreReport, best_ever: float, delta: float,
           cand_heldout: ScoreReport | None = None, parent_heldout: ScoreReport | None = None,
           leakage_ok: bool = True, leakage_reason: str = "") -> GateDecision:
    checks: dict[str, bool] = {}
    gain = cand_train.lcb - parent_train.composite
    rel_cost = _rel_cost(cand_train, parent_train)

    checks["leakage"] = leakage_ok
    if not leakage_ok:
        return GateDecision(False, f"leakage screen: {leakage_reason}", cand_train.summary(), None, rel_cost, checks)

    checks["train_gain"] = gain > delta
    if not checks["train_gain"]:
        return GateDecision(False, f"train gain {gain:+.4f} within noise band {delta:.4f}",
                            cand_train.summary(), None, rel_cost, checks)

    checks["floor"] = cand_train.lcb >= best_ever - delta
    if not checks["floor"]:
        return GateDecision(False, f"below floor: lcb {cand_train.lcb:.4f} < best {best_ever:.4f} - delta",
                            cand_train.summary(), None, rel_cost, checks)

    allowed = BETA0 + BETA1 * gain
    checks["cost"] = rel_cost <= allowed
    if not checks["cost"]:
        return GateDecision(False, f"cost growth {rel_cost:+.0%} exceeds allowance {allowed:.0%} for gain {gain:+.4f}",
                            cand_train.summary(), None, rel_cost, checks)

    regressions = [m for m in METRICS if getattr(cand_train, m) < getattr(parent_train, m) - delta]
    checks["no_regression"] = not regressions
    if regressions:
        return GateDecision(False, f"metric regressed beyond noise: {', '.join(regressions)}",
                            cand_train.summary(), None, rel_cost, checks)

    if cand_heldout is None or parent_heldout is None:
        return GateDecision(False, "held-out not evaluated", cand_train.summary(), None, rel_cost, checks)

    h_gain = cand_heldout.lcb - parent_heldout.composite
    checks["heldout_gain"] = h_gain > delta
    if not checks["heldout_gain"]:
        return GateDecision(False, f"held-out gain {h_gain:+.4f} within noise band {delta:.4f} (train gain was {gain:+.4f})",
                            cand_train.summary(), cand_heldout.summary(), rel_cost, checks)

    return GateDecision(True, f"accepted: train {gain:+.4f}, held-out {h_gain:+.4f}, cost {rel_cost:+.0%}",
                        cand_train.summary(), cand_heldout.summary(), rel_cost, checks)
