import unittest

from core.schema import ScoreReport
from grader import gate


def rep(composite, cost=0.001, **kw):
    base = dict(split="train", n=10, label_acc=composite, planted_caught=composite, nei_recall=composite,
                cost_usd=cost * 10, cost_per_claim=cost, lcb=composite, composite=composite)
    base.update(kw)
    return ScoreReport(**base)


class GateTests(unittest.TestCase):
    def test_rejects_gain_inside_noise(self):
        d = gate.decide(rep(0.52), rep(0.50), best_ever=0.50, delta=0.03)
        self.assertFalse(d.accepted)
        self.assertIn("noise", d.reason)

    def test_rejects_when_below_floor(self):
        d = gate.decide(rep(0.60), rep(0.50), best_ever=0.70, delta=0.03)
        self.assertFalse(d.accepted)
        self.assertIn("floor", d.reason)

    def test_rejects_unearned_cost(self):
        d = gate.decide(rep(0.55, cost=0.003), rep(0.50, cost=0.001), best_ever=0.50, delta=0.03)
        self.assertFalse(d.accepted)
        self.assertIn("cost", d.reason)

    def test_rejects_metric_regression(self):
        cand = rep(0.60, nei_recall=0.2)
        parent = rep(0.50, nei_recall=0.5)
        d = gate.decide(cand, parent, best_ever=0.50, delta=0.03)
        self.assertFalse(d.accepted)
        self.assertIn("regressed", d.reason)

    def test_requires_heldout(self):
        d = gate.decide(rep(0.60), rep(0.50), best_ever=0.50, delta=0.03)
        self.assertFalse(d.accepted)
        self.assertEqual(d.reason, "held-out not evaluated")

    def test_rejects_heldout_flat(self):
        d = gate.decide(rep(0.60), rep(0.50), 0.50, 0.03, cand_heldout=rep(0.51, split="heldout"),
                        parent_heldout=rep(0.50, split="heldout"))
        self.assertFalse(d.accepted)
        self.assertIn("held-out", d.reason)

    def test_accepts_real_gain(self):
        d = gate.decide(rep(0.60), rep(0.50), 0.50, 0.03, cand_heldout=rep(0.58, split="heldout"),
                        parent_heldout=rep(0.50, split="heldout"))
        self.assertTrue(d.accepted)
        self.assertTrue(all(d.checks.values()))

    def test_leakage_short_circuits(self):
        d = gate.decide(rep(0.90), rep(0.50), 0.50, 0.03, leakage_ok=False, leakage_reason="names test item")
        self.assertFalse(d.accepted)
        self.assertEqual(list(d.checks), ["leakage"])

    def test_noise_estimate_floor(self):
        self.assertGreaterEqual(gate.estimate_noise([0.5, 0.5, 0.5], save=False), 0.01)
        self.assertAlmostEqual(gate.estimate_noise([0.5, 0.6], save=False), 0.1, places=3)


if __name__ == "__main__":
    unittest.main()
