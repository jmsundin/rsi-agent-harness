# Context for coding agents working on Ratchet

Read this first, then `README.md` and `docs/DESIGN.md`. This file explains why the code is shaped the way it is and what not to break. It is written for Muse Code (Muse Wonder), but any agent should follow it.

## What this is, in three sentences

Ratchet is an entry for the Meta Global AI Developer Hackathon (Oct 26 – Nov 4, 2026, Indie track, Push the Frontier). It is a scientific claim-checking harness whose *harness* (prompts, rules, workflow) is edited by an improver agent in an outer loop, with every edit kept only if it beats a hidden held-out split by more than a measured noise band. The claim checker is the inner loop; the self-improvement loop is the product.

## Why it is built this way

The 2026 literature on harness-level recursive self-improvement converged on a few rules, and the code follows them deliberately:

| Rule | Where it lives | Source |
| --- | --- | --- |
| Keep the signal the agent optimizes separate from the signal that selects it | `grader/` is read-only; held-out split never shown to the improver | AIDE² (arXiv 2609.26457) |
| Measure noise before the loop; never tune it | `grader/gate.py: estimate_noise`, `grader/data/noise.json` | RRSI (2609.24972) |
| One attributable edit per candidate, with a hypothesis and a falsifier | `core/schema.py: Proposal`, `loop/improver.py` | RRSI, HSI (2608.08466) |
| Screen diffs for benchmark leakage before scoring | `loop/critic.py` | RRSI |
| Cost must be earned; metrics must not regress | `grader/gate.py: decide` | RRSI |
| Frozen anchor: the improver edits the harness and its own brief, never the loop or grader | `editable/` vs. everything else, enforced in `loop/sandbox.py` | HSI, Hyperagents (2603.19461) |
| Workers think at fixed low effort; only the improver thinks hard | `core/config.py: *_REASONING` | HSI |

If you are about to change something that violates one of these, stop and say so instead.

## Repository map

```
editable/                 the ONLY tree the improver may change (rungs 1-4)
  playbook.md             rung 1: one-line rules the verifier reads every call
  prompts/judge.md        rung 2
  prompts/sceptic.md      rung 2
  harness/run.py          rung 3: run_claims(claims, llm) -> list[Verdict]  (signature is FIXED)
  improver_instructions.md rung 4: the improver's own brief (text only)
core/                     frozen
  config.py               env, model routing, dollar caps
  llm.py                  OpenAI-compatible chat via urllib; disk cache; cost ledger with hard caps
  net.py                  shared SSL context (certifi fallback)
  schema.py               Claim, Verdict, ScoreReport, Proposal, GateDecision (dataclasses)
  mock.py                 deterministic offline model; RATCHET_MOCK=1
  trace.py                per-run receipt
grader/                   frozen, READ-ONLY to agents in the loop
  data.py                 SciFact loader + fixed train/heldout/ood splits (grader/data/splits.json)
  planted.py              fabricated-citation and wrong-source traps
  score.py                label_acc, planted_caught, nei_recall, cost; composite + LCB
  gate.py                 the acceptance rule (see docs/DESIGN.md)
loop/                     frozen
  improver.py             propose() and propose_self_edit()
  critic.py               leakage screen (regex + model) on the diff
  archive.py              git branches cand/NNN, CHANGELOG.md, runs/results.jsonl
  sandbox.py              boundary enforcement, smoke import, subprocess scoring
  run.py                  one generation end to end; CLI
eval/run.py               score one harness version on one split
research/                 inner research harness for the demo (question -> evidence board -> brief)
ui/                       stdlib dashboard reading runs/results.jsonl
tests/                    unittest; must stay runnable with RATCHET_MOCK=1 and no network
```

## Hard constraints

1. **Standard library only at runtime.** No new dependencies without asking. `certifi` and `pytest` are optional extras.
2. **`run_claims(claims, llm)` keeps its signature.** `loop/sandbox.py: smoke` checks it; the eval and the research board depend on it.
3. **Nothing under `grader/`, `core/`, `loop/`, `eval/` may be edited by the improver.** You may edit them as the developer, but do not add any code path that lets the improver reach them.
4. **Every model call goes through `core.llm.chat`.** That is where caching and dollar caps live. No direct HTTP to the model endpoint elsewhere.
5. **Never lower δ to make an edit pass.** It is measured from repeated base-harness runs.
6. **No test-item references in `editable/`.** The critic rejects `syn-N`, `sf-N`, `doc-N`, the words `planted`/`heldout`, and any 8-word window copied from a claim.
7. **Tests must pass offline:** `RATCHET_MOCK=1 python -m unittest discover -s tests`.
8. **The loop refuses to start with uncommitted changes in `editable/`.** Commit before running it.

## Hackathon rules that shape decisions

- New work only; public repo; demo only what was built in the window. Keep `BUILT_DURING_EVENT.md` honest.
- Avoid the judges' "overdone" list: no medical advice, no basic RAG framing, no dashboard-as-product, no Streamlit. The claim domain is model-organism and materials science; the dashboard is a view onto the loop.
- Judging (as published): Impact 30%, Use of Meta AI tooling 25%, Demo 25%, Technical depth 20%. Meta models: `muse-wonder-1.0` as improver, `muse-spark-1.3` as worker; Muse Code as the build tool. Name the model behind each stage in anything user-facing.

## Current state (Oct 26 evening)

Done: scaffold, grader, gate, editable harness, loop, dashboard, research board, 21 tests, SciFact fetched locally (868 claims, 60/40/20 splits). Real-model eval confirmed working (~$0.002 per claim).

Known gaps, in priority order:
1. ~~**Provisional self-edits are not auto-reverted.**~~ Done: `loop/run.py: maybe_revert_self_edit` judges the pending self-edit at `state["self_edit_due_gen"]` (= acceptance gen + `SELF_EDIT_EVERY`); if the window acceptance rate does not strictly beat `state["self_edit_baseline"]`, `loop/archive.py: revert_commit` reverts it on `main` and `log_revert` records it in the changelog. Pending state is in-memory, so the verdict lands in the same run. Covered by `tests/test_self_edit_revert.py`.
2. **Pruning rule not implemented.** RRSI: components with no positive gain in the last 4 rounds should be reported to the improver as deletion targets. Needs a per-component gain history in `state` and a line in the improver prompt.
3. **OOD split on real data is just more biomed.** SciFact is single-domain. A second claim source would make `ood` meaningful; low priority.
4. **`research/board.py` has no mock for Frame/Synthesis**, so it returns empty offline. Fine for now.
5. **Dashboard has no family tree**, only a score-per-generation chart. Nice to have.

## Schedule context

Thu Oct 29 is go/no-go: at least one accepted edit that beats held-out on real SciFact data. Fri: workflow rung and self-edit. Sat: long run, UI, demo replay. Sun: freeze. Tue Nov 3: submit. Prefer small, verifiable changes over new features; anything that makes the Thursday gate more likely to pass is the priority.

## Commit conventions

Short imperative subject; body explains the why if not obvious; end with:

```
Co-Authored-By: Muse Code (muse-wonder-1.0) <muse@meta.ai>
```

Run `make test` before every commit.
