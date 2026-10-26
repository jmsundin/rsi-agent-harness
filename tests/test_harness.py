import os
import unittest

os.environ["RATCHET_MOCK"] = "1"

from core import llm, mock  # noqa: E402
from core.schema import Claim  # noqa: E402
from editable.harness.run import quote_match, run_claims  # noqa: E402
from grader import data, planted, score  # noqa: E402

SRC = ("Background: debated. Methods: we treated worms. Results: Treatment increased lifespan relative to "
       "vehicle controls (p = 0.01). Conclusions: it works.")


class QuoteMatchTests(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(quote_match("Treatment increased lifespan relative to vehicle controls", SRC))

    def test_case_and_whitespace(self):
        self.assertTrue(quote_match("treatment  INCREASED lifespan relative to vehicle controls", SRC))

    def test_fabricated(self):
        self.assertFalse(quote_match("Survival was extended by 31% in the intervention arm.", SRC))

    def test_too_short(self):
        self.assertFalse(quote_match("Results", SRC))


class HarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mock.install()

    def test_fabricated_citation_is_rejected(self):
        c = Claim(id="t1", claim="In worms, treatment increased lifespan.", source_id="d", source_title="t",
                  source_text=SRC, gold_label="SUPPORTS", planted=True,
                  cited_quote="Survival was extended by 31% in the intervention arm.")
        v = run_claims([c], llm.chat)[0]
        # gen-0 mock judge is fooled by the citation; the deterministic quote check catches it.
        self.assertEqual(v.label, "REJECTED")
        self.assertIn("quote_missing", v.flags)

    def test_scoring_runs_on_all_splits(self):
        for split in ("train", "heldout", "ood"):
            claims = planted.with_planted(data.load_split(split), split)
            rep = score.score(claims, run_claims(claims, llm.chat), split)
            self.assertEqual(rep.n, len(claims))
            self.assertTrue(0.0 <= rep.composite <= 1.0)

    def test_planted_claims_are_separate_from_gold(self):
        claims = data.load_split("train")
        p = planted.plant(claims, 4, seed=1)
        self.assertEqual(len(p), 4)
        self.assertTrue(all(c.planted for c in p))
        self.assertFalse(any(c.planted for c in claims))


if __name__ == "__main__":
    unittest.main()
