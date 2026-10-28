# Ratchet

**A research-claim-checking harness that improves its own harness, and keeps only the edits that beat a hidden held-out split.**

Most research agents are as good on day ten as on day one. Ratchet runs an outer loop in which an improver agent (Muse Wonder) reads where the inner harness failed, proposes one attributable edit, and a read-only grader decides whether it survives. Like a ratchet, it only moves forward.

Built for the Meta Global AI Developer Hackathon 2026, Indie track, Push the Frontier.

```
question ──> Frame ──> Retrieve ──> Verifier + Sceptic ──> Evidence board + cited brief
                                        ▲        │
                      INNER LOOP        │        │ failure traces
   ─────────────────────────────────────┼────────┼──────────────────────────────
                      OUTER LOOP        │        ▼
            Archive (git) <── accept ── Held-out gate <── Train eval <── Candidate <── Improver
                                              ▲
                                        Hidden grader (read-only, never shown to the improver)
```

## Why this isn't "just another research agent"

| What judges have seen before | What Ratchet does |
| --- | --- |
| A fixed harness with citations | A harness whose prompts, rules and workflow are edited by an agent, generation after generation |
| Scores that go up on the training set | Every accepted edit also beat a **hidden split** the improver never sees, by more than the **measured noise band** |
| "Trust me" | A **rejected cheat** in the changelog: edits that encode test items are caught by a leakage critic before scoring |
| Prompt tweaks | Four rungs: playbook rules, prompts, the workflow code, and **the improver's own instructions** |

The design follows the 2026 literature on harness-level recursive self-improvement: the public/private signal split from AIDE² (arXiv 2609.26457), the regularized proposal and selection rules from RRSI (2609.24972), the three-scope frozen anchor from Hierarchical Self-Improvement (2608.08466), and the editable meta-mechanism from Meta's Hyperagents (2603.19461). See `docs/` for the notes.

## Quick start

Standard library only. Python 3.11+.

```bash
git clone https://github.com/jmsundin/rsi-agent-harness && cd rsi-agent-harness
python3 -m venv .venv && source .venv/bin/activate
pip install certifi pytest       # certifi: TLS roots on macOS python.org builds; pytest: optional
cp .env.example .env            # add MODEL_API_KEY from dev.meta.ai

# 1. Smoke everything offline with the deterministic mock (no API calls, ~5 s)
RATCHET_MOCK=1 python -m unittest discover -s tests
RATCHET_MOCK=1 python -m loop.run --generations 6

# 2. Watch it
python -m ui.server             # http://127.0.0.1:8080

# 3. Real data and real models
python -m grader.data fetch     # downloads SciFact (1.4K expert-written claims) and rebuilds splits
python -m eval.run --split train --runs 3        # baseline; measure the noise band
python -m loop.run --generations 30 --runs 2     # the actual run (~$0.70/generation at list prices)

# 4. The payoff: the same question on gen-0 vs. the best generation
git worktree add .worktrees/gen0 <gen-0 sha>
python -m research.board "Does blocking the H+,K+-ATPase pump alter anterior regeneration in planaria?" --editable .worktrees/gen0/editable
python -m research.board "Does blocking the H+,K+-ATPase pump alter anterior regeneration in planaria?"
```

## How one generation works

1. **Noise first.** Before any generation, the base harness is scored three times and the spread becomes δ, frozen in `grader/data/noise.json`. δ is measured, never tuned.
2. **Propose.** The improver reads the incumbent's failure clusters and the full changelog (including rejections and why), and returns one edit with a `component`, `hypothesis`, `falsifier` and the new file content. Every 4th generation it may instead edit its own `improver_instructions.md`.
3. **Isolate.** The edit is applied on a fresh `cand/NNN` git branch in its own worktree. Writes outside `editable/` are refused; frozen files are diffed against `main`; `run_claims(claims, llm)` must still import with the same signature.
4. **Screen.** A leakage critic reads the **diff** (not the proposal) and rejects test-item IDs, copied test text, or model-flagged benchmark-specific logic.
5. **Score on train** in a subprocess with a scrubbed environment and a dollar cap, using the grader from the main checkout (a candidate cannot change its own scorer).
6. **Gate**, in order: train gain > δ (on a lower confidence bound) → never below best-ever − δ → cost growth ≤ 10% + 2.5 × gain → no single metric regresses beyond δ → **only then** score on the hidden split, which must also improve by > δ.
7. **Archive.** Accept = fast-forward `main`. Reject = tagged `rejected/NNN`. Either way: a line in `CHANGELOG.md` and a record in `runs/results.jsonl`.

## Repository layout

```
editable/        the ONLY tree the improver may change
  playbook.md              rung 1: rules the verifier reads every call
  prompts/*.md             rung 2
  harness/run.py           rung 3: run_claims(claims, llm) -> verdicts (interface fixed)
  improver_instructions.md rung 4: the improver's own brief
core/            frozen: config, model client (urllib + cache + cost ledger), schema, mock
grader/          frozen, READ-ONLY: SciFact loader, splits, planted errors, scorer, gate
loop/            frozen: improver, leakage critic, git archive, sandbox, orchestrator
eval/run.py      score one harness version on one split
research/        the inner research harness: question -> cited, verified evidence board
ui/              dashboard: score per generation, candidate list, diff viewer
tests/           unittest; runs offline
```

## Metrics

| Metric | What it measures |
| --- | --- |
| `label_acc` | SUPPORTS / REFUTES / NOT_ENOUGH_INFO accuracy on real claims |
| `planted_caught` | fraction of fabricated-citation and wrong-source traps the harness did not fall for |
| `nei_recall` | honest "not enough evidence" answers when that is the truth |
| `cost_per_claim` | USD, charged by the ledger on every model call |
| `composite` / `lcb` | weighted mean, and its lower confidence bound over repeated runs |

Splits: `train` (the improver sees failure traces from this), `heldout` (hidden; decides acceptance), `ood` (a different field; reported, never used for selection).

## Models

| Role | Model | Why |
| --- | --- | --- |
| Improver, Frame, Synthesis, leakage critic | `muse-wonder-1.0` | the few hard-reasoning calls per generation |
| Judge, Sceptic | `muse-spark-1.3` | the hundreds of cheap scoring calls |
| Judge, Sceptic (alternative) | `meta-models/muse-spark-open-1026` on Baseten | set `BASETEN_API_KEY`; workers switch to the open-weights model, improver stays on Wonder. Check with `python -m scripts.check_worker` |
| Any other OpenAI-compatible worker | Modal / Fireworks / self-hosted | set `RATCHET_WORKER_API_BASE`, `RATCHET_WORKER_API_KEY`, `RATCHET_MODEL_WORKER` |

Workers run at fixed low reasoning effort; only the improver thinks hard. Gains therefore come from the harness, not from thinking longer at task time.

## Troubleshooting

- `CERTIFICATE_VERIFY_FAILED` on macOS: the python.org build ships without system root certs. Run
  `/Applications/Python 3.x/Install Certificates.command`, or `pip install certifi` (the client picks it up automatically).
- `401`: wrong `MODEL_API_KEY`. `404` on the model: update `RATCHET_MODEL_*` in `.env` to the IDs your Model API dashboard lists.
- "editable/ has uncommitted changes": the loop branches candidates from a clean incumbent; commit first.

## Honest limits

- The bundled `grader/data/sample_claims.jsonl` is **synthetic** (invented findings) so the loop runs offline. Real evaluation needs SciFact (`python -m grader.data fetch`).
- The mock model is designed to be fixable by playbook rules; it demonstrates the loop, not the models.
- Self-edits are accepted provisionally and auto-reverted (`git revert`, history preserved) if the acceptance rate over the next `SELF_EDIT_EVERY` generations does not beat the previous window; the revert is logged in `CHANGELOG.md`. The pending verdict lives in the loop's in-memory `state`, so it is judged within the run that accepted the self-edit.
- Harness evolution has known failure modes (overfitting, noise chasing, test-time-search confounds). The gate and the OOD slice exist to expose them, not to hide them. Report train and held-out side by side.

## License

MIT.
