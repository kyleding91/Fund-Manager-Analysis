"""Benchmark regression guard for the screen.

Skips entirely if the live database (data/13f.db) is absent — the offline suite
must pass without it. When the DB is present, it asserts the labeled benchmark in
config/benchmark.yaml holds against the latest quarter: every must_pass filer is
shown and no must_exclude filer is shown. This is the regression guard that locks
in the tuned screen so future changes can't silently regress it.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config                                          # noqa: E402

_DB_PRESENT = config.DB_PATH.exists()


@unittest.skipUnless(_DB_PRESENT, "data/13f.db not present — skipping benchmark guard")
class TestBenchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import evaluate_screen
        from src.database import connect
        cls.evaluate_screen = evaluate_screen
        with connect() as conn:
            if not evaluate_screen.is_rescreened(conn):
                raise unittest.SkipTest(
                    "DB not yet re-screened with firm-type columns — "
                    "run rebuild_universe.py first.")
            quarter = evaluate_screen._latest_quarter(conn)
            cls.report = evaluate_screen.evaluate(conn, quarter)
        cls.quarter = quarter

    def test_all_must_pass_shown(self):
        hidden = self.report["benchmark"]["must_pass_hidden"]
        self.assertEqual(
            hidden, [],
            f"must_pass filers hidden in {self.quarter}: "
            + ", ".join(f"{h['name']} ({h['why']})" for h in hidden))

    def test_no_must_exclude_shown(self):
        shown = self.report["benchmark"]["must_exclude_shown"]
        self.assertEqual(
            shown, [],
            f"must_exclude filers still shown in {self.quarter}: "
            + ", ".join(f"{s['name']} ({s['why']})" for s in shown))

    def test_no_must_pass_hidden_by_mechanical_rule(self):
        mech = self.report["benchmark"]["must_pass_hidden_by_mechanical_rule"]
        self.assertEqual(
            mech, [],
            "must_pass filers hidden purely by a mechanical rule (should only ever "
            "be hidden by explicit curation/firm-type): "
            + ", ".join(f"{m['name']} ({m['why']})" for m in mech))

    def test_false_positives_under_threshold(self):
        self.assertTrue(
            self.report["criteria"]["false_positives_under_threshold"],
            f"suspected false positives {self.report['fp_fraction'] * 100:.1f}% "
            f">= {int(self.evaluate_screen.MAX_FP_FRACTION * 100)}% of the shown universe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
