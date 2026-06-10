"""Tests for the sticky membership roster (config/roster.yaml).

Covers the core semantics the project owner chose:
  * a member that LAPSES (fails the current screen) stays shown;
  * a passing filer that is NOT a member is not shown (it joins via the
    roster-update step in rebuild_universe, never implicitly);
  * removed members are never auto-re-added;
  * without a roster file everything falls back to the per-quarter screen.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import curation, insights, queries, roster              # noqa: E402
from src.database import connect, init_db, record_screen, upsert_fund  # noqa: E402
from src.screener import AggHolding, ScreenedFund                # noqa: E402

ROSTER_YAML = """\
members:
  - cik: 100
    name: Alpha Fund
    joined: 2024-Q4
    added_by: screen
    status: active
  - cik: 300
    name: Charlie Fund
    joined: 2024-Q4
    added_by: screen
    status: removed
    removed_quarter: 2025-Q1
    reason: drifted into an index-like book
"""


def _fund(cik, name, accession, passes, reject=""):
    sf = ScreenedFund(
        cik=cik, manager_name=name, quarter_label="2025-Q1",
        period_of_report="2025-03-31", form_type="13F-HR",
        date_filed="2025-05-15", accession=accession,
        total_aum_usd=3e9, num_positions=3, num_issuers=3,
        passes_screen=passes,
        holdings=[AggHolding("X CORP", "COM", "X00000100", 1e9, 10, "SH", "", 33.3),
                  AggHolding("Y CORP", "COM", "Y00000200", 1e9, 10, "SH", "", 33.3),
                  AggHolding("Z CORP", "COM", "Z00000300", 1e9, 10, "SH", "", 33.3)],
    )
    sf.reject_reason = reject
    return sf


class TestRosterMembership(unittest.TestCase):
    def setUp(self):
        self._orig = roster.ROSTER_PATH
        roster.ROSTER_PATH = Path(tempfile.mkdtemp()) / "roster.yaml"
        roster.ROSTER_PATH.write_text(ROSTER_YAML, encoding="utf-8")
        roster.reload()
        curation.reload()

        self.db = Path(tempfile.mkdtemp()) / "t.db"
        with connect(self.db) as conn:
            init_db(conn)
            # Alpha: roster member that LAPSED this quarter (fails the screen).
            a = _fund("100", "Alpha Fund", "a-q1", False, "aum_below_floor")
            upsert_fund(conn, a)
            record_screen(conn, a)
            # Bravo: passes the screen but is NOT (yet) on the roster.
            b = _fund("200", "Bravo Fund", "b-q1", True)
            upsert_fund(conn, b)
            record_screen(conn, b)

    def tearDown(self):
        roster.ROSTER_PATH = self._orig
        roster.reload()
        curation.reload()

    def test_lapsed_member_stays_shown(self):
        with connect(self.db) as conn:
            names = list(queries.list_funds(conn, quarter="2025-Q1")["manager_name"])
        self.assertIn("Alpha Fund", names)        # lapsed but sticky
        self.assertNotIn("Bravo Fund", names)     # qualifier, not yet admitted

    def test_lapsed_listed_for_review(self):
        with connect(self.db) as conn:
            # Need a prior quarter for screen_changes; fake one via Alpha's record.
            a_prev = _fund("100", "Alpha Fund", "a-q4", True)
            a_prev.quarter_label = "2024-Q4"
            a_prev.period_of_report = "2024-12-31"
            upsert_fund(conn, a_prev)
            record_screen(conn, a_prev)
            chg = insights.screen_changes(conn, "2025-Q1")
        lapsed = {r["manager_name"]: r["reject_reason"] for r in chg["lapsed"]}
        self.assertEqual(lapsed, {"Alpha Fund": "aum_below_floor"})
        self.assertEqual(chg["entered"], [])      # nobody joined in 2025-Q1
        self.assertEqual(chg["left"], [])         # nobody auto-leaves, ever

    def test_removed_member_not_resurrected(self):
        added = roster.add_members([
            {"cik": "100", "name": "Alpha Fund", "joined": "2025-Q1"},   # dup
            {"cik": "300", "name": "Charlie Fund", "joined": "2025-Q1"},  # removed
            {"cik": "400", "name": "Delta Fund", "joined": "2025-Q1"},    # new
        ])
        self.assertEqual(added, 1)                          # only Delta
        self.assertIn("400", roster.active_ciks())
        self.assertNotIn("300", roster.active_ciks())       # stays removed
        self.assertEqual(roster.joined_in("2025-Q1"), {"400"})

    def test_predicate_uses_membership_not_passes(self):
        pred = curation.screen_predicate("f.")
        self.assertNotIn("passes_screen", pred)
        self.assertIn("'100'", pred)              # active member in the IN-list
        self.assertNotIn("'300'", pred)           # removed member is not

    def test_fallback_without_roster(self):
        roster.ROSTER_PATH = Path(tempfile.mkdtemp()) / "absent.yaml"
        roster.reload()
        pred = curation.screen_predicate("f.")
        self.assertIn("f.passes_screen = 1", pred)
        with connect(self.db) as conn:
            names = list(queries.list_funds(conn, quarter="2025-Q1")["manager_name"])
        self.assertEqual(names, ["Bravo Fund"])   # mechanical screen only


if __name__ == "__main__":
    unittest.main(verbosity=2)
