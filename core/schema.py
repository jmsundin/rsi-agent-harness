"""Shared data types. Plain dataclasses so the whole project runs on the standard library."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

LABELS = ("SUPPORTS", "REFUTES", "NOT_ENOUGH_INFO")


@dataclass
class Claim:
    """One claim-checking task: a claim and the passage it is supposedly backed by."""
    id: str
    claim: str
    source_id: str          # paper / abstract id
    source_title: str
    source_text: str        # the passage the verifier may cite from
    gold_label: str         # SUPPORTS | REFUTES | NOT_ENOUGH_INFO
    planted: bool = False   # true if this is a fabricated-evidence trap
    cited_quote: str = ""   # for planted errors: the quote the claim pretends to rest on
    split: str = "train"
    domain: str = "biomed"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Verdict:
    """What the harness says about one claim."""
    claim_id: str
    label: str                      # SUPPORTS | REFUTES | NOT_ENOUGH_INFO | REJECTED
    quote: str = ""                 # exact passage the verdict rests on
    quote_found: bool = False       # deterministic check: quote appears in source_text
    confidence: float = 0.5
    rationale: str = ""
    flags: list[str] = field(default_factory=list)   # e.g. ["quote_missing", "sceptic_downgrade"]
    cost_usd: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoreReport:
    """Multi-metric score of one harness version on one split."""
    split: str
    n: int
    label_acc: float
    planted_caught: float      # fraction of planted errors flagged REJECTED or NEI
    nei_recall: float          # fraction of true NOT_ENOUGH_INFO answered NEI
    cost_usd: float
    cost_per_claim: float
    lcb: float                 # lower confidence bound on the composite
    composite: float
    per_claim: list[dict[str, Any]] = field(default_factory=list)
    seed: int = 0
    runs: int = 1

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def summary(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("per_claim", None)
        return d


@dataclass
class FileEdit:
    path: str       # relative to editable/
    content: str    # full new content


@dataclass
class Proposal:
    """One edit the improver wants to try. Everything a reviewer needs to attribute the change."""
    component: str          # prompt | playbook | workflow | improver_instructions
    hypothesis: str         # what the edit is expected to fix
    falsifier: str          # what result would show the hypothesis is wrong
    rationale: str
    edits: list[FileEdit]
    parent: str = ""        # git ref of the incumbent

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GateDecision:
    accepted: bool
    reason: str
    train: dict[str, Any] | None = None
    heldout: dict[str, Any] | None = None
    cost_delta: float = 0.0
    checks: dict[str, bool] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else str(o))
