import tempfile
import unittest
from pathlib import Path

from core.schema import FileEdit, Proposal
from loop import sandbox


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "editable").mkdir()

    def _prop(self, path, content="x"):
        return Proposal(component="playbook", hypothesis="h", falsifier="f", rationale="r",
                        edits=[FileEdit(path=path, content=content)])

    def test_rejects_parent_traversal(self):
        with self.assertRaises(sandbox.BoundaryViolation):
            sandbox.apply(self._prop("../grader/gate.py"), self.tmp)

    def test_rejects_absolute_path(self):
        with self.assertRaises(sandbox.BoundaryViolation):
            sandbox.apply(self._prop("/etc/passwd"), self.tmp)

    def test_rejects_disallowed_type(self):
        with self.assertRaises(sandbox.BoundaryViolation):
            sandbox.apply(self._prop("hook.sh"), self.tmp)

    def test_rejects_empty(self):
        with self.assertRaises(sandbox.BoundaryViolation):
            sandbox.apply(Proposal("playbook", "h", "f", "r", edits=[]), self.tmp)

    def test_writes_inside_editable(self):
        written = sandbox.apply(self._prop("playbook.md", "- rule\n"), self.tmp)
        self.assertEqual(written, ["playbook.md"])
        self.assertEqual((self.tmp / "editable" / "playbook.md").read_text(), "- rule\n")


if __name__ == "__main__":
    unittest.main()
