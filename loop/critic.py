"""Leakage critic: reads the DIFF (not the proposal) and rejects benchmark-specific edits.

Two layers (RRSI): a deterministic scan for test-item identifiers and literal test text,
then a model read for subtler leakage (hard-coded answers, rules that only fire on the
evaluation items, inert machinery). Runs BEFORE scoring, so a leaking candidate never gets
the inflated score that would make it attractive later.
"""
from __future__ import annotations

import re

from core import llm
from grader import data, planted

SYSTEM = """LEAKAGE CRITIC. You review a diff to a scientific claim-checking harness.
Reject the diff if it encodes anything specific to the evaluation set: claim identifiers, paper titles or IDs,
sentences copied from test items, rules that can only apply to particular test items, hard-coded answers,
or code that never executes. Generic improvements to prompts, rules or workflow are fine.
Respond with JSON only: {"leaks": true|false, "reason": "<one sentence or empty>"}"""

ID_PATTERNS = [r"\bsyn-\d+\b", r"\bsf-\d+(?:-\d+)?\b", r"\bdoc-\d+\b", r"planted", r"heldout", r"held-out split"]


def _deterministic(diff: str) -> str | None:
    added = "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    for pat in ID_PATTERNS:
        if re.search(pat, added, re.I):
            return f"added text matches test-item pattern {pat!r}"
    # Literal test text: any 8-word window from a train/held-out claim or source appearing in the diff.
    low = added.lower()
    for split in ("train", "heldout"):
        for c in planted.with_planted(data.load_split(split), split):
            for text in (c.claim, c.cited_quote):
                words = text.lower().split()
                for i in range(0, max(1, len(words) - 7)):
                    window = " ".join(words[i:i + 8])
                    if len(window) > 30 and window in low:
                        return "added text copies an evaluation item verbatim"
    return None


def screen(diff: str) -> tuple[bool, str]:
    """Return (ok, reason). ok=False means the candidate is rejected before scoring."""
    if not diff.strip():
        return False, "empty diff"
    det = _deterministic(diff)
    if det:
        return False, det
    reply = llm.chat([{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": f"DIFF:\n{diff[:12000]}"}],
                     role="improver", json_mode=True, max_tokens=200)
    try:
        j = reply.json()
    except Exception:
        return True, ""
    if j.get("leaks"):
        return False, str(j.get("reason", "model critic flagged leakage"))
    return True, ""
