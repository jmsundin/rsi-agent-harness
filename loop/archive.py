"""Git-backed archive of harness versions.

Every candidate is a commit on a `cand/NNN` branch created from the incumbent; accepted
candidates are merged into `main` (fast-forward). Every evaluated candidate, accepted or
not, gets a line in CHANGELOG.md and a record in runs/results.jsonl. The improver reads the
changelog; the UI reads results.jsonl.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from core import config

CHANGELOG = config.ROOT / "CHANGELOG.md"
RESULTS = config.RUNS_DIR / "results.jsonl"


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=cwd or config.ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def head() -> str:
    return git("rev-parse", "--short", "HEAD")


def next_candidate_id() -> int:
    branches = git("branch", "--list", "cand/*", check=False).split()
    nums = [int(b.split("/")[1]) for b in branches if b.startswith("cand/") and b.split("/")[1].isdigit()]
    return (max(nums) + 1) if nums else 1


def create_worktree(cand_id: int, base_ref: str = "HEAD") -> tuple[Path, str]:
    """Create branch cand/NNN at base_ref and check it out in .worktrees/cand-NNN."""
    config.WORKTREES_DIR.mkdir(exist_ok=True)
    branch = f"cand/{cand_id:03d}"
    path = config.WORKTREES_DIR / f"cand-{cand_id:03d}"
    if path.exists():
        git("worktree", "remove", "--force", str(path), check=False)
    git("worktree", "add", "-b", branch, str(path), base_ref)
    return path, branch


def remove_worktree(path: Path) -> None:
    git("worktree", "remove", "--force", str(path), check=False)


def commit_in(path: Path, message: str) -> str:
    git("add", "-A", "editable", cwd=path)
    git("commit", "-q", "-m", message, cwd=path, check=False)
    return git("rev-parse", "--short", "HEAD", cwd=path)


def diff_editable(path: Path, base_ref: str) -> str:
    return git("diff", base_ref, "--", "editable", cwd=path, check=False)


def accept(branch: str) -> str:
    """Fast-forward main to the accepted candidate."""
    git("merge", "--ff-only", branch)
    return head()


def revert_commit(sha: str, cwd: Path | None = None) -> str:
    """Undo a commit already on main with a new inverse commit (history kept).

    `git revert --no-edit` needs no editor, so the loop can run it unattended;
    it requires a clean working tree and fails (RuntimeError) on conflict.
    Returns the new HEAD.
    """
    git("revert", "--no-edit", sha, cwd=cwd)
    return git("rev-parse", "--short", "HEAD", cwd=cwd)


def tag_rejected(branch: str, cand_id: int) -> None:
    git("tag", "-f", f"rejected/{cand_id:03d}", branch, check=False)


def ensure_changelog() -> None:
    if not CHANGELOG.exists():
        CHANGELOG.write_text("# Changelog\n\nEvery candidate the loop evaluated, newest last. Read by the improver.\n\n")


def log(record: dict[str, Any]) -> None:
    """Append one candidate record to CHANGELOG.md and runs/results.jsonl."""
    ensure_changelog()
    config.RUNS_DIR.mkdir(exist_ok=True)
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **record}
    with RESULTS.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    status = "accepted" if record.get("accepted") else "rejected"
    tr = record.get("train") or {}
    ho = record.get("heldout") or {}
    line = (f"- [{status}] gen {record.get('generation')} cand {record.get('candidate')} "
            f"({record.get('component')}): {record.get('hypothesis')} "
            f"| train {tr.get('composite', '-')} held-out {ho.get('composite', '-')} "
            f"| {record.get('reason')}\n")
    with CHANGELOG.open("a") as f:
        f.write(line)


def log_revert(sha: str, baseline: float, window_rate: float | None, reverted: bool,
               new_head: str = "") -> None:
    """Record a provisional self-edit verdict in CHANGELOG.md and runs/results.jsonl."""
    ensure_changelog()
    config.RUNS_DIR.mkdir(exist_ok=True)
    if reverted:
        line = (f"- [reverted] self-edit {sha}: acceptance {baseline:.0%} -> {window_rate:.0%} "
                f"over the next window; reverted in {new_head}\n")
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "self_edit": True,
                  "self_edit_revert": True, "reverted_sha": sha, "accepted": False,
                  "component": "improver_instructions",
                  "hypothesis": "provisional self-edit under review",
                  "reason": line.strip()[2:]}
    else:
        why = ("no window evidence" if window_rate is None
               else f"acceptance {baseline:.0%} -> {window_rate:.0%}")
        line = f"- [revert-failed] self-edit {sha}: {why}; provisional edit kept, see trace\n"
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "self_edit": True,
                  "self_edit_revert": False, "reverted_sha": sha, "accepted": True,
                  "component": "improver_instructions",
                  "hypothesis": "provisional self-edit under review",
                  "reason": line.strip()[2:]}
    with RESULTS.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    with CHANGELOG.open("a") as f:
        f.write(line)


def read_changelog(max_lines: int = 60) -> str:
    ensure_changelog()
    lines = [l for l in CHANGELOG.read_text().splitlines() if l.startswith("- [")]
    return "\n".join(lines[-max_lines:])


def read_results() -> list[dict[str, Any]]:
    if not RESULTS.exists():
        return []
    return [json.loads(l) for l in RESULTS.read_text().splitlines() if l.strip()]
