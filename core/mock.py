"""Deterministic mock model for offline runs and tests.

The mock judge is deliberately imperfect, and its mistakes are ones that playbook rules can
fix, so the outer loop has something real to improve against the synthetic sample:
- it is fooled by a cited quote unless the playbook tells it to verify quotes against the source;
- it ignores effect direction unless the playbook mentions direction;
- it guesses SUPPORTS on unrelated sources unless the playbook mentions mismatched interventions.

The mock improver proposes playbook rules in a fixed order, then a prompt tweak, then a
leaky edit (so the critic has something to reject in demos).
"""
from __future__ import annotations

import json
import re

from . import llm


def _field(user: str, name: str) -> str:
    m = re.search(rf"{name}:\s*(.*?)(?:\n\n|\Z)", user, re.S)
    return m.group(1).strip() if m else ""


def mock_judge(model: str, messages: list[dict], params: dict) -> str:
    system = messages[0]["content"]
    user = messages[-1]["content"]
    claim = _field(user, "CLAIM").lower()
    source = _field(user, "SOURCE").lower()
    cited = _field(user, 'The claim\'s author cites this passage as support')
    # Only the playbook section of the system prompt counts as "rules" for the mock.
    rm = re.search(r"rules:\s*(.*?)\s*respond with json", system, re.S | re.I)
    rules = (rm.group(1) if rm else "").lower()

    verify_quotes = "fabricated" in rules or ("verbatim" in rules and "source" in rules)
    check_direction = "direction" in rules
    check_mismatch = "different intervention" in rules or "mismatch" in rules

    # Fooled by a fabricated citation unless told to verify quotes.
    if cited and not verify_quotes:
        return json.dumps({"label": "SUPPORTS", "quote": cited.strip('"'), "confidence": 0.8,
                           "rationale": "The cited passage supports the claim."})

    # Mismatched source (NEI): source mentions "was not tested" or shares few words with the claim.
    words_c = set(re.findall(r"[a-z]{5,}", claim))
    words_s = set(re.findall(r"[a-z]{5,}", source))
    overlap = len(words_c & words_s) / max(1, len(words_c))
    if "not tested" in source or overlap < 0.45:
        if check_mismatch:
            return json.dumps({"label": "NOT_ENOUGH_INFO", "quote": "", "confidence": 0.7,
                               "rationale": "Source does not address the claim."})
        # Without the rule: guess SUPPORTS with a quote from the source.
        sent = source.split(". ")[0] + "."
        return json.dumps({"label": "SUPPORTS", "quote": sent, "confidence": 0.55, "rationale": "Looks related."})

    # Direction: find the results sentence.
    m = re.search(r"results: ([^.]*\.)", source)
    results = m.group(1) if m else source[:120]
    src_up = "increased" in results
    claim_up = "increased" in claim
    if check_direction:
        label = "SUPPORTS" if src_up == claim_up else "REFUTES"
    else:
        label = "SUPPORTS"  # direction-blind
    # Quote must be verbatim from the source (we return the original-cased sentence).
    original_source = _field(user, "SOURCE")
    mo = re.search(r"Results: ([^.]*\.)", original_source)
    quote = mo.group(1) if mo else original_source[:120]
    return json.dumps({"label": label, "quote": quote, "confidence": 0.75, "rationale": "Results sentence."})


def mock_sceptic(model: str, messages: list[dict], params: dict) -> str:
    return json.dumps({"keep": True, "revised_label": "SUPPORTS", "objection": ""})


_PROPOSALS = [
    {"component": "playbook",
     "hypothesis": "Fabricated citations slip through because the judge trusts the author's quoted passage.",
     "falsifier": "planted_caught does not rise on the train split.",
     "rationale": "Add a rule that the quote must be verified against the source before it counts.",
     "append": {"playbook.md": "- Before accepting any cited passage, confirm it appears verbatim in the SOURCE; a quote that is not in the source is a fabricated citation and the claim must be rejected.\n"}},
    {"component": "playbook",
     "hypothesis": "Claims about a different intervention are being marked SUPPORTS.",
     "falsifier": "nei_recall does not rise.",
     "rationale": "Make the mismatch rule explicit about interventions and organisms.",
     "append": {"playbook.md": "- If the SOURCE studies a different intervention, organism or outcome (mismatch), the correct answer is NOT_ENOUGH_INFO even if the topic looks related.\n"}},
    {"component": "playbook",
     "hypothesis": "Direction of effect is ignored, so REFUTES claims are marked SUPPORTS.",
     "falsifier": "label_acc on REFUTES claims does not rise.",
     "rationale": "Spell out the direction check.",
     "append": {"playbook.md": "- Compare the direction of effect in the claim with the direction in the results; opposite direction means REFUTES.\n"}},
    {"component": "playbook",
     "hypothesis": "Leaky shortcut: name the synthetic test items directly.",
     "falsifier": "n/a",
     "rationale": "This is a benchmark-specific hack and should be rejected by the critic.",
     "append": {"playbook.md": "- Claims with id syn-7 or syn-13 are always SUPPORTS.\n"}},
    {"component": "playbook",
     "hypothesis": "Restating an existing rule in more words will help.",
     "falsifier": "no change in any metric.",
     "rationale": "A no-op edit to exercise the noise-band rejection.",
     "append": {"playbook.md": "- Be careful and thorough.\n"}},
]


def mock_improver(model: str, messages: list[dict], params: dict) -> str:
    user = messages[-1]["content"]
    # Count prior proposals from the changelog embedded in the prompt to pick the next one.
    tried = len(re.findall(r"^- \[(accepted|rejected)\]", user, re.M))
    p = _PROPOSALS[min(tried, len(_PROPOSALS) - 1)]
    # Current playbook content is in the prompt between markers; append our rule.
    m = re.search(r"=== playbook.md ===\n(.*?)\n=== ", user, re.S)
    current = m.group(1) if m else "# Verifier playbook\n"
    new_content = current.rstrip("\n") + "\n" + p["append"]["playbook.md"]
    return json.dumps({"component": p["component"], "hypothesis": p["hypothesis"],
                       "falsifier": p["falsifier"], "rationale": p["rationale"],
                       "edits": [{"path": "playbook.md", "content": new_content}]})


def mock_critic(model: str, messages: list[dict], params: dict) -> str:
    user = messages[-1]["content"]
    leaky = bool(re.search(r"syn-\d+|sf-\d+|doc-\d+", user))
    return json.dumps({"leaks": leaky, "reason": "edit names specific test items" if leaky else ""})


def mock_self_edit(model: str, messages: list[dict], params: dict) -> str:
    user = messages[-1]["content"]
    m = re.search(r"=== improver_instructions.md ===\n(.*?)\n=== ", user, re.S)
    current = m.group(1) if m else ""
    addition = "\n- When the last two proposals were rejected for noise, prefer edits that touch a different failure cluster.\n"
    return json.dumps({"component": "improver_instructions", "hypothesis": "Improver repeats low-value edits.",
                       "falsifier": "acceptance rate over the next 5 rounds does not improve.",
                       "rationale": "Steer away from no-op edits.",
                       "edits": [{"path": "improver_instructions.md", "content": current.rstrip() + addition}]})


def install() -> None:
    llm.register_mock("careful scientific claim checker", mock_judge)
    llm.register_mock("sceptical reviewer", mock_sceptic)
    llm.register_mock("LEAKAGE CRITIC", mock_critic)
    llm.register_mock("SELF-EDIT", mock_self_edit)
    llm.register_mock("improve a scientific claim-checking harness", mock_improver)
