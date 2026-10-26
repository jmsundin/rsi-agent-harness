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
WORKER_API_BASE = (env("RATCHET_WORKER_API_BASE") or API_BASE).rstrip("/")
WORKER_API_KEY = env("RATCHET_WORKER_API_KEY") or API_KEY

MODEL_IMPROVER = env("RATCHET_MODEL_IMPROVER", "muse-wonder-1.0")
MODEL_WORKER = env("RATCHET_MODEL_WORKER", "muse-spark-1.3")

# USD per million tokens (input, output). Standard-mode list prices, Oct 2026.
PRICES = {
    "muse-wonder-1.0": (4.00, 20.00),
    "muse-spark-1.3": (1.25, 4.25),
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
