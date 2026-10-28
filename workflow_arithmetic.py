"""F8 workflow CLI checks. Run: python3 workflow_arithmetic.py

HILLCLIMBER_ARITHMETIC_BIN may select a task-local build with the separately
owned exact median fix, without modifying process.lisp in this worktree.
"""
import json
import math
import os
import pathlib
import unittest
from fractions import Fraction

import integration

if os.environ.get("HILLCLIMBER_ARITHMETIC_BIN"):
    integration.BIN = pathlib.Path(os.environ["HILLCLIMBER_ARITHMETIC_BIN"]).resolve()


class WorkflowArithmetic(unittest.TestCase):
    setUp = integration.Integration.setUp
    git = integration.Integration.git
    cli = integration.Integration.cli
    begin = integration.Integration.begin

    def configure(self, samples, direction="lower", tolerance="0"):
        cases = "".join(f"{i}) n={sample};;\n" for i, sample in enumerate(samples, 1))
        (self.repo / "bench.sh").write_text(
            "case $(ls .auto/runs | wc -l | tr -d ' ') in\n" +
            cases + f"*) n={samples[-1]};;\nesac\n"
            "echo METRIC elapsed_ms=$n\n")
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Arithmetic regression fixture")
        self.cli("init", "--name", "Arithmetic", "--metric", "elapsed_ms",
                 "--direction", direction, "--scope", "src", "--max-runs", "20",
                 "--benchmark", "bench.sh", "--check", "checks.sh",
                 "--tolerance", tolerance)

    def events(self):
        return [json.loads(line) for line in
                (self.repo / ".auto/events.jsonl").read_text().splitlines()]

    def check_baseline(self, samples, score, mad):
        self.configure(samples)
        measured = self.cli("run", "--baseline", "--repeat", str(len(samples)))
        self.assertEqual((measured["score"], measured["mad"]), (score, mad))
        self.assertTrue(all(math.isfinite(measured[k]) for k in ("score", "mad")))
        self.assertEqual(self.cli("status")["best"], score)
        self.assertEqual(self.cli("status")["executions"], len(samples))
        self.assertEqual(self.events()[-1]["mad"], mad)
        journal = self.repo / ".auto/events.jsonl"
        before = journal.read_bytes()
        self.cli("recover")
        self.cli("recover")
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_f8_mad_positive_center_with_opposite_extreme_outlier(self):
        self.check_baseline(["-1e308", "1e308", "1e308"], 1e308, 0)

    def test_f8_mad_negative_center_with_opposite_extreme_outlier(self):
        self.check_baseline(["-1e308", "-1e308", "1e308"], -1e308, 0)

    def test_f8_mad_finite_nonzero_despite_outlier_overflow(self):
        self.check_baseline(["-1e308", "5e307", "9e307", "1e308", "1e308"],
                            9e307, float(Fraction(1e308) - Fraction(9e307)))

    def test_f8_even_mad_finite_near_limit(self):
        self.check_baseline(["-1e308", "-1e308", "1e308", "1e308"], 0, 1e308)

    def test_f8_even_mad_exact_distances_before_rounding(self):
        self.check_baseline(["-1e308", "0", "1e308", "1e308"], 5e307, 5e307)

    def test_f8_mad_subnormal_distances(self):
        self.check_baseline(["0", "1e-323", "2e-323"], 1e-323, 1e-323)

    def test_f8_candidate_mad_is_finite_and_keepable(self):
        self.configure(["1.1e308", "-1e308", "1e308", "1e308"])
        self.cli("run", "--baseline")
        self.begin()
        measured = self.cli("run", "--repeat", "3")
        self.assertEqual((measured["score"], measured["mad"]), (1e308, 0))
        self.assertEqual(self.events()[-1]["type"], "aggregate")
        self.assertEqual(self.events()[-1]["mad"], 0)
        self.cli("decide", "keep", "--reason", "Finite MAD despite opposite outlier")
        self.cli("recover")
        self.cli("recover")
        self.assertEqual(self.cli("status")["best"], 1e308)
        self.assertEqual(self.cli("status")["executions"], 4)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def extreme_keep(self, direction, samples, improved):
        self.configure(samples, direction, "1.7e308")
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        head = self.git("rev-parse", "HEAD")
        if improved:
            self.cli("decide", "keep", "--reason", "Exact predicate exceeds double range")
            self.cli("recover")
            self.cli("recover")
            self.assertEqual(self.cli("status")["best"], float(samples[-1]))
            self.assertEqual([e["type"] for e in self.events()
                              if e["type"] in ("intent", "applied", "resolved")],
                             ["intent", "applied", "resolved"])
            self.assertNotEqual(self.git("rev-parse", "HEAD"), head)
        else:
            journal = self.repo / ".auto/events.jsonl"
            before = journal.read_bytes()
            self.assertEqual(self.cli("decide", "keep", "--reason", "Extreme regression",
                                      expected=3)["code"], "not-improved")
            self.assertEqual(journal.read_bytes(), before)
            self.assertEqual(self.git("rev-parse", "HEAD"), head)
            self.cli("decide", "discard", "--reason", "Preserve accepted score")
            self.assertEqual(self.cli("status")["best"], float(samples[0]))
        self.assertEqual(self.cli("status")["executions"], 2)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_f8_keep_lower_extreme_improvement(self):
        self.extreme_keep("lower", ["1e308", "-1e308"], True)

    def test_f8_keep_higher_extreme_improvement(self):
        self.extreme_keep("higher", ["-1e308", "1e308"], True)

    def test_f8_keep_lower_extreme_regression(self):
        self.extreme_keep("lower", ["-1e308", "1e308"], False)

    def test_f8_keep_higher_extreme_regression(self):
        self.extreme_keep("higher", ["1e308", "-1e308"], False)

    def strict_tolerance(self, direction, samples):
        self.configure(samples, direction, "1")
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        self.assertEqual(self.cli("decide", "keep", "--reason", "Equal to tolerance",
                                  expected=3)["code"], "not-improved")
        self.cli("run")
        self.cli("decide", "keep", "--reason", "Strictly beyond tolerance")
        self.assertEqual(self.cli("status")["best"], float(samples[-1]))

    def test_f8_keep_lower_strict_tolerance_unchanged(self):
        self.strict_tolerance("lower", ["10", "9", "8"])

    def test_f8_keep_higher_strict_tolerance_unchanged(self):
        self.strict_tolerance("higher", ["10", "11", "12"])

    def exact_tolerance_boundary(self, direction, samples):
        self.configure(samples, direction, "1")
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        # The true delta exceeds 1 but rounding it to double would give 1.
        self.cli("decide", "keep", "--reason", "Exact strict improvement")
        self.assertEqual(self.cli("status")["best"], float(samples[-1]))

    def test_f8_keep_lower_compares_exact_delta_at_rounding_boundary(self):
        self.exact_tolerance_boundary("lower", ["1", "-1.1102230246251565e-16"])

    def test_f8_keep_higher_compares_exact_delta_at_rounding_boundary(self):
        self.exact_tolerance_boundary("higher", ["-1", "1.1102230246251565e-16"])


if __name__ == "__main__":
    unittest.main()
