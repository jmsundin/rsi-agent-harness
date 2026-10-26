"""The improver: reads failure traces and the changelog, proposes ONE attributable edit.

Also implements the self-edit rung: every `SELF_EDIT_EVERY` generations it may propose an
edit to its own instructions file instead, judged by whether acceptance rate improves.
"""
from __future__ import annotations

import json
from pathlib import Path

from core import config, llm
from core.schema import FileEdit, Proposal

SELF_EDIT_EVERY = 4
EDITABLE_FILES = ("playbook.md", "prompts/judge.md", "prompts/sceptic.md", "harness/run.py",
                  "improver_instructions.md")


def _editable_dump(editable: Path, files=EDITABLE_FILES) -> str:
    parts = []
    for rel in files:
        p = editable / rel
        if p.exists():
            parts.append(f"=== {rel} ===\n{p.read_text()}\n")
    parts.append("=== end ===")
    return "\n".join(parts)


def failure_traces(report: dict, max_items: int = 12) -> str:
    """Specific misses from the incumbent's train report, grouped so the improver sees clusters."""
    wrong = [p for p in report.get("per_claim", []) if not p["ok"]]
    clusters: dict[str, list[dict]] = {}
    for p in wrong:
        key = f"gold={p['gold']} pred={p['pred']} planted={p['planted']}"
        clusters.setdefault(key, []).append(p)
    lines = [f"{len(wrong)} of {report.get('n', 0)} claims wrong. Clusters (largest first):"]
    for key, items in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- {len(items)}x {key}; flags seen: {sorted({f for p in items for f in p['flags']})}")
    return "\n".join(lines[:max_items + 1])


def _parse(reply: llm.Reply, allowed: tuple[str, ...]) -> Proposal:
    j = reply.json()
    edits = [FileEdit(path=e["path"], content=e["content"]) for e in j.get("edits", [])]
    edits = [e for e in edits if e.path in allowed]
    return Proposal(component=str(j.get("component", "playbook")), hypothesis=str(j.get("hypothesis", "")),
                    falsifier=str(j.get("falsifier", "")), rationale=str(j.get("rationale", "")), edits=edits)


def propose(editable: Path, train_report: dict, changelog: str, generation: int,
            stalled: bool = False, untouched: list[str] | None = None) -> Proposal:
    instructions = (editable / "improver_instructions.md").read_text()
    allowed = ("playbook.md", "prompts/judge.md", "prompts/sceptic.md", "harness/run.py")
    system = instructions
    user = (f"GENERATION {generation}\n\nFAILURE TRACES OF THE CURRENT BEST VERSION:\n{failure_traces(train_report)}\n\n"
            f"CHANGELOG (every edit tried so far):\n{changelog or '(none yet)'}\n\n"
            f"{'SEARCH IS STALLED: prefer a component not yet touched: ' + ', '.join(untouched or []) if stalled else ''}\n\n"
            f"CURRENT EDITABLE FILES:\n{_editable_dump(editable, allowed)}\n\n"
            "Propose ONE edit. Respond with JSON only:\n"
            '{"component": "playbook|prompt|workflow", "hypothesis": "...", "falsifier": "...", '
            '"rationale": "...", "edits": [{"path": "<one of the editable paths>", "content": "<full new file content>"}]}')
    reply = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                     role="improver", json_mode=True, max_tokens=4000)
    return _parse(reply, allowed)


def propose_self_edit(editable: Path, changelog: str, acceptance_rate: float) -> Proposal:
    """Rung 4: the improver edits its own instructions (text only)."""
    system = ("SELF-EDIT. You are the improver of a claim-checking harness, reviewing your own instructions. "
              "Your recent proposals were accepted at the rate shown. Propose ONE change to your instructions that "
              "should raise the acceptance rate: a heuristic about which edits to try, what to avoid, or how to read traces. "
              "Keep the hard rules (no test-item references, one edit per round, fixed interface). "
              "Respond with JSON only: {\"component\": \"improver_instructions\", \"hypothesis\": \"...\", "
              "\"falsifier\": \"...\", \"rationale\": \"...\", \"edits\": [{\"path\": \"improver_instructions.md\", "
              "\"content\": \"<full new content>\"}]}")
    user = (f"ACCEPTANCE RATE OF RECENT PROPOSALS: {acceptance_rate:.0%}\n\nCHANGELOG:\n{changelog}\n\n"
            f"CURRENT FILES:\n{_editable_dump(editable, ('improver_instructions.md',))}")
    reply = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                     role="improver", json_mode=True, max_tokens=2500)
    return _parse(reply, ("improver_instructions.md",))
