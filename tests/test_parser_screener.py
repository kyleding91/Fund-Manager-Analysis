"""Offline unit tests for parsing + screening (no network needed)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config                             # noqa: E402
from src.parser import parse_submission           # noqa: E402
from src import screener                            # noqa: E402
from src.screener import screen_filing             # noqa: E402


def _submission(holdings_xml: str, *, prefix: str = "", manager="Test Capital LP",
                period="03-31-2025", value_total="3000000000", entry_total="2") -> str:
    """Build a minimal SGML submission with a cover page + information table."""
    p = f"{prefix}:" if prefix else ""
    ns = f' xmlns:{prefix}="http://www.sec.gov/edgar/thirteenffiler"' if prefix else ""
    return f"""<SEC-DOCUMENT>
<DOCUMENT>
<TYPE>13F-HR
<XML>
<edgarSubmission>
  <headerData><filerInfo><periodOfReport>{period}</periodOfReport></filerInfo></headerData>
  <formData>
    <coverPage><filingManager><name>{manager}</name></filingManager></coverPage>
    <summaryPage><tableValueTotal>{value_total}</tableValueTotal><tableEntryTotal>{entry_total}</tableEntryTotal></summaryPage>
  </formData>
</edgarSubmission>
</XML>
</DOCUMENT>
<DOCUMENT>
<TYPE>INFORMATION TABLE
<XML>
<{p}informationTable{ns}>
{holdings_xml}
</{p}informationTable>
</XML>
</DOCUMENT>
</SEC-DOCUMENT>"""


def _entry(name, cusip, value, shares, prefix=""):
    p = f"{prefix}:" if prefix else ""
    return f"""<{p}infoTable>
  <{p}nameOfIssuer>{name}</{p}nameOfIssuer>
  <{p}titleOfClass>COM</{p}titleOfClass>
  <{p}cusip>{cusip}</{p}cusip>
  <{p}value>{value}</{p}value>
  <{p}shrsOrPrnAmt><{p}sshPrnamt>{shares}</{p}sshPrnamt><{p}sshPrnamtType>SH</{p}sshPrnamtType></{p}shrsOrPrnAmt>
</{p}infoTable>"""


class TestParser(unittest.TestCase):
    def test_basic_parse(self):
        xml = _entry("ALPHA CORP", "000000100", "2000000000", "1000") + \
              _entry("BETA INC", "000000200", "1000000000", "500")
        pf = parse_submission(_submission(xml), cik="1", form_type="13F-HR",
                              date_filed="2025-05-15", accession="acc-1")
        self.assertEqual(pf.manager_name, "Test Capital LP")
        self.assertEqual(pf.period_of_report, "2025-03-31")
        self.assertEqual(pf.quarter_label, "2025-Q1")
        self.assertEqual(len(pf.holdings), 2)
        self.assertEqual(pf.reported_entry_total, 2)

    def test_namespace_prefixed(self):
        """Filings that use namespace prefixes (<ns1:infoTable>) must still parse."""
        xml = _entry("ALPHA CORP", "000000100", "2000000000", "1000", prefix="ns1")
        pf = parse_submission(_submission(xml, prefix="ns1"), cik="1",
                              form_type="13F-HR", date_filed="2025-05-15", accession="a")
        self.assertEqual(len(pf.holdings), 1)
        self.assertEqual(pf.holdings[0].name_of_issuer, "ALPHA CORP")


class TestScreener(unittest.TestCase):
    def test_aggregates_duplicate_cusip(self):
        """Two rows for the same security (shared managers) collapse into one."""
        xml = _entry("ALPHA CORP", "000000100", "1500000000", "1000") + \
              _entry("ALPHA CORP", "000000100", "1500000000", "1000")
        pf = parse_submission(_submission(xml), cik="1", form_type="13F-HR",
                              date_filed="2025-05-15", accession="a")
        sf = screen_filing(pf)
        self.assertEqual(sf.num_positions, 1)
        self.assertEqual(sf.holdings[0].value_usd, 3_000_000_000)
        self.assertAlmostEqual(sf.holdings[0].pct_of_portfolio, 100.0)

    def test_units_pre2023_thousands(self):
        """A filing before the 2023 cutover is multiplied by 1000."""
        xml = _entry("ALPHA CORP", "000000100", "3000000", "1000")  # 3,000,000 thousand
        pf = parse_submission(_submission(xml), cik="1", form_type="13F-HR",
                              date_filed="2022-05-15", accession="a")
        sf = screen_filing(pf)
        self.assertEqual(sf.total_aum_usd, 3_000_000_000)  # $3B after x1000

    def test_screen_pass_concentrated(self):
        # 3 issuers (at the min_holdings floor), $2.5B total, concentrated.
        xml = (_entry("ALPHA CORP", "100000100", "1500000000", "1000")
               + _entry("BETA INC", "200000200", "700000000", "500")
               + _entry("GAMMA LLC", "300000300", "300000000", "300"))
        pf = parse_submission(_submission(xml, entry_total="3"), cik="1",
                              form_type="13F-HR", date_filed="2025-05-15", accession="a")
        self.assertTrue(screen_filing(pf).passes_screen)

    def test_screen_fail_small_aum(self):
        xml = _entry("ALPHA CORP", "000000100", "1000000000", "1000")  # only $1B
        pf = parse_submission(_submission(xml), cik="1", form_type="13F-HR",
                              date_filed="2025-05-15", accession="a")
        self.assertFalse(screen_filing(pf).passes_screen)

    def test_screen_fail_confidential_omitted(self):
        """A confidential-treatment filing (holdings omitted) must NOT pass.

        Such filings report a big cover-page total but only a placeholder row
        (value 0, cusip 000000000). They were previously slipping through as a
        giant '1-issuer' fund via the cover-page fallback.
        """
        placeholder = _entry("NA", "000000000", "0", "0")
        sub = _submission(placeholder, value_total="864690921985", entry_total="1507")
        sub = sub.replace(
            "<isConfidentialOmitted>",  # no-op if absent
            "<isConfidentialOmitted>",
        )
        # inject the confidential flag into the summary page
        sub = sub.replace("</tableEntryTotal>",
                          "</tableEntryTotal><isConfidentialOmitted>true</isConfidentialOmitted>")
        pf = parse_submission(sub, cik="1374170", form_type="13F-HR",
                              date_filed="2026-05-11", accession="conf")
        sf = screen_filing(pf)
        self.assertTrue(pf.is_confidential)
        self.assertEqual(sf.num_positions, 0)       # placeholder row dropped
        self.assertEqual(sf.total_aum_usd, 0)       # no cover-page fallback
        self.assertFalse(sf.passes_screen)

    def test_screen_fail_too_many_issuers(self):
        xml = "".join(
            _entry(f"CO{i}", f"{i:06d}100", "100000000", "10") for i in range(35)
        )  # 35 issuers, $3.5B, evenly spread -> top 10 only ~29%
        pf = parse_submission(_submission(xml, entry_total="35"), cik="1",
                              form_type="13F-HR", date_filed="2025-05-15", accession="a")
        sf = screen_filing(pf)
        self.assertEqual(sf.num_issuers, 35)
        self.assertFalse(sf.meets_count)
        self.assertFalse(sf.meets_weight)
        self.assertFalse(sf.passes_screen)

    def test_screen_pass_exactly_30_issuers(self):
        """The issuer test is inclusive: exactly 30 distinct issuers passes."""
        xml = "".join(
            _entry(f"CO{i}", f"{i:06d}100", "100000000", "10") for i in range(30)
        )  # 30 issuers, $3.0B
        pf = parse_submission(_submission(xml, entry_total="30"), cik="1",
                              form_type="13F-HR", date_filed="2025-05-15", accession="a")
        sf = screen_filing(pf)
        self.assertEqual(sf.num_issuers, 30)
        self.assertTrue(sf.meets_count)
        self.assertTrue(sf.passes_screen)

    def test_screen_pass_heavy_top_ten(self):
        """A long tail still passes if the top 10 are >= 80% of AUM."""
        # 10 big names at $1B each ($10B) + 40 tiny names at $10M each ($0.4B).
        big = "".join(_entry(f"BIG{i}", f"{i:06d}100", "1000000000", "10")
                      for i in range(10))
        tail = "".join(_entry(f"TAIL{i}", f"9{i:05d}100", "10000000", "10")
                       for i in range(40))
        pf = parse_submission(_submission(big + tail, entry_total="50"), cik="1",
                              form_type="13F-HR", date_filed="2025-05-15", accession="a")
        sf = screen_filing(pf)
        self.assertEqual(sf.num_issuers, 50)
        self.assertFalse(sf.meets_count)        # too many issuers
        self.assertGreaterEqual(sf.top_n_pct, 80.0)
        self.assertTrue(sf.meets_weight)        # but concentrated up top
        self.assertTrue(sf.passes_screen)

    def test_mostly_etfs_fails(self):
        """A concentrated-looking book that is mostly ETFs is a passive basket."""
        # 3 distinct issuers, all ETFs, $3B -> looks "concentrated" (3 names,
        # top-10 100%) but is 100% index funds, so it must NOT pass.
        xml = (_entry("ISHARES CORE S&P 500 ETF", "100000100", "1500000000", "10")
               + _entry("VANGUARD TOTAL STOCK MKT", "200000200", "900000000", "10")
               + _entry("SPDR S&P 500 ETF TRUST", "300000300", "600000000", "10"))
        pf = parse_submission(_submission(xml, entry_total="3"), cik="1",
                              form_type="13F-HR", date_filed="2025-05-15", accession="a")
        sf = screen_filing(pf)
        self.assertEqual(sf.num_issuers, 3)
        self.assertGreaterEqual(sf.etf_pct, 50.0)
        self.assertFalse(sf.passes_screen)
        self.assertEqual(sf.reject_reason, screener.REJECT_MOSTLY_ETFS)

    def test_small_etf_sleeve_still_passes(self):
        """A genuine stock-picker with a minor ETF sleeve still passes."""
        # 3 real names ($2.4B) + one small hedge ETF ($0.3B) -> ETF ~11%, passes.
        xml = (_entry("ALPHA CORP", "100000100", "1200000000", "10")
               + _entry("BETA INC", "200000200", "800000000", "10")
               + _entry("GAMMA LLC", "300000300", "400000000", "10")
               + _entry("SPDR GOLD SHARES", "400000400", "300000000", "10"))
        pf = parse_submission(_submission(xml, entry_total="4"), cik="1",
                              form_type="13F-HR", date_filed="2025-05-15", accession="a")
        sf = screen_filing(pf)
        self.assertLess(sf.etf_pct, 50.0)
        self.assertTrue(sf.passes_screen)

    def test_weight_branch_fails_above_ceiling(self):
        """A top-heavy book with more than MAX_HOLDINGS_WEIGHTED issuers fails.

        This is the long-tail mutual-fund-complex case: top 10 are >= 80% of AUM,
        but the total number of names is far too large to be a focused book.
        """
        n_tail = config.MAX_HOLDINGS_WEIGHTED + 20  # comfortably over the ceiling
        big = "".join(_entry(f"BIG{i}", f"{i:06d}100", "1000000000", "10")
                      for i in range(10))
        tail = "".join(_entry(f"TAIL{i}", f"9{i:05d}100", "1000000", "10")
                       for i in range(n_tail))
        total = 10 + n_tail
        pf = parse_submission(_submission(big + tail, entry_total=str(total)), cik="1",
                              form_type="13F-HR", date_filed="2025-05-15", accession="a")
        sf = screen_filing(pf)
        self.assertEqual(sf.num_issuers, total)
        self.assertGreater(sf.num_issuers, config.MAX_HOLDINGS_WEIGHTED)
        self.assertGreaterEqual(sf.top_n_pct, 80.0)
        self.assertFalse(sf.meets_weight)       # too many names for the weight branch
        self.assertFalse(sf.meets_count)
        self.assertFalse(sf.passes_screen)
        self.assertEqual(sf.reject_reason, screener.REJECT_WEIGHT_HOLDINGS)


class TestRejectReason(unittest.TestCase):
    def _screen(self, xml, *, entry_total, date="2025-05-15"):
        pf = parse_submission(_submission(xml, entry_total=str(entry_total)), cik="1",
                              form_type="13F-HR", date_filed=date, accession="a")
        return screen_filing(pf)

    def test_pass_has_empty_reason(self):
        xml = (_entry("ALPHA CORP", "100000100", "1500000000", "1000")
               + _entry("BETA INC", "200000200", "700000000", "500")
               + _entry("GAMMA LLC", "300000300", "300000000", "300"))
        self.assertEqual(self._screen(xml, entry_total=3).reject_reason, "")

    def test_aum_below_floor_reason(self):
        xml = _entry("ALPHA CORP", "000000100", "1000000000", "1000")  # $1B
        sf = self._screen(xml, entry_total=1)
        self.assertFalse(sf.passes_screen)
        self.assertEqual(sf.reject_reason, screener.REJECT_AUM)

    def test_not_concentrated_reason(self):
        xml = "".join(
            _entry(f"CO{i}", f"{i:06d}100", "100000000", "10") for i in range(35)
        )  # 35 issuers, evenly spread → neither branch
        sf = self._screen(xml, entry_total=35)
        self.assertFalse(sf.passes_screen)
        self.assertEqual(sf.reject_reason, screener.REJECT_NOT_CONCENTRATED)

    def test_below_min_holdings_reason(self):
        # $3B AUM but fewer than min_holdings distinct names → a single-/double-
        # stake vehicle, not a portfolio. Rejected by the holdings floor.
        xml = (_entry("ALPHA CORP", "100000100", "2000000000", "1000")
               + _entry("BETA INC", "200000200", "1000000000", "500"))  # 2 issuers
        sf = self._screen(xml, entry_total=2)
        self.assertEqual(sf.num_issuers, 2)
        self.assertLess(sf.num_issuers, config.MIN_HOLDINGS)
        self.assertFalse(sf.passes_screen)
        self.assertEqual(sf.reject_reason, screener.REJECT_MIN_HOLDINGS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
