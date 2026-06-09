"""Tests for the curation layer (config/curation.yaml overrides on the screen).

Covers CIK normalisation, the SQL predicate it produces, filter_ciks, the YAML
loader in config, and an end-to-end check that an excluded manager disappears
from the insight queries while the mechanical `passes_screen` flag is untouched.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, curation                                 # noqa: E402
from src.database import connect, init_db, upsert_fund           # noqa: E402
from src.screener import AggHolding, ScreenedFund                # noqa: E402
from src import insights, queries                                # noqa: E402


def _write_curation(text: str) -> Path:
    path = Path(tempfile.mkdtemp()) / "curation.yaml"
    path.write_text(text, encoding="utf-8")
    return path


class TestNormalisation(unittest.TestCase):
    def test_norm_strips_leading_zeros(self):
        self.assertEqual(curation._norm("0001067983"), "1067983")
        self.assertEqual(curation._norm(1067983), "1067983")
        self.assertEqual(curation._norm("1067983"), "1067983")

    def test_norm_all_zeros(self):
        self.assertEqual(curation._norm("0000000"), "0")


class TestCurationOverrides(unittest.TestCase):
    def setUp(self):
        self._orig_path = curation.CURATION_PATH
        curation.reload()

    def tearDown(self):
        curation.CURATION_PATH = self._orig_path
        curation.reload()

    def _use(self, yaml_text: str):
        curation.CURATION_PATH = _write_curation(yaml_text)
        curation.reload()

    def test_empty_predicate(self):
        self._use("exclude:\ninclude:\n")
        self.assertEqual(curation.screen_predicate("f."), "f.passes_screen = 1")
        self.assertEqual(curation.excluded_ciks(), set())
        self.assertEqual(curation.included_ciks(), set())

    def test_exclude_predicate(self):
        self._use("exclude:\n  - cik: 0000102909\n    name: Vanguard\n")
        self.assertEqual(curation.excluded_ciks(), {"102909"})
        pred = curation.screen_predicate("f.")
        self.assertIn("passes_screen = 1", pred)
        self.assertIn("NOT (", pred)
        self.assertIn("'102909'", pred)

    def test_include_predicate(self):
        self._use("include:\n  - cik: 1067983\n")
        pred = curation.screen_predicate("f.")
        self.assertIn("OR", pred)
        self.assertIn("'1067983'", pred)

    def test_filter_ciks(self):
        self._use("exclude:\n  - cik: 200\ninclude:\n  - cik: 999\n")
        out = curation.filter_ciks(["100", "200", "0000300"])
        self.assertEqual(out, {"100", "300", "999"})

    def test_missing_file_is_safe(self):
        curation.CURATION_PATH = Path("/nonexistent/curation.yaml")
        curation.reload()
        self.assertEqual(curation.excluded_ciks(), set())
        self.assertEqual(curation.screen_predicate("f."), "f.passes_screen = 1")


class TestScreenConfigLoader(unittest.TestCase):
    def test_defaults_when_missing(self):
        vals = config._load_screen.__wrapped__() if hasattr(
            config._load_screen, "__wrapped__") else config._load_screen()
        # Loader returns a dict with all four keys regardless of file presence.
        for key in ("min_aum_usd", "max_holdings", "top_n", "top_n_min_pct"):
            self.assertIn(key, vals)

    def test_partial_override(self):
        path = Path(tempfile.mkdtemp()) / "screen.yaml"
        path.write_text("max_holdings: 40\n", encoding="utf-8")
        orig = config.SCREEN_PATH
        try:
            config.SCREEN_PATH = path
            vals = config._load_screen()
            self.assertEqual(vals["max_holdings"], 40)
            # Untouched keys fall back to defaults.
            self.assertEqual(vals["min_aum_usd"], config._SCREEN_DEFAULTS["min_aum_usd"])
        finally:
            config.SCREEN_PATH = orig


def _fund(cik, name, accession, quarter, period, holdings, date_filed, passes=True):
    return ScreenedFund(
        cik=cik, manager_name=name, quarter_label=quarter, period_of_report=period,
        form_type="13F-HR", date_filed=date_filed, accession=accession,
        total_aum_usd=sum(h.value_usd for h in holdings),
        num_positions=len(holdings), num_issuers=len(holdings),
        passes_screen=passes, holdings=holdings,
    )


def _h(name, cusip, value, shares):
    return AggHolding(name, "COM", cusip, value, shares, "SH", "", 0.0)


class TestCurationEndToEnd(unittest.TestCase):
    def setUp(self):
        self._orig_path = curation.CURATION_PATH
        self.db = Path(tempfile.mkdtemp()) / "t.db"
        with connect(self.db) as conn:
            init_db(conn)
            upsert_fund(conn, _fund(
                "100", "Alpha Fund", "a-q1", "2025-Q1", "2025-03-31",
                [_h("ALPHA", "AAA000100", 3e9, 2000)], "2025-05-15"))
            upsert_fund(conn, _fund(
                "200", "Bravo Fund", "b-q1", "2025-Q1", "2025-03-31",
                [_h("ALPHA", "AAA000100", 2e9, 1000)], "2025-05-15"))

    def tearDown(self):
        curation.CURATION_PATH = self._orig_path
        curation.reload()

    def test_excluded_manager_hidden_from_funds_list(self):
        curation.CURATION_PATH = _write_curation("exclude:\n  - cik: 200\n")
        curation.reload()
        with connect(self.db) as conn:
            funds = queries.list_funds(conn, quarter="2025-Q1")
            names = list(funds["manager_name"])
            self.assertIn("Alpha Fund", names)
            self.assertNotIn("Bravo Fund", names)
            # most_held should only count the remaining fund.
            mh = insights.most_held(conn, "2025-Q1")
            self.assertEqual(int(mh.iloc[0]["num_funds"]), 1)
            # The mechanical flag in the DB is untouched (audit trail intact).
            row = conn.execute(
                "SELECT passes_screen FROM filings WHERE cik = '200'").fetchone()
            self.assertEqual(row[0], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
