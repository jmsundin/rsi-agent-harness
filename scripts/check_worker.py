"""Smoke-test the worker endpoint with one tiny call and print the receipt.

    python -m scripts.check_worker

Uses whatever core.config resolved (BASETEN_API_KEY -> Spark Open on Baseten, etc.).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config, llm  # noqa: E402


def main() -> None:
    print(f"worker provider : {config.WORKER_PROVIDER}")
    print(f"worker endpoint : {config.WORKER_API_BASE}")
    print(f"worker model    : {config.MODEL_WORKER}")
    print(f"key present     : {'yes' if config.WORKER_API_KEY else 'NO'}")
    if not config.WORKER_API_KEY:
        raise SystemExit("no worker key; set BASETEN_API_KEY or RATCHET_WORKER_API_KEY in .env")
    r = llm.chat([{"role": "system", "content": "Reply with JSON only."},
                  {"role": "user", "content": 'Return {"ok": true, "model_family": "<your model family>"}'}],
                 role="worker", json_mode=True, max_tokens=60, use_cache=False)
    print(f"reply           : {r.text}")
    print(f"tokens in/out   : {r.tokens_in}/{r.tokens_out}   ledger usd: {r.usd:.6f}")


if __name__ == "__main__":
    main()
