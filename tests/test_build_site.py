"""Smoke test for the static-site generator (build_site.py).

Builds a tiny synthetic two-quarter database, points the generator at it, and
asserts that the expected pages are produced with the expected content. This is
a guard against template/render regressions — it does not hit the network.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import connect, init_db, upsert_fund          # noqa: E402
from src.screener import AggHolding, ScreenedFund               # noqa: E402
from rosterless import no_roster, restore_roster   # noqa: E402
from src import config                                          # noqa: E402


def _h(name, cusip, value, shares):
    return AggHolding(name, "COM", cusip, value, shares, "SH", "", 0.0)


def _fund(cik, name, accession, quarter, period, holdings, date_filed):
    return ScreenedFund(
        cik=cik, manager_name=name, quarter_label=quarter, period_of_report=period,
        form_type="13F-HR", date_filed=date_filed, accession=accession,
        total_aum_usd=sum(h.value_usd for h in holdings),
        num_positions=len(holdings), num_issuers=len(holdings),
        passes_screen=True, holdings=holdings,
    )


class TestBuildSite(unittest.TestCase):
    def setUp(self):
        no_roster()  # build from the mechanical screen, not the repo roster
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "t.db"
        with connect(self.db) as conn:
            init_db(conn)
            # One concentrated manager present in both quarters so the fund page
            # exercises both the AUM timeline and the QoQ-moves section.
            upsert_fund(conn, _fund(
                "1112520", "Akre Capital Management LLC", "ak-q4", "2024-Q4",
                "2024-12-31",
                [_h("MASTERCARD", "57636Q104", 3.0e9, 1000),
                 _h("MOODYS", "615369105", 2.5e9, 800)],
                "2025-02-14"))
            upsert_fund(conn, _fund(
                "1112520", "Akre Capital Management LLC", "ak-q1", "2025-Q1",
                "2025-03-31",
                [_h("MASTERCARD", "57636Q104", 3.6e9, 1500),   # added
                 _h("KKR", "48251W104", 2.1e9, 900)],          # new (Moodys exited)
                "2025-05-15"))
            # A second manager only in the latest quarter (a "new manager").
            upsert_fund(conn, _fund(
                "0001067983", "Berkshire Hathaway Inc", "bh-q1", "2025-Q1",
                "2025-03-31",
                [_h("APPLE", "037833100", 90e9, 5000),
                 _h("AMERICAN EXPRESS", "025816109", 40e9, 1000)],
                "2025-05-15"))

        # Point the generator's config at our throwaway DB.
        self._orig_db = config.DB_PATH
        config.DB_PATH = self.db

    def tearDown(self):
        restore_roster()
        config.DB_PATH = self._orig_db

    def test_build_produces_expected_pages(self):
        import importlib
        from src import site_data
        importlib.reload(site_data)          # pick up the patched DB_PATH
        import build_site
        importlib.reload(build_site)

        out = self.tmp / "site"
        res = build_site.build(out, quarter="2025-Q1")

        # Top-level pages exist.
        for name in ("index.html", "funds.html", "stocks.html", "methodology.html"):
            self.assertTrue((out / name).exists(), f"missing {name}")
        # Assets copied.
        self.assertTrue((out / "assets" / "style.css").exists())
        self.assertTrue((out / "assets" / "app.js").exists())
        # .nojekyll present for GitHub Pages.
        self.assertTrue((out / ".nojekyll").exists())
        # Service worker gets a unique cache version stamped per build (so a
        # redeploy invalidates returning visitors' old offline caches).
        sw = (out / "sw.js").read_text(encoding="utf-8")
        self.assertNotIn('const CACHE = "valueflow-v1"', sw)
        self.assertIn('const CACHE = "valueflow-2025q1-', sw)
        self.assertIn('"moves.html"', sw)
        # CSV export present.
        self.assertTrue((out / "data" / "managers-2025q1.csv").exists())

        # Per-fund pages for both managers — in BOTH language trees.
        akre = out / "funds" / "1112520.html"                            # en default
        self.assertTrue(akre.exists())
        self.assertTrue((out / "zh" / "funds" / "1112520.html").exists())
        self.assertTrue((out / "funds" / "0001067983.html").exists())
        self.assertTrue((out / "zh" / "funds" / "0001067983.html").exists())

        # Per-stock page (MASTERCARD, issuer CUSIP 57636Q) exists, names its
        # holder, links back to that manager, and the most-held page links to it.
        stock = out / "stocks" / "57636Q.html"
        self.assertTrue(stock.exists())
        stock_html = stock.read_text(encoding="utf-8")
        self.assertIn("MASTERCARD", stock_html)
        self.assertIn("Akre Capital Management", stock_html)
        self.assertIn("../funds/1112520.html", stock_html)
        stocks_html = (out / "stocks.html").read_text(encoding="utf-8")
        self.assertIn("stocks/57636Q.html", stocks_html)
        # zh mirror has the same stock page and link.
        self.assertTrue((out / "zh" / "stocks" / "57636Q.html").exists())
        self.assertIn("stocks/57636Q.html",
                      (out / "zh" / "stocks.html").read_text(encoding="utf-8"))

        # The quarterly money-moves page exists, is linked in the nav, and
        # names the manager behind a move.
        moves = out / "moves.html"
        self.assertTrue(moves.exists())
        moves_html = moves.read_text(encoding="utf-8")
        self.assertIn("How money moved this quarter", moves_html)
        self.assertIn("Akre Capital Management", moves_html)   # KKR new buy
        home = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="moves.html"', home)

        # Generator reports the right shape.
        self.assertEqual(res["quarter"], "2025-Q1")
        self.assertEqual(res["funds"], 2)
        self.assertGreaterEqual(res["pages"], 6)
        self.assertGreaterEqual(res["stocks"], 1)

        # Home pages carry the brand; English is the default at the root, the
        # Chinese mirror lives under /zh/, each links to its counterpart.
        home_en = (out / "index.html").read_text(encoding="utf-8")
        home_zh = (out / "zh" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Value Flow", home_en)
        self.assertIn('lang="en"', home_en)
        self.assertIn("Most-held stocks", home_en)
        self.assertIn('href="zh/index.html"', home_en)       # switch to zh
        self.assertIn('lang="zh-CN"', home_zh)
        self.assertIn("热门持仓", home_zh)                   # zh UI string
        self.assertIn('href="../index.html"', home_zh)       # switch back to en

        # Akre's page shows the QoQ moves (KKR is new, Moodys exited).
        akre_html = akre.read_text(encoding="utf-8")
        self.assertIn("Akre Capital Management", akre_html)
        self.assertIn("MASTERCARD", akre_html)
        self.assertIn("Quarter-over-quarter", akre_html)

        # Holdings table links to the original filing on SEC EDGAR. CIK has no
        # leading zeros; the accession appears with dashes (filename) and the
        # folder uses it without dashes.
        self.assertIn(
            "https://www.sec.gov/Archives/edgar/data/1112520/akq1/ak-q1-index.htm",
            akre_html)
        self.assertIn("filing on SEC EDGAR", akre_html)

        # Multi-quarter view: Akre has two quarters on record, so there's a
        # quarter selector and a panel per quarter (newest first).
        self.assertIn('id="quarter-chips"', akre_html)
        self.assertIn('data-q="2025q1"', akre_html)
        self.assertIn('data-q="2024q4"', akre_html)
        # Holdings appear before the QoQ-moves heading within a panel.
        self.assertLess(akre_html.index("Holdings &mdash;"),
                        akre_html.index("Quarter-over-quarter moves"))
        # The earliest quarter has no prior filing, so it shows the fallback note
        # rather than a moves table — proving every quarter has a QoQ section.
        self.assertIn("earliest quarter on record", akre_html)

        # A single-quarter manager (Berkshire) still renders a QoQ section, just
        # with the no-comparison note — the view is consistent for all managers.
        bh_html = (out / "funds" / "0001067983.html").read_text(encoding="utf-8")
        self.assertIn("Quarter-over-quarter moves", bh_html)
        self.assertIn("earliest quarter on record", bh_html)


if __name__ == "__main__":
    unittest.main()
