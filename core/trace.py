"""Per-run receipt: which model did what, at what cost, in what time. Written as JSONL."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import config


class Trace:
    def __init__(self, run_id: str, directory: Path | None = None):
        self.run_id = run_id
        self.dir = directory or (config.RUNS_DIR / run_id)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "trace.jsonl"
        self.t0 = time.time()

    def event(self, kind: str, **data: Any) -> None:
        rec = {"t": round(time.time() - self.t0, 3), "kind": kind, **data}
        with self.path.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def receipt(self, ledger_snapshot: dict[str, Any], **extra: Any) -> dict[str, Any]:
        r = {"run_id": self.run_id, "elapsed_s": round(time.time() - self.t0, 2),
             "models": {"improver": config.MODEL_IMPROVER, "worker": config.MODEL_WORKER,
                        "worker_provider": config.WORKER_PROVIDER},
             **ledger_snapshot, **extra}
        (self.dir / "receipt.json").write_text(json.dumps(r, indent=2, default=str))
        return r
