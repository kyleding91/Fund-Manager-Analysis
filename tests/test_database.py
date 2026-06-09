"""Offline unit tests for the SQLite storage layer."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import (connect, init_db, upsert_fund,        # noqa: E402
                          record_screen, stats)
from src.screener import AggHolding, ScreenedFund               # noqa: E402


def _fund(accession, date_filed, form_type="13F-HR", aum=3e9, name="Test Capital"):
    return ScreenedFund(
        cik="999", manager_name=name, quarter_label="2025-Q1",
        period_of_report="2025-03-31", form_type=form_type, date_filed=date_filed,
        accession=accession, total_aum_usd=aum, num_positions=2, num_issuers=2,
        passes_screen=True,
        holdings=[
            AggHolding("ALPHA CORP", "COM", "000000100", 2e9, 1000, "SH", "", 66.7),
            AggHolding("BETA INC", "COM", "000000200", 1e9, 500, "SH", "", 33.3),
        ],
    )


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "t.db"

    def test_insert_and_stats(self):
        with connect(self.tmp) as conn:
            init_db(conn)
            upsert_fund(conn, _fund("acc-1", "2025-05-15"))
            s = stats(conn)
        self.assertEqual(s["funds"], 1)
        self.assertEqual(s["filings"], 1)
        self.assertEqual(s["holdings"], 2)

    def test_idempotent_reload(self):
        """Loading the same accession twice must not duplicate rows."""
        with connect(self.tmp) as conn:
            init_db(conn)
            upsert_fund(conn, _fund("acc-1", "2025-05-15"))
            upsert_fund(conn, _fund("acc-1", "2025-05-15"))  # again
            s = stats(conn)
        self.assertEqual(s["filings"], 1)
        self.assertEqual(s["holdings"], 2)

    def test_quarter_screen_ledger(self):
        """record_screen writes one upsertable row per (cik, quarter)."""
        passer = _fund("acc-1", "2025-05-15")
        passer.top_n_pct = 100.0
        passer.meets_count = True
        passer.passes_screen = True
        # A non-qualifier we still want to log in the ledger.
        failer = _fund("acc-2", "2025-05-15", name="Too Broad LP")
        failer.cik = "888"
        failer.num_issuers = 120
        failer.passes_screen = False
        with connect(self.tmp) as conn:
            init_db(conn)
            record_screen(conn, passer)
            record_screen(conn, failer)
            record_screen(conn, passer)  # idempotent upsert, no duplicate
            rows = conn.execute(
                "SELECT cik, passes_screen FROM quarter_screen ORDER BY cik"
            ).fetchall()
            n_pass = conn.execute(
                "SELECT COUNT(*) FROM quarter_screen WHERE passes_screen=1"
            ).fetchone()[0]
        self.assertEqual(len(rows), 2)            # 2 distinct managers
        self.assertEqual(n_pass, 1)               # only the qualifier passes

    def test_amendment_supersedes(self):
        """A later 13F-HR/A for the same period becomes current; original is not."""
        with connect(self.tmp) as conn:
            init_db(conn)
            upsert_fund(conn, _fund("acc-1", "2025-05-15", "13F-HR"))
            upsert_fund(conn, _fund("acc-2", "2025-06-10", "13F-HR/A", aum=3.5e9))
            rows = conn.execute(
                "SELECT accession, is_current FROM filings ORDER BY date_filed"
            ).fetchall()
            current = conn.execute(
                "SELECT accession FROM filings WHERE is_current=1"
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["accession"], "acc-2")  # amendment wins


if __name__ == "__main__":
    unittest.main(verbosity=2)
