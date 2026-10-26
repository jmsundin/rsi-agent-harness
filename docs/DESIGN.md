# Design notes

## The acceptance rule, with sources

| Check | Rule | From |
| --- | --- | --- |
| Noise band δ | spread of 3 repeated base-harness scores; never lowered | RRSI §3.3, GSME |
| Ranking | lower confidence bound: mean − 0.5·se over repeated runs | HSI §4.1 |
| Train gain | cand.lcb − parent.composite > δ | RRSI eq. 5 |
| Floor | cand.lcb ≥ best_ever − δ | RRSI eq. 5 |
| Cost | ΔC ≤ β₀ + β₁·ΔS with β₀ = 0.10, β₁ = 2.5 | RRSI eq. 7 |
| No regression | each metric within δ of parent | this project |
| Held-out | hidden split must also gain > δ | AIDE² §2.1 (private grade) |
| Leakage | critic reads the diff; test IDs and copied text rejected before scoring | RRSI §3.3 |

## What the improver may touch

Three scopes (HSI): the task harness (`editable/harness`, `prompts`, `playbook.md`), the evolver's own
brief (`improver_instructions.md`, text only), and a frozen anchor (`core/`, `grader/`, `loop/`, `eval/`)
that no agent edits. Writes outside `editable/` fail at `loop/sandbox.py`; frozen files are diffed against
`main` after every edit.

## Why claim checking is the inner task

It is cheap to score (cents per candidate on Spark), gold-labelled (SciFact), hard to fake (planted
fabricated citations), and the regime where harness evolution is known to help: a competent-but-imperfect
model with clean feedback. It is also the component of a research agent whose failure is most harmful.

## Reading list

AIDE² 2609.26457 · RRSI 2609.24972 · Hierarchical Self-Improvement 2608.08466 · Hyperagents 2603.19461 ·
Darwin Gödel Machine 2505.22954 · GEPA 2507.19457 · ACE 2510.04618 · SICA 2504.15228 ·
Rethinking the Evaluation of Harness Evolution 2607.12227 · SEAGym 2606.17546 · SciFact 2004.14974
