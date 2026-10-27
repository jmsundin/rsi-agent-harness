"""Run the outer loop.

    python -m loop.run --generations 10 [--runs 1] [--limit N] [--no-heldout]

One generation:
  1. (first time) estimate the noise band delta from repeated base-harness runs; freeze it.
  2. score the incumbent on train if not cached for this HEAD.
  3. improver proposes ONE edit (or, every SELF_EDIT_EVERY gens, an edit to its own instructions).
  4. apply in a fresh worktree; enforce the editable/ boundary; smoke-test the interface.
  5. leakage critic reads the diff.
  6. score candidate on train in a subprocess.
  7. gate checks (noise, floor, cost, no-regression); only then score on held-out.
  8. accept -> fast-forward main; reject -> tag. Log either way.

Self-edits are judged differently: they are accepted provisionally and reverted if the
acceptance rate over the next SELF_EDIT_EVERY generations does not beat the previous window.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import config, llm  # noqa: E402
from core.schema import GateDecision, ScoreReport  # noqa: E402
from core.trace import Trace  # noqa: E402
from grader import gate  # noqa: E402
from loop import archive, critic, improver, sandbox  # noqa: E402

STALL_WINDOW = 3
COMPONENTS = ["playbook", "prompt", "workflow"]


def _report(d: dict) -> ScoreReport:
    keys = ScoreReport.__dataclass_fields__.keys()
    return ScoreReport(**{k: d[k] for k in keys if k in d})


def _incumbent_report(split: str, runs: int, seed: int, limit: int | None, cache: dict) -> dict:
    key = f"{archive.head()}:{split}:{seed}"
    if key not in cache:
        cache[key] = sandbox.score_in_subprocess(config.ROOT, split, runs, seed, config.CAP_PER_RUN, limit)
    return cache[key]


def self_edit_should_revert(baseline: float, window: list[bool]) -> bool:
    """A provisional self-edit survives only if the window strictly beats baseline."""
    if not window:
        return False
    return (sum(window) / len(window)) <= baseline


def maybe_revert_self_edit(gen: int, state: dict, trace: Trace) -> bool:
    """Judge a pending provisional self-edit once its window has elapsed.

    Returns True if the self-edit commit was reverted. The verdict is final
    either way: the pending state is cleared so the next self-edit starts a
    fresh window, and the outcome is logged in the changelog.
    """
    sha = state.get("self_edit_sha")
    if not sha:
        return False
    due = state.get("self_edit_due_gen",
                    state.get("self_edit_gen", gen) + improver.SELF_EDIT_EVERY)
    if gen < due:
        return False
    baseline = state.get("self_edit_baseline", 0.0)
    window = list(state.get("self_edit_window") or [])
    window_rate = (sum(window) / len(window)) if window else None

    def clear() -> None:
        for key in ("self_edit_baseline", "self_edit_sha", "self_edit_gen",
                    "self_edit_due_gen", "self_edit_window"):
            state.pop(key, None)

    if not self_edit_should_revert(baseline, window):
        trace.event("self_edit_kept", generation=gen, sha=sha,
                    baseline=baseline, window_rate=window_rate)
        clear()
        return False
    try:
        new_head = archive.revert_commit(sha)
    except RuntimeError as e:
        archive.git("revert", "--abort", check=False)
        archive.log_revert(sha, baseline, window_rate, reverted=False)
        trace.event("self_edit_revert_failed", generation=gen, sha=sha, error=str(e))
        clear()
        return False
    archive.log_revert(sha, baseline, window_rate, reverted=True, new_head=new_head)
    trace.event("self_edit_reverted", generation=gen, sha=sha, baseline=baseline,
                window_rate=window_rate, new_head=new_head)
    clear()
    return True


def ensure_noise(runs: int, limit: int | None, trace: Trace) -> float:
    if gate.NOISE_PATH.exists():
        return gate.load_delta()
    trace.event("noise_estimate_start")
    comps = []
    for s in range(3):
        rep = sandbox.score_in_subprocess(config.ROOT, "train", 1, 1000 + s, config.CAP_PER_RUN, limit)
        comps.append(rep["composite"])
    delta = gate.estimate_noise(comps)
    trace.event("noise_estimate", samples=comps, delta=delta)
    return delta


def generation(gen: int, runs: int, limit: int | None, use_heldout: bool, trace: Trace,
               cache: dict, state: dict) -> dict:
    llm.LEDGER.begin_scope(f"gen:{gen}", config.CAP_PER_GENERATION)
    # Judge any provisional self-edit whose window has elapsed before this
    # generation scores or proposes against the incumbent it produced.
    maybe_revert_self_edit(gen, state, trace)
    delta = gate.load_delta()
    base_ref = archive.head()
    inc_train = _incumbent_report("train", runs, 0, limit, cache)
    changelog = archive.read_changelog()

    # Stall detection and untouched components (RRSI structured exploration).
    recent = state.setdefault("recent_composites", [])
    stalled = len(recent) >= STALL_WINDOW and (max(recent[-STALL_WINDOW:]) - min(recent[-STALL_WINDOW:])) <= delta
    touched = state.setdefault("touched", set())
    untouched = [c for c in COMPONENTS if c not in touched]

    # Rung 4: self-edit every few generations.
    self_edit = gen > 0 and gen % improver.SELF_EDIT_EVERY == 0
    results = archive.read_results()
    recent_results = [r for r in results if not r.get("self_edit")][-improver.SELF_EDIT_EVERY:]
    acc_rate = (sum(1 for r in recent_results if r["accepted"]) / len(recent_results)) if recent_results else 0.0

    if self_edit:
        proposal = improver.propose_self_edit(config.EDITABLE_DIR, changelog, acc_rate)
    else:
        proposal = improver.propose(config.EDITABLE_DIR, inc_train, changelog, gen, stalled, untouched)
    proposal.parent = base_ref
    touched.add(proposal.component)
    trace.event("proposal", generation=gen, component=proposal.component, hypothesis=proposal.hypothesis,
                self_edit=self_edit)

    cand_id = archive.next_candidate_id()
    wt, branch = archive.create_worktree(cand_id, base_ref)
    record = {"generation": gen, "candidate": cand_id, "branch": branch, "parent": base_ref,
              "component": proposal.component, "hypothesis": proposal.hypothesis,
              "falsifier": proposal.falsifier, "self_edit": self_edit, "accepted": False}
    try:
        sandbox.apply(proposal, wt)
        sandbox.check_frozen(wt, base_ref)
        sandbox.smoke(wt)
        sha = archive.commit_in(wt, f"cand {cand_id:03d} ({proposal.component}): {proposal.hypothesis}")
        diff = archive.diff_editable(wt, base_ref)
        record["diff"] = diff
        record["sha"] = sha

        ok, why = critic.screen(diff)
        if not ok:
            decision = GateDecision(False, f"leakage screen: {why}", checks={"leakage": False})
        elif self_edit:
            # Provisional acceptance; judged by the next window's acceptance rate.
            decision = GateDecision(True, f"self-edit accepted provisionally (prior acceptance {acc_rate:.0%})",
                                    checks={"leakage": True, "provisional": True})
            state["self_edit_baseline"] = acc_rate
            state["self_edit_sha"] = sha
            state["self_edit_gen"] = gen
            state["self_edit_due_gen"] = gen + improver.SELF_EDIT_EVERY
            state["self_edit_window"] = []
        else:
            cand_train_d = sandbox.score_in_subprocess(wt, "train", runs, 0, config.CAP_PER_RUN, limit)
            cand_train = _report(cand_train_d)
            best_ever = state.get("best_ever", inc_train["composite"])
            decision = gate.decide(cand_train, _report(inc_train), best_ever, delta, leakage_ok=True)
            # Only spend on held-out if everything else passed.
            if all(decision.checks.get(k, True) for k in ("train_gain", "floor", "cost", "no_regression")):
                if use_heldout:
                    inc_held = _incumbent_report("heldout", runs, 0, limit, cache)
                    cand_held = sandbox.score_in_subprocess(wt, "heldout", runs, 0, config.CAP_PER_RUN, limit)
                    decision = gate.decide(cand_train, _report(inc_train), best_ever, delta,
                                           _report(cand_held), _report(inc_held), leakage_ok=True)
                    record["heldout"] = {k: cand_held[k] for k in ("composite", "lcb", "label_acc", "planted_caught", "nei_recall", "cost_per_claim")}
                else:
                    decision = GateDecision(True, decision.reason + " (held-out skipped)", checks=decision.checks)
            record["train"] = {k: cand_train_d[k] for k in ("composite", "lcb", "label_acc", "planted_caught", "nei_recall", "cost_per_claim")}
            record["incumbent_train"] = {k: inc_train[k] for k in ("composite", "label_acc", "planted_caught", "nei_recall", "cost_per_claim")}
            recent.append(cand_train.composite)

        record["reason"] = decision.reason
        record["checks"] = decision.checks
        if decision.accepted:
            archive.accept(branch)
            record["accepted"] = True
            if not self_edit:
                state["best_ever"] = max(state.get("best_ever", 0.0), record["train"]["composite"])
        else:
            archive.tag_rejected(branch, cand_id)
    except (sandbox.BoundaryViolation, RuntimeError) as e:
        record["reason"] = f"rejected before scoring: {e}"
        record["checks"] = {"boundary": False}
    finally:
        archive.remove_worktree(wt)

    # Feed this generation's verdict into a pending self-edit's window.
    if not self_edit and state.get("self_edit_sha"):
        state.setdefault("self_edit_window", []).append(bool(record["accepted"]))
    record["ledger"] = llm.LEDGER.snapshot()
    archive.log(record)
    trace.event("decision", generation=gen, candidate=cand_id, accepted=record["accepted"], reason=record["reason"])
    return record


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=5)
    ap.add_argument("--runs", type=int, default=1, help="repeated runs per evaluation (for LCB)")
    ap.add_argument("--limit", type=int, default=None, help="claims per split (speeds up smoke runs)")
    ap.add_argument("--no-heldout", action="store_true")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    if config.MOCK:
        from core import mock
        mock.install()

    run_id = args.run_id or f"loop-{archive.head()}"
    trace = Trace(run_id)
    archive.git("status", "--porcelain")  # fail early if not a git repo
    if archive.git("status", "--porcelain", "--", "editable"):
        raise SystemExit("editable/ has uncommitted changes; commit them first so candidates branch from a clean incumbent")

    delta = ensure_noise(args.runs, args.limit, trace)
    print(f"noise band delta = {delta:.4f}  incumbent = {archive.head()}")
    cache: dict = {}
    state: dict = {}
    for gen in range(args.generations):
        try:
            rec = generation(gen, args.runs, args.limit, not args.no_heldout, trace, cache, state)
        except llm.BudgetExceeded as e:
            print(f"stopping: {e}")
            break
        tr = rec.get("train") or {}
        ho = rec.get("heldout") or {}
        print(f"gen {gen:02d} cand {rec['candidate']:03d} [{'ACCEPT' if rec['accepted'] else 'reject'}] "
              f"{rec['component']:<22} train={tr.get('composite', '-')} held-out={ho.get('composite', '-')} :: {rec['reason']}")
    receipt = trace.receipt(llm.LEDGER.snapshot(), incumbent=archive.head(), delta=delta)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
