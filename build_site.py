#!/usr/bin/env python3
"""Generate the static website from the 13F database — BILINGUAL.

Reads the screened data (via src.site_data) and renders a self-contained set of
static HTML pages + assets into an output directory (default: ./site), ready to
publish on GitHub Pages, Cloudflare Pages, or any static host.

Languages: the site is built TWICE from the same templates and data —
English (the default) at the site root, Chinese under /zh/. All UI strings come
from src/i18n.py (en/zh pairs side by side); templates contain no hardcoded
prose, and every page carries a language switcher to its exact counterpart.

Usage
-----
  python build_site.py                 # build the latest quarter into ./site
  python build_site.py --out docs      # build into ./docs
  python build_site.py --quarter 2025-Q4
"""
from __future__ import annotations

import argparse
import csv
import io
import shutil
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src import config, i18n, site_data as sd

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
SITE_NAME = "Value Flow"
# Absolute base URL of the published site — social-share crawlers (WeChat,
# iMessage, Twitter) require ABSOLUTE og:image URLs, relative ones are ignored.
SITE_BASE_URL = "https://kyleding91.github.io/Fund-Manager-Analysis/"

# (language, subdirectory) — the first entry is the default at the site root.
LANG_DIRS = (("en", ""), ("zh", "zh"))


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(WEB / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    return env


def _quarter_slug(q: str) -> str:
    return q.replace("-", "").lower()  # 2026-Q1 -> 2026q1


def _write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def _managers_csv(funds: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["manager_name", "category", "aum_usd", "num_issuers",
                "num_positions", "form_type", "date_filed", "quarter", "cik"])
    for f in funds:
        w.writerow([f["manager_name"], f["category"], int(f["aum_usd"]),
                    f["num_issuers"], f["num_positions"], f["form_type"],
                    f["date_filed"], f["quarter_label"], f["cik"]])
    return buf.getvalue()


def build(out_dir: Path, quarter: str | None = None) -> dict:
    if not config.DB_PATH.exists():
        raise SystemExit(f"No database at {config.DB_PATH}. Load a quarter first.")
    conn = sd.connect_ro()
    qs = sd.quarters(conn)
    if not qs:
        raise SystemExit("Database has no screened funds yet.")
    quarter = quarter or qs[0]
    if quarter not in qs:
        raise SystemExit(f"Quarter {quarter} not in DB. Available: {', '.join(qs)}")

    env = _env()
    fresh = sd.freshness(conn, quarter)
    criteria = dict(min_aum_b=int(config.MIN_AUM_USD / 1e9),
                    max_holdings=config.MAX_HOLDINGS,
                    max_holdings_weighted=config.MAX_HOLDINGS_WEIGHTED,
                    min_holdings=config.MIN_HOLDINGS,
                    max_etf_pct=int(config.MAX_ETF_PCT),
                    top_n=config.TOP_N, top_n_min_pct=int(config.TOP_N_MIN_PCT))
    common = dict(site_name=SITE_NAME, quarter=quarter,
                  quarter_slug=_quarter_slug(quarter), freshness=fresh,
                  all_quarters=qs, criteria=criteria,
                  og_image=SITE_BASE_URL + "assets/icon-512.png")

    # fresh output (preserve nothing stale)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)

    # static assets (stylesheet, scripts, PWA icons) — shared by both languages
    asset_files = ("style.css", "app.js", "icon-192.png", "icon-512.png",
                   "icon-512-maskable.png", "apple-touch-icon.png", "favicon-32.png")
    for name in asset_files:
        shutil.copyfile(WEB / "static" / name, out_dir / "assets" / name)

    # PWA manifest + service worker live at the site ROOT so the worker's scope
    # covers every page (including /en/*), making the site installable.
    shutil.copyfile(WEB / "static" / "manifest.webmanifest",
                    out_dir / "manifest.webmanifest")
    # Stamp a unique cache version into the service worker each build. The
    # version change makes every installed browser discard its old cache on the
    # next visit (the worker's activate step deletes non-matching caches) — so
    # a redeploy can never leave returning visitors on a mix of old/new pages.
    sw = (WEB / "static" / "sw.js").read_text(encoding="utf-8")
    build_id = f"valueflow-{_quarter_slug(quarter)}-{int(time.time())}"
    sw = sw.replace('const CACHE = "valueflow-v1";',
                    f'const CACHE = "{build_id}";')
    (out_dir / "sw.js").write_text(sw, encoding="utf-8")

    # data (computed ONCE — both languages render the same numbers)
    universe = sd.universe(conn, quarter)
    funds = sd.directory(conn, quarter)
    stock_rows = sd.stocks(conn, quarter)
    moves = sd.quarter_moves(conn, quarter)
    linkable = sd.stock_page_cusips(conn, quarter)
    manager_details = []
    for cik in sd.all_manager_ciks(conn):
        detail = sd.fund_detail(conn, cik, quarter, linkable=linkable)
        if detail:
            manager_details.append((cik, detail))
    stock_details = []
    for cusip in sorted(linkable):
        detail = sd.stock_detail(conn, cusip, quarter)
        if detail:
            stock_details.append((cusip, detail))

    # CSV export (shared; carries the firm-type category column)
    _write(out_dir / "data" / f"managers-{_quarter_slug(quarter)}.csv",
           _managers_csv(funds))

    pages = 0
    stock_pages = 0
    for lang, sub in LANG_DIRS:
        lang_dir = out_dir / sub if sub else out_dir
        other_sub = next(s for l, s in LANG_DIRS if l != lang)
        # asset prefix from this language tree's top level back to the real root
        depth0 = "../" if sub else ""

        def render(template: str, rel_path: str, depth: int, **ctx) -> None:
            """Render one page for `lang` at lang_dir/rel_path (depth = subdirs)."""
            up = "../" * depth
            asset_root = up + depth0
            # the same page in the other language (zh <-> en), relative href
            if sub:   # we're in /en/ -> counterpart is at the real root
                switch = up + "../" + rel_path
            else:     # we're at the root -> counterpart is under /en/
                switch = up + (other_sub + "/" if other_sub else "") + rel_path
            tpl = env.get_template(template)
            html = tpl.render(
                root=up, asset_root=asset_root,
                lang=lang, html_lang=i18n.HTML_LANG[lang],
                alt_hreflang=i18n.HTML_LANG[next(l for l, _ in LANG_DIRS if l != lang)],
                switch_href=switch,
                t=lambda key, **kw: i18n.t(key, lang, **kw),
                **ctx)
            _write(lang_dir / rel_path, html)

        render("index.html", "index.html", 0, active="home", u=universe, m=moves, **common)
        pages += 1
        render("funds.html", "funds.html", 0, active="funds", funds=funds, **common)
        pages += 1
        render("stocks.html", "stocks.html", 0, active="stocks", stocks=stock_rows, **common)
        pages += 1
        render("methodology.html", "methodology.html", 0, active="methodology", **common)
        pages += 1
        if moves:
            render("moves.html", "moves.html", 0, active="moves", m=moves, **common)
            pages += 1

        for cik, detail in manager_details:
            render("fund.html", f"funds/{cik}.html", 1, active="funds", f=detail, **common)
            pages += 1
        for cusip, detail in stock_details:
            render("stock.html", f"stocks/{cusip}.html", 1, active="stocks", s=detail, **common)
            pages += 1
            if lang == "zh":
                stock_pages += 1

    # a .nojekyll so GitHub Pages serves files/dirs starting with _ untouched
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    return {"quarter": quarter, "pages": pages, "funds": len(funds),
            "stocks": stock_pages, "langs": [l for l, _ in LANG_DIRS],
            "out": str(out_dir)}


def main() -> None:
    p = argparse.ArgumentParser(description="Build the static 13F website.")
    p.add_argument("--out", default="site", help="Output directory (default: site)")
    p.add_argument("--quarter", help="Quarter label, e.g. 2026-Q1 (default: latest)")
    args = p.parse_args()
    res = build((ROOT / args.out).resolve(), quarter=args.quarter)
    print(f"Built {res['pages']} pages ({res['funds']} managers, "
          f"languages: {'+'.join(res['langs'])}) for {res['quarter']} -> {res['out']}")


if __name__ == "__main__":
    main()
