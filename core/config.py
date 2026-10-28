"""Configuration from environment. Loads .env if present; env vars win."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


MOCK = env("RATCHET_MOCK", "0") == "1"

API_BASE = env("MODEL_API_BASE", "https://api.meta.ai/v1").rstrip("/")
API_KEY = env("MODEL_API_KEY", "")

# Worker (judge / sceptic) routing. Three ways, most specific wins:
#   1. RATCHET_WORKER_API_BASE / RATCHET_WORKER_API_KEY / RATCHET_MODEL_WORKER set explicitly.
#   2. BASETEN_API_KEY set: route workers to Muse Spark Open on Baseten's Model API.
#      The hackathon key is scoped to exactly this model ID.
#   3. Neither: workers use the Meta Model API alongside the improver.
BASETEN_API_BASE = "https://inference.baseten.co/v1"
BASETEN_MODEL = "meta-models/muse-spark-open-1026"
BASETEN_API_KEY = env("BASETEN_API_KEY", "")

if env("RATCHET_WORKER_API_BASE"):
    WORKER_API_BASE = env("RATCHET_WORKER_API_BASE").rstrip("/")
    WORKER_API_KEY = env("RATCHET_WORKER_API_KEY") or API_KEY
    _worker_default = "muse-spark-1.3"
elif BASETEN_API_KEY:
    WORKER_API_BASE = BASETEN_API_BASE
    WORKER_API_KEY = BASETEN_API_KEY
    _worker_default = BASETEN_MODEL
else:
    WORKER_API_BASE = API_BASE
    WORKER_API_KEY = API_KEY
    _worker_default = "muse-spark-1.3"

MODEL_IMPROVER = env("RATCHET_MODEL_IMPROVER", "muse-wonder-1.0")
WORKER_PROVIDER = "baseten" if WORKER_API_BASE.startswith(BASETEN_API_BASE) else "meta"
if WORKER_PROVIDER == "baseten":
    # The hackathon Baseten key serves exactly one model; a Meta API ID left in .env
    # (e.g. muse-spark-1.3) would 404 there, so the Baseten route always pins the model.
    MODEL_WORKER = BASETEN_MODEL
else:
    MODEL_WORKER = env("RATCHET_MODEL_WORKER", _worker_default)

# USD per million tokens (input, output). Standard-mode list prices, Oct 2026.
# Spark Open on Baseten is billed against hackathon credits at the listed rate; the ledger
# still charges it so caps and cost-per-claim stay comparable across providers.
PRICES = {
    "muse-wonder-1.0": (4.00, 20.00),
    "muse-spark-1.3": (1.25, 4.25),
    BASETEN_MODEL: (1.25, 4.25),
    "mock": (0.0, 0.0),
}

CAP_PER_RUN = float(env("RATCHET_CAP_PER_RUN", "3.00"))
CAP_PER_GENERATION = float(env("RATCHET_CAP_PER_GENERATION", "1.50"))
CAP_TOTAL = float(env("RATCHET_CAP_TOTAL", "120.00"))

CACHE_DIR = ROOT / ".cache"
RUNS_DIR = ROOT / "runs"
EDITABLE_DIR = ROOT / "editable"
GRADER_DIR = ROOT / "grader"
WORKTREES_DIR = ROOT / ".worktrees"

# Fixed reasoning effort for the inner loop (HSI: no extra thinking at task time).
WORKER_REASONING = env("RATCHET_WORKER_REASONING", "low")
IMPROVER_REASONING = env("RATCHET_IMPROVER_REASONING", "high")
