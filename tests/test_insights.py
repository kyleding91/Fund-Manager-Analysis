"""Offline unit tests for the insight computations (synthetic 2-quarter DB)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import connect, init_db, upsert_fund          # noqa: E402
from src.screener import AggHolding, ScreenedFund               # noqa: E402
from src import insights                                        # noqa: E402


def _fund(cik, name, accession, quarter, period, holdings, date_filed):
    return ScreenedFund(
        cik=cik, manager_name=name, quarter_label=quarter, period_of_report=period,
        form_type="13F-HR", date_filed=date_filed, accession=accession,
        total_aum_usd=sum(h.value_usd for h in holdings),
        num_positions=len(holdings), num_issuers=len(holdings),
        passes_screen=True, holdings=holdings,
    )


def _h(name, cusip, value, shares):
    return AggHolding(name, "COM", cusip, value, shares, "SH", "", 0.0)


class TestInsights(unittest.TestCase):
    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "t.db"
        with connect(self.db) as conn:
            init_db(conn)
            # Fund A: both quarters. Q4 -> Q1 it buys more ALPHA, sells BETA, opens GAMMA.
            upsert_fund(conn, _fund(
                "A", "Alpha Fund", "a-q4", "2024-Q4", "2024-12-31",
                [_h("ALPHA", "AAA000100", 2e9, 1000), _h("BETA", "BBB000200", 1.5e9, 800)],
                "2025-02-14"))
            upsert_fund(conn, _fund(
                "A", "Alpha Fund", "a-q1", "2025-Q1", "2025-03-31",
                [_h("ALPHA", "AAA000100", 2.4e9, 1500),   # added (shares up)
                 _h("GAMMA", "GGG000300", 1e9, 400)],     # new; BETA exited
                "2025-05-15"))
            # Fund B: only Q1 -> a "new manager" this quarter.
            upsert_fund(conn, _fund(
                "B", "Bravo Fund", "b-q1", "2025-Q1", "2025-03-31",
                [_h("ALPHA", "AAA000100", 3e9, 2000)], "2025-05-15"))

    def test_previous_quarter(self):
        with connect(self.db) as conn:
            self.assertEqual(insights.previous_quarter(conn, "2025-Q1"), "2024-Q4")
            self.assertIsNone(insights.previous_quarter(conn, "2024-Q4"))

    def test_most_held(self):
        with connect(self.db) as conn:
            mh = insights.most_held(conn, "2025-Q1")
        top = mh.iloc[0]
        self.assertEqual(top["issuer"], "ALPHA")
        self.assertEqual(top["num_funds"], 2)   # held by both A and B

    def test_new_managers(self):
        with connect(self.db) as conn:
            nm = insights.new_managers(conn, "2025-Q1")
        self.assertListEqual(list(nm["manager_name"]), ["Bravo Fund"])

    def test_qoq_changes(self):
        with connect(self.db) as conn:
            ch = insights.qoq_changes(conn, "A", "2025-Q1")
        kinds = dict(zip(ch["issuer"], ch["change_type"]))
        self.assertEqual(kinds["ALPHA"], "added")
        self.assertEqual(kinds["GAMMA"], "new")
        self.assertEqual(kinds["BETA"], "exited")

    def test_qoq_none_without_prior(self):
        with connect(self.db) as conn:
            self.assertIsNone(insights.qoq_changes(conn, "B", "2025-Q1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
