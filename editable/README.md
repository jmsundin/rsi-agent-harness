# editable/

The ONLY tree the improver may change. Everything else in the repo is a frozen anchor.

| Path | Rung | What it is |
| --- | --- | --- |
| `playbook.md` | 1 | Rules the verifier reads on every call. Appended by the improver. |
| `prompts/*.md` | 2 | Per-stage prompts. |
| `harness/run.py` | 3 | The workflow: `run_claims(claims, llm) -> list[Verdict]`. Interface is fixed. |
| `improver_instructions.md` | 4 | The improver's own brief. Text only. |

Invariants the loop enforces (see `loop/sandbox.py`):
- Writes outside this directory are rejected.
- `run_claims` keeps its signature; the sandbox smoke-tests it before scoring.
- No network access except the model endpoint.
