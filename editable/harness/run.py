"""The claim-checking workflow. Editable by the improver (rung 3).

FIXED INTERFACE (do not change):
    run_claims(claims: list[Claim], llm) -> list[Verdict]

`llm` is a callable with the signature of core.llm.chat. The harness must get every model
call through it so cost is charged and cached. Files it reads live next to this one.

Stages (gen-0):
 1. quote_match  deterministic: does the model's quote appear verbatim in the source?
 2. judge        Spark labels the claim against the source, citing a quote.
 3. sceptic      Spark argues against the verdict; may downgrade to NOT_ENOUGH_INFO.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from core.schema import Claim, Verdict

HERE = Path(__file__).resolve().parent
EDITABLE = HERE.parent


def _read(rel: str) -> str:
    return (EDITABLE / rel).read_text()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def quote_match(quote: str, source: str, threshold: float = 0.92) -> bool:
    """True if `quote` appears in `source` (exact after whitespace/case normalisation, or a
    near-exact window match). Deterministic; no model involved."""
    q, s = _norm(quote), _norm(source)
    if not q or len(q) < 12:
        return False
    if q in s:
        return True
    # Sliding window near-match to tolerate small punctuation differences.
    w = len(q)
    best = 0.0
    step = max(1, w // 8)
    for i in range(0, max(1, len(s) - w + 1), step):
        r = difflib.SequenceMatcher(None, q, s[i:i + w]).ratio()
        if r > best:
            best = r
            if best >= threshold:
                return True
    return best >= threshold


def _judge(claim: Claim, llm) -> dict:
    system = _read("prompts/judge.md").replace("{playbook}", _read("playbook.md"))
    user = (f"CLAIM: {claim.claim}\n\nSOURCE TITLE: {claim.source_title}\n\nSOURCE:\n{claim.source_text}")
    if claim.cited_quote:
        user += f"\n\nThe claim's author cites this passage as support: \"{claim.cited_quote}\""
    reply = llm([{"role": "system", "content": system}, {"role": "user", "content": user}],
                role="worker", json_mode=True, max_tokens=400)
    try:
        out = reply.json()
    except Exception:
        out = {"label": "NOT_ENOUGH_INFO", "quote": "", "confidence": 0.3, "rationale": "unparseable"}
    out["_usd"] = reply.usd
    return out


def _sceptic(claim: Claim, verdict: Verdict, llm) -> dict:
    system = _read("prompts/sceptic.md")
    user = (f"CLAIM: {claim.claim}\n\nSOURCE:\n{claim.source_text}\n\nVERDICT: {verdict.label}\n"
            f"QUOTE: {verdict.quote}\nRATIONALE: {verdict.rationale}")
    reply = llm([{"role": "system", "content": system}, {"role": "user", "content": user}],
                role="worker", json_mode=True, max_tokens=300)
    try:
        out = reply.json()
    except Exception:
        out = {"keep": True, "revised_label": verdict.label, "objection": ""}
    out["_usd"] = reply.usd
    return out


def run_claims(claims: list[Claim], llm) -> list[Verdict]:
    verdicts: list[Verdict] = []
    for c in claims:
        j = _judge(c, llm)
        v = Verdict(claim_id=c.id, label=str(j.get("label", "NOT_ENOUGH_INFO")).upper(),
                    quote=str(j.get("quote", "")), confidence=float(j.get("confidence", 0.5) or 0.5),
                    rationale=str(j.get("rationale", "")), cost_usd=j["_usd"])
        if v.label not in ("SUPPORTS", "REFUTES", "NOT_ENOUGH_INFO"):
            v.label = "NOT_ENOUGH_INFO"
            v.flags.append("bad_label")

        # Stage 1: deterministic quote check. A SUPPORTS/REFUTES verdict without a real quote is rejected.
        v.quote_found = quote_match(v.quote, c.source_text)
        if v.label in ("SUPPORTS", "REFUTES") and not v.quote_found:
            v.flags.append("quote_missing")
            v.label = "REJECTED"
            verdicts.append(v)
            continue

        # Stage 3: sceptic pass only on confident SUPPORTS/REFUTES verdicts.
        if v.label in ("SUPPORTS", "REFUTES"):
            s = _sceptic(c, v, llm)
            v.cost_usd += s["_usd"]
            if not s.get("keep", True):
                rl = str(s.get("revised_label", "NOT_ENOUGH_INFO")).upper()
                v.flags.append("sceptic_downgrade")
                v.label = rl if rl in ("SUPPORTS", "REFUTES", "NOT_ENOUGH_INFO") else "NOT_ENOUGH_INFO"
                v.rationale += f" | sceptic: {s.get('objection', '')}"
        verdicts.append(v)
    return verdicts
