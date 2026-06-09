"""Unit tests for the filer-type classifier."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.classify import (                                # noqa: E402
    classify_manager, is_investment_manager, label,
    MANAGER, FOUNDATION, PENSION, BANK, MARKET_MAKER, OPERATING,
)


class TestClassify(unittest.TestCase):
    def test_allow_list_overrides_corp_suffix(self):
        # Famous stock-pickers whose names look like operating companies.
        for name in ("BERKSHIRE HATHAWAY INC", "Icahn Enterprises", "Markel Group Inc",
                     "Carlyle Group Inc.", "PAULSON & CO. INC.", "Lindsell Train Ltd",
                     "FUNDSMITH INVESTMENT SERVICES LTD.", "Matson Money. Inc."):
            self.assertEqual(classify_manager(name), MANAGER, name)

    def test_investor_keyword_managers(self):
        # "INVESTORS" / "INVESTMENT" keywords rescue managers from the Corp bucket.
        for name in ("H&F Corporate Investors X, Ltd.", "First Beijing Investment Ltd"):
            self.assertEqual(classify_manager(name), MANAGER, name)

    def test_permanent_fund_is_pension(self):
        self.assertEqual(classify_manager("TEXAS PERMANENT SCHOOL FUND CORP"), PENSION)

    def test_managers(self):
        for name in ("Pershing Square Capital Management LP",
                     "Akre Capital Management",
                     "Baupost Group LLC",
                     "Tiger Global Management LLC",
                     "Viking Global Investors LP",
                     "Lone Pine Capital LLC"):
            self.assertEqual(classify_manager(name), MANAGER, name)

    def test_foundations_and_endowments(self):
        for name in ("Bill & Melinda Gates Foundation Trust",
                     "Yale University",
                     "The Regents of the University of California",
                     "Howard Hughes Medical Institute"):
            self.assertEqual(classify_manager(name), FOUNDATION, name)

    def test_pensions_and_sovereign(self):
        for name in ("California Public Employees Retirement System",
                     "Ontario Teachers Pension Plan Board",
                     "Public Investment Fund",
                     "State of Wisconsin Investment Board",
                     "National Pension Service"):
            self.assertEqual(classify_manager(name), PENSION, name)

    def test_market_makers(self):
        for name in ("Citadel Securities LLC",
                     "Susquehanna International Group",
                     "Jane Street Group LLC",
                     "Virtu Financial"):
            self.assertEqual(classify_manager(name), MARKET_MAKER, name)

    def test_banks_and_insurers(self):
        for name in ("JPMorgan Chase Bank",
                     "Prudential Insurance Co",
                     "Northwestern Mutual Life Ins"):
            self.assertEqual(classify_manager(name), BANK, name)

    def test_operating_companies(self):
        # No manager keyword + a corporate suffix => operating company.
        for name in ("Microsoft Corporation",
                     "Apple Inc",
                     "Eni S.p.A. PLC"):
            self.assertEqual(classify_manager(name), OPERATING, name)

    def test_empty_defaults_to_manager(self):
        self.assertEqual(classify_manager(""), MANAGER)
        self.assertEqual(classify_manager(None), MANAGER)

    def test_helpers(self):
        self.assertTrue(is_investment_manager("Pershing Square Capital Management"))
        self.assertFalse(is_investment_manager("Yale University"))
        self.assertTrue(label("Yale University").startswith("🎓"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
