import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from loop import archive, run


class FakeTrace:
    def __init__(self):
        self.events = []

    def event(self, name, **kw):
        self.events.append((name, kw))


def pending_state(baseline=0.5, window=(True, False, False), sha="abc1234"):
    return {
        "self_edit_baseline": baseline,
        "self_edit_sha": sha,
        "self_edit_gen": 4,
        "self_edit_due_gen": 8,
        "self_edit_window": list(window),
    }


class ShouldRevertTests(unittest.TestCase):
    def test_reverts_when_window_did_not_beat_baseline(self):
        self.assertTrue(run.self_edit_should_revert(0.5, [True, False, False]))

    def test_reverts_on_flat_window(self):
        # "does not beat" includes exactly matching the baseline.
        self.assertTrue(run.self_edit_should_revert(0.5, [True, False]))

    def test_keeps_when_window_beats_baseline(self):
        self.assertFalse(run.self_edit_should_revert(0.5, [True, True, False]))

    def test_keeps_when_no_window_evidence(self):
        self.assertFalse(run.self_edit_should_revert(0.5, []))


class MaybeRevertTests(unittest.TestCase):
    def test_noop_before_due_generation(self):
        state = pending_state()
        with mock.patch.object(archive, "revert_commit") as rev:
            self.assertFalse(run.maybe_revert_self_edit(6, state, FakeTrace()))
        rev.assert_not_called()
        self.assertEqual(state["self_edit_sha"], "abc1234")

    def test_noop_without_pending_self_edit(self):
        with mock.patch.object(archive, "revert_commit") as rev:
            self.assertFalse(run.maybe_revert_self_edit(8, {}, FakeTrace()))
        rev.assert_not_called()

    def test_reverts_and_clears_state_when_window_regressed(self):
        state = pending_state(window=(True, False, False))
        trace = FakeTrace()
        with mock.patch.object(archive, "revert_commit", return_value="def5678") as rev, \
                mock.patch.object(archive, "log_revert") as log_rev:
            self.assertTrue(run.maybe_revert_self_edit(8, state, trace))
        rev.assert_called_once_with("abc1234")
        log_rev.assert_called_once()
        self.assertNotIn("self_edit_sha", state)
        self.assertTrue(any(name == "self_edit_reverted" for name, _ in trace.events))

    def test_keeps_and_clears_state_when_window_improved(self):
        state = pending_state(window=(True, True, False))
        with mock.patch.object(archive, "revert_commit") as rev, \
                mock.patch.object(archive, "log_revert"):
            self.assertFalse(run.maybe_revert_self_edit(8, state, FakeTrace()))
        rev.assert_not_called()
        self.assertNotIn("self_edit_sha", state)

    def test_failed_revert_is_logged_not_raised(self):
        state = pending_state(window=(False, False, False))
        trace = FakeTrace()
        with mock.patch.object(archive, "revert_commit", side_effect=RuntimeError("conflict")), \
                mock.patch.object(archive, "git"), \
                mock.patch.object(archive, "log_revert") as log_rev:
            self.assertFalse(run.maybe_revert_self_edit(8, state, trace))
        log_rev.assert_called_once()
        self.assertTrue(any(name == "self_edit_revert_failed" for name, _ in trace.events))


class RevertCommitTests(unittest.TestCase):
    def test_revert_commit_undoes_without_rewriting_history(self):
        tmp = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
        (tmp / "f.txt").write_text("one\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=tmp, check=True)
        (tmp / "f.txt").write_text("two\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "self-edit"], cwd=tmp, check=True)
        bad_sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=tmp,
                                 capture_output=True, text=True, check=True).stdout.strip()

        new_head = archive.revert_commit(bad_sha, cwd=tmp)

        self.assertEqual((tmp / "f.txt").read_text(), "one\n")
        count = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=tmp,
                               capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(count, "3")  # base + self-edit + revert: history not rewritten
        self.assertNotEqual(new_head, bad_sha)


if __name__ == "__main__":
    unittest.main()
