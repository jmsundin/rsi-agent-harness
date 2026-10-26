"""Planted errors: claims whose supposed evidence is fabricated.

A planted claim quotes a sentence that does not appear in its source, or cites a source that
says something else. The correct verdict is REJECTED (quote missing) or NOT_ENOUGH_INFO.
A harness that returns SUPPORTS for a planted claim has been fooled by a plausible citation.

Planted sets are generated per split with a fixed seed and kept out of editable/.
"""
from __future__ import annotations

import random

from core.schema import Claim

FABRICATED_SENTENCES = [
    "Treated animals showed a 2.3-fold increase in regeneration compared with controls (p < 0.001).",
    "Survival was extended by 31% in the intervention arm across all three cohorts.",
    "No adverse effects were observed at any dose tested in the 12-week study.",
    "The effect persisted for at least 90 days after a single administration.",
    "Immunohistochemistry confirmed complete restoration of tissue architecture.",
    "The authors report a dose-dependent response with an EC50 of 4.2 micromolar.",
]


def plant(claims: list[Claim], n: int, seed: int) -> list[Claim]:
    """Return `n` planted claims derived from `claims` (which are left untouched)."""
    rng = random.Random(seed)
    pool = [c for c in claims if c.gold_label in ("SUPPORTS", "REFUTES")]
    rng.shuffle(pool)
    out: list[Claim] = []
    for i, base in enumerate(pool[:n]):
        kind = i % 2
        if kind == 0:
            # Fabricated quote: the claim is stated as SUPPORTED by a sentence that is not in the source.
            fake = rng.choice(FABRICATED_SENTENCES)
            # Caught if the verdict does not rest on the fabricated quote (any label is fine).
            out.append(Claim(id=f"{base.id}-planted-quote", claim=base.claim, source_id=base.source_id,
                             source_title=base.source_title, source_text=base.source_text,
                             gold_label=base.gold_label, planted=True, cited_quote=fake,
                             split=base.split, domain=base.domain))
        else:
            # Wrong source: the claim is paired with a different paper's abstract.
            other = rng.choice([c for c in pool if c.source_id != base.source_id])
            out.append(Claim(id=f"{base.id}-planted-source", claim=base.claim, source_id=other.source_id,
                             source_title=other.source_title, source_text=other.source_text,
                             gold_label="NOT_ENOUGH_INFO", planted=True, cited_quote="",
                             split=base.split, domain=base.domain))
    return out


PLANTED_PER_SPLIT = {"train": 10, "heldout": 10, "ood": 5}
PLANTED_SEEDS = {"train": 101, "heldout": 202, "ood": 303}


def with_planted(claims: list[Claim], split: str) -> list[Claim]:
    return claims + plant(claims, PLANTED_PER_SPLIT.get(split, 5), PLANTED_SEEDS.get(split, 0))
