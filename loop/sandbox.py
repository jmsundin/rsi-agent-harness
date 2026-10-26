"""Apply a proposal inside a worktree and score it in a subprocess.

Boundary rules (HSI's frozen anchor, enforced here, not by trust):
- an edit path must resolve inside <worktree>/editable/ (no `..`, no absolute paths);
- the frozen files are compared against main after the edit; any change rejects the candidate;
- `run_claims` must still import and keep its signature;
- the scoring subprocess gets a scrubbed environment: the model key and base URL only.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core import config
from core.schema import Proposal

FROZEN = ("core", "grader", "loop", "eval", "research", "ui")


class BoundaryViolation(RuntimeError):
    pass


def apply(proposal: Proposal, worktree: Path) -> list[str]:
    editable = (worktree / "editable").resolve()
    written = []
    for e in proposal.edits:
        target = (editable / e.path).resolve()
        if editable not in target.parents and target != editable:
            raise BoundaryViolation(f"edit outside editable/: {e.path}")
        if target.suffix not in (".md", ".py", ".txt"):
            raise BoundaryViolation(f"disallowed file type: {e.path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(e.content)
        written.append(e.path)
    if not written:
        raise BoundaryViolation("proposal contained no edits")
    return written


def check_frozen(worktree: Path, base_ref: str) -> None:
    r = subprocess.run(["git", "diff", "--name-only", base_ref, "--", *FROZEN],
                       cwd=worktree, capture_output=True, text=True)
    changed = [l for l in r.stdout.splitlines() if l.strip()]
    if changed:
        raise BoundaryViolation(f"frozen files changed: {changed}")


def smoke(worktree: Path) -> None:
    """Import the candidate harness and check the interface before spending on scoring."""
    code = ("import importlib.util,sys;sys.path.insert(0,%r);"
            "s=importlib.util.spec_from_file_location('h',%r);m=importlib.util.module_from_spec(s);"
            "s.loader.exec_module(m);import inspect;"
            "assert list(inspect.signature(m.run_claims).parameters)==['claims','llm'],'signature changed'"
            % (str(config.ROOT), str(worktree / "editable" / "harness" / "run.py")))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise BoundaryViolation(f"harness failed to import: {r.stderr.strip()[-400:]}")


def _env() -> dict[str, str]:
    keep = ("MODEL_API_KEY", "MODEL_API_BASE", "RATCHET_WORKER_API_BASE", "RATCHET_WORKER_API_KEY",
            "RATCHET_MODEL_WORKER", "RATCHET_MODEL_IMPROVER", "RATCHET_MOCK", "RATCHET_WORKER_REASONING",
            "PATH", "HOME", "LANG")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def score_in_subprocess(worktree: Path, split: str, runs: int, seed: int, cap: float,
                        limit: int | None = None) -> dict:
    """Run eval.run from the MAIN checkout against the candidate's editable tree."""
    reports = config.RUNS_DIR / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    out = reports / f"{worktree.name}-{split}-{seed}.json"
    cmd = [sys.executable, "-I", str(config.ROOT / "eval" / "run.py"), "--split", split,
           "--editable", str(worktree / "editable"), "--runs", str(runs), "--seed", str(seed),
           "--out", str(out)]
    if limit:
        cmd += ["--limit", str(limit)]
    env = _env()
    env["RATCHET_CAP_PER_RUN"] = str(cap)
    r = subprocess.run(cmd, cwd=config.ROOT, env=env, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"scoring failed: {r.stderr.strip()[-600:]}")
    return json.loads(out.read_text())
