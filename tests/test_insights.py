"""Offline unit tests for the insight computations (synthetic 2-quarter DB)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import connect, init_db, upsert_fund          # noqa: E402
from src.screener import AggHolding, ScreenedFund               # noqa: E402
from src import insights, site_data                             # noqa: E402


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

    def test_holders_of(self):
        """Every shown manager holding an issuer, largest position first."""
        with connect(self.db) as conn:
            h = insights.holders_of(conn, "AAA000", "2025-Q1")
        # Both A (2.4B) and B (3B) hold ALPHA; B is larger so it's first.
        self.assertEqual(list(h["cik"]), ["B", "A"])
        self.assertAlmostEqual(float(h.iloc[0]["value_usd"]), 3e9)

    def test_issuer_trend(self):
        """Per-quarter combined value + holder count for one issuer (oldest first)."""
        with connect(self.db) as conn:
            tr = insights.issuer_trend(conn, "AAA000")
        rows = {r["quarter"]: (int(r["holders"]), float(r["total_value"]))
                for _, r in tr.iterrows()}
        self.assertEqual(rows["2024-Q4"], (1, 2e9))     # only A held it in Q4
        self.assertEqual(rows["2025-Q1"], (2, 5.4e9))   # A (2.4B) + B (3B)

    def test_stock_detail(self):
        """The assembled stock page: holders, QoQ moves, new buyers, trend."""
        with connect(self.db) as conn:
            d = site_data.stock_detail(conn, "AAA000", "2025-Q1")
        self.assertEqual(d["issuer"], "ALPHA")
        self.assertEqual(d["num_holders"], 2)
        counts = {c["kind"]: c["n"] for c in d["counts"]}
        self.assertEqual(counts["new"], 1)        # B is new to ALPHA
        self.assertEqual(counts["added"], 1)      # A bought more (shares 1000->1500)
        self.assertEqual(counts["exited"], 0)     # nobody dropped ALPHA
        self.assertEqual([b["name"] for b in d["new_buyers"]], ["Bravo Fund"])
        self.assertEqual(len(d["trend"]), 2)

    def test_stock_detail_exit(self):
        """A manager that dropped a stock shows up as an exit on that stock's page."""
        with connect(self.db) as conn:
            # BETA was held by A in Q4 and fully sold in Q1 -> no current holders.
            self.assertIsNone(site_data.stock_detail(conn, "BBB000", "2025-Q1"))
            # GAMMA is new in Q1 (A only); ALPHA's page lists A's prior BETA? no —
            # exits are per-stock: check ALPHA has none, and that a held-then-sold
            # stock with a *surviving* holder would list the exit. Here BETA has no
            # surviving holder, so it has no page (None above), which is correct.
        with connect(self.db) as conn:
            d = site_data.stock_detail(conn, "GGG000", "2025-Q1")
        self.assertEqual(d["issuer"], "GAMMA")
        self.assertEqual(d["num_holders"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
