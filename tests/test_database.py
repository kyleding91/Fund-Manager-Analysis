"""Offline unit tests for the SQLite storage layer."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import (connect, init_db, upsert_fund,        # noqa: E402
                          record_screen, stats, sync_filings_screen)
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

    def test_filer_type_and_reject_reason_persist(self):
        """upsert_fund + record_screen store the firm-type and reject-reason."""
        passer = _fund("acc-1", "2025-05-15")
        passer.filer_type = "Investment Manager"
        failer = _fund("acc-2", "2025-05-15", name="One Stock Co")
        failer.cik = "888"
        failer.passes_screen = False
        failer.filer_type = "Holding Company"
        failer.reject_reason = "below_min_holdings"
        with connect(self.tmp) as conn:
            init_db(conn)
            upsert_fund(conn, passer)
            record_screen(conn, passer)
            record_screen(conn, failer)
            ft = conn.execute(
                "SELECT filer_type FROM filings WHERE accession='acc-1'").fetchone()[0]
            fund_ft = conn.execute(
                "SELECT filer_type FROM funds WHERE cik='999'").fetchone()[0]
            qrow = conn.execute(
                "SELECT filer_type, reject_reason FROM quarter_screen WHERE cik='888'"
            ).fetchone()
        self.assertEqual(ft, "Investment Manager")
        self.assertEqual(fund_ft, "Investment Manager")
        self.assertEqual(qrow["filer_type"], "Holding Company")
        self.assertEqual(qrow["reject_reason"], "below_min_holdings")

    def test_migration_adds_new_columns(self):
        """init_db migrates an older DB that lacks filer_type / reject_reason."""
        import sqlite3
        # Simulate a pre-existing DB with the OLD schema: all the original columns
        # (and the indexes that reference them), but NOT the new filer_type /
        # reject_reason columns this migration adds.
        conn = sqlite3.connect(str(self.tmp))
        conn.executescript(
            """CREATE TABLE funds (cik TEXT PRIMARY KEY, manager_name TEXT);
               CREATE TABLE filings (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   cik TEXT NOT NULL, accession TEXT UNIQUE NOT NULL, form_type TEXT,
                   quarter_label TEXT, period_of_report TEXT, date_filed TEXT,
                   total_aum_usd REAL, num_positions INTEGER, num_issuers INTEGER,
                   top_n_pct REAL, passes_screen INTEGER, is_current INTEGER DEFAULT 1,
                   loaded_at TEXT);
               CREATE TABLE quarter_screen (cik TEXT NOT NULL, quarter_label TEXT NOT NULL,
                   period_of_report TEXT, manager_name TEXT, total_aum_usd REAL,
                   num_positions INTEGER, num_issuers INTEGER, top_n_pct REAL,
                   meets_count INTEGER, meets_weight INTEGER, passes_screen INTEGER,
                   updated_at TEXT, PRIMARY KEY (cik, quarter_label));
               CREATE TABLE holdings (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   filing_id INTEGER NOT NULL, cusip TEXT, issuer_cusip TEXT,
                   name_of_issuer TEXT, title_of_class TEXT, value_usd REAL,
                   shares REAL, shares_type TEXT, put_call TEXT, pct_of_portfolio REAL);""")
        conn.commit()
        conn.close()
        with connect(self.tmp) as conn:
            init_db(conn)  # should ALTER in the new columns
            fcols = {r[1] for r in conn.execute("PRAGMA table_info(filings)")}
            fundcols = {r[1] for r in conn.execute("PRAGMA table_info(funds)")}
            qcols = {r[1] for r in conn.execute("PRAGMA table_info(quarter_screen)")}
        self.assertIn("filer_type", fcols)
        self.assertIn("filer_type", fundcols)
        self.assertIn("filer_type", qcols)
        self.assertIn("reject_reason", qcols)

    def test_sync_filings_screen_clears_stale_pass(self):
        """A filing left passes_screen=1 by an old screen is corrected from the ledger.

        Reproduces the staleness bug: a filer's holdings were stored when it
        passed (filings.passes_screen=1), then a later re-screen under tightened
        rules records passes_screen=0 in the quarter_screen ledger but does NOT
        re-store the filing. sync_filings_screen must copy the ledger verdict
        (and firm_type) back onto the stored filing so it leaves the curated set.
        """
        with connect(self.tmp) as conn:
            init_db(conn)
            # Filing stored as a passer (the stale state).
            sf = _fund("acc-1", "2025-05-15")
            sf.passes_screen = True
            upsert_fund(conn, sf)
            # Fresh re-screen says it now FAILS and is a holding company.
            failed = _fund("acc-1", "2025-05-15")
            failed.passes_screen = False
            failed.filer_type = "Holding Company"
            failed.reject_reason = "below_min_holdings"
            record_screen(conn, failed)

            before = conn.execute(
                "SELECT passes_screen FROM filings WHERE accession='acc-1'"
            ).fetchone()[0]
            n = sync_filings_screen(conn)
            row = conn.execute(
                "SELECT passes_screen, filer_type FROM filings WHERE accession='acc-1'"
            ).fetchone()
        self.assertEqual(before, 1)                 # was stale-passing
        self.assertEqual(n, 1)                      # one row reconciled
        self.assertEqual(row["passes_screen"], 0)   # now correctly failing
        self.assertEqual(row["filer_type"], "Holding Company")

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
