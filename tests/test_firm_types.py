"""Tests for the firm-type layer (heuristic + per-CIK overrides in YAML).

Covers the name heuristic (including the new MUTUAL_FUND category), per-CIK
override resolution from config/firm_types.yaml, the default/extended excluded
firm-type set, and that excluded types drive the curation predicate.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import classify, curation                              # noqa: E402


def _write_firm_types(text: str) -> Path:
    path = Path(tempfile.mkdtemp()) / "firm_types.yaml"
    path.write_text(text, encoding="utf-8")
    return path


class TestHeuristic(unittest.TestCase):
    def test_manager_names(self):
        self.assertEqual(classify.firm_type_heuristic("Pershing Square Capital Management, L.P."),
                         classify.MANAGER)
        self.assertEqual(classify.firm_type_heuristic("Akre Capital Management LLC"),
                         classify.MANAGER)

    def test_mutual_fund_complex(self):
        self.assertEqual(classify.firm_type_heuristic("Acme Index Fund Trust"),
                         classify.MUTUAL_FUND)
        self.assertEqual(classify.firm_type_heuristic("Big Mutual Funds, Inc."),
                         classify.MUTUAL_FUND)

    def test_allowlisted_manager_not_mistaken(self):
        # Fundsmith contains "FUND" but is an allow-listed genuine manager.
        self.assertEqual(classify.firm_type_heuristic("Fundsmith Investment Services Ltd."),
                         classify.MANAGER)

    def test_market_maker(self):
        self.assertEqual(classify.firm_type_heuristic("Belvedere Trading LLC"),
                         classify.MARKET_MAKER)


class TestEtfDetection(unittest.TestCase):
    def test_etf_sponsor_names(self):
        for name in ("iShares Core S&P 500 ETF", "VANGUARD TOTAL STOCK MKT",
                     "SPDR S&P 500 ETF TRUST", "Invesco QQQ Trust",
                     "DIMENSIONAL US CORE EQUITY", "Schwab Strategic Tr"):
            self.assertTrue(classify.is_etf_name(name), name)

    def test_real_companies_not_flagged(self):
        for name in ("APPLE INC", "BERKSHIRE HATHAWAY INC", "MICROSOFT CORP",
                     "JPMORGAN CHASE & CO", "ALPHABET INC"):
            self.assertFalse(classify.is_etf_name(name), name)


class TestOverrides(unittest.TestCase):
    def setUp(self):
        self._orig = classify.FIRM_TYPES_PATH
        classify.reload()

    def tearDown(self):
        classify.FIRM_TYPES_PATH = self._orig
        classify.reload()

    def _use(self, text: str):
        classify.FIRM_TYPES_PATH = _write_firm_types(text)
        classify.reload()

    def test_per_cik_override_wins(self):
        # A name that looks like a manager, force-tagged as a holding company.
        self._use("overrides:\n  - cik: 316011\n    type: Holding Company\n")
        self.assertEqual(classify.firm_type("316011", "Lilly Endowment Inc"),
                         classify.HOLDING_COMPANY)
        # Integer CIK input resolves the same.
        self.assertEqual(classify.firm_type(316011, "Lilly Endowment Inc"),
                         classify.HOLDING_COMPANY)

    def test_per_cik_override_leading_zeros(self):
        # A quoted leading-zero CIK still normalises to the same manager.
        self._use("overrides:\n  - cik: '0000102909'\n    type: Mutual Fund / Advisor Complex\n")
        self.assertEqual(classify.firm_type("102909", "Vanguard Group Inc"),
                         classify.MUTUAL_FUND)

    def test_invalid_override_type_ignored(self):
        self._use("overrides:\n  - cik: 123\n    type: Not A Real Type\n")
        # Falls back to heuristic rather than storing a bogus type.
        self.assertEqual(classify.firm_type("123", "Generic Capital Management"),
                         classify.MANAGER)

    def test_default_excluded_types(self):
        self._use("overrides:\n")
        self.assertEqual(classify.excluded_firm_types(), (classify.MARKET_MAKER,))

    def test_extended_excluded_types(self):
        self._use("excluded_types:\n  - Market Maker / Broker\n  - Mutual Fund / Advisor Complex\n")
        excluded = set(classify.excluded_firm_types())
        self.assertIn(classify.MARKET_MAKER, excluded)
        self.assertIn(classify.MUTUAL_FUND, excluded)

    def test_excluded_types_drive_predicate(self):
        self._use("excluded_types:\n  - Mutual Fund / Advisor Complex\n")
        curation.reload()
        pred = curation.screen_predicate("f.")
        self.assertIn("Mutual Fund / Advisor Complex", pred)
        self.assertIn("COALESCE(f.filer_type", pred)
        curation.reload()


if __name__ == "__main__":
    unittest.main(verbosity=2)
