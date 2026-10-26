"""Model client.

Talks to any OpenAI-compatible chat endpoint (Meta Model API by default) with urllib,
caches every response on disk keyed by (model, messages, params), charges every call to a
ledger with hard dollar caps, and offers a deterministic mock so the whole loop runs offline.

Design notes
- No SDK: the chat-completions request is a JSON POST; keeping it explicit keeps the
  harness auditable and dependency-free.
- The ledger is the enforcement point for RATCHET_CAP_*; a call that would exceed a cap
  raises BudgetExceeded before any network I/O.
- Reasoning effort is a per-role setting (HSI): workers run at fixed low effort so
  gains can't come from thinking longer at task time; the improver runs at high effort.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import config


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Ledger:
    """Tracks spend. One per process; scoped (run/generation) via snapshots."""
    total_usd: float = 0.0
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cap_total: float = config.CAP_TOTAL
    cap_scope: float = config.CAP_PER_RUN
    scope_usd: float = 0.0
    scope_name: str = "run"
    history: list[dict[str, Any]] = field(default_factory=list)

    def begin_scope(self, name: str, cap: float) -> None:
        self.scope_name, self.cap_scope, self.scope_usd = name, cap, 0.0

    def charge(self, model: str, tin: int, tout: int) -> float:
        pin, pout = config.PRICES.get(model, (4.0, 20.0))
        usd = (tin * pin + tout * pout) / 1_000_000
        if self.scope_usd + usd > self.cap_scope:
            raise BudgetExceeded(f"{self.scope_name} cap {self.cap_scope:.2f} USD exceeded")
        if self.total_usd + usd > self.cap_total:
            raise BudgetExceeded(f"total cap {self.cap_total:.2f} USD exceeded")
        self.total_usd += usd
        self.scope_usd += usd
        self.calls += 1
        self.tokens_in += tin
        self.tokens_out += tout
        self.history.append({"t": time.time(), "model": model, "in": tin, "out": tout, "usd": usd})
        return usd

    def snapshot(self) -> dict[str, Any]:
        return {"total_usd": round(self.total_usd, 6), "scope_usd": round(self.scope_usd, 6),
                "calls": self.calls, "tokens_in": self.tokens_in, "tokens_out": self.tokens_out}


LEDGER = Ledger()


def _cache_key(model: str, messages: list[dict], params: dict) -> str:
    blob = json.dumps({"m": model, "msgs": messages, "p": params}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


class Cache:
    def __init__(self, directory: Path):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> dict | None:
        p = self.dir / f"{key}.json"
        if p.exists():
            try:
                return json.loads(p.read_text())
            except json.JSONDecodeError:
                return None
        return None

    def put(self, key: str, value: dict) -> None:
        (self.dir / f"{key}.json").write_text(json.dumps(value))


CACHE = Cache(config.CACHE_DIR)


@dataclass
class Reply:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    usd: float
    cached: bool

    def json(self) -> Any:
        """Parse the reply as JSON, tolerating code fences and leading prose."""
        t = self.text.strip()
        if t.startswith("```"):
            t = t.split("```", 2)[1]
            if t.startswith("json"):
                t = t[4:]
        start = t.find("{")
        end = t.rfind("}")
        if start != -1 and end != -1:
            t = t[start:end + 1]
        return json.loads(t)


# ---- mock model ---------------------------------------------------------------------------

MockFn = Callable[[str, list[dict], dict], str]
_MOCK_HANDLERS: list[tuple[str, MockFn]] = []


def register_mock(marker: str, fn: MockFn) -> None:
    """Register a handler used when RATCHET_MOCK=1 and the system prompt contains `marker`."""
    _MOCK_HANDLERS.append((marker, fn))


def _mock_reply(model: str, messages: list[dict], params: dict) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    for marker, fn in _MOCK_HANDLERS:
        if marker in system:
            return fn(model, messages, params)
    return '{"error": "no mock handler"}'


# ---- public API ---------------------------------------------------------------------------

def chat(messages: list[dict], *, role: str = "worker", model: str | None = None,
         temperature: float = 0.0, max_tokens: int = 1200, json_mode: bool = False,
         seed: int = 0, use_cache: bool = True) -> Reply:
    """One chat completion. `role` is 'worker' or 'improver' and picks model, endpoint, effort."""
    if role == "improver":
        model = model or config.MODEL_IMPROVER
        base, key, effort = config.API_BASE, config.API_KEY, config.IMPROVER_REASONING
    else:
        model = model or config.MODEL_WORKER
        base, key, effort = config.WORKER_API_BASE, config.WORKER_API_KEY, config.WORKER_REASONING

    params = {"temperature": temperature, "max_tokens": max_tokens, "json": json_mode,
              "seed": seed, "effort": effort}

    if config.MOCK:
        text = _mock_reply(model, messages, params)
        tin = sum(len(m["content"]) for m in messages) // 4
        tout = len(text) // 4
        usd = LEDGER.charge("mock", tin, tout)
        return Reply(text, "mock", tin, tout, usd, cached=False)

    ck = _cache_key(model, messages, params)
    if use_cache:
        hit = CACHE.get(ck)
        if hit:
            return Reply(hit["text"], model, hit["tin"], hit["tout"], 0.0, cached=True)

    # Pre-charge an estimate so the cap check happens before the network call.
    est_in = sum(len(m["content"]) for m in messages) // 4
    LEDGER.charge(model, est_in, 0)

    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature,
                            "max_tokens": max_tokens, "seed": seed}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if effort:
        body["reasoning_effort"] = effort

    req = urllib.request.Request(
        f"{base}/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST")

    last_err: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f"model call failed after retries: {last_err}")

    text = data["choices"][0]["message"]["content"] or ""
    usage = data.get("usage", {})
    tin = int(usage.get("prompt_tokens", est_in))
    tout = int(usage.get("completion_tokens", len(text) // 4))
    # Settle: we pre-charged est_in input tokens; charge the remainder and the output.
    usd = LEDGER.charge(model, max(0, tin - est_in), tout)
    if use_cache:
        CACHE.put(ck, {"text": text, "tin": tin, "tout": tout})
    return Reply(text, model, tin, tout, usd, cached=False)
