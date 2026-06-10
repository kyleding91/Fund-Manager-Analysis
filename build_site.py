#!/usr/bin/env python3
"""Generate the static website from the 13F database.

Reads the screened data (via src.site_data) and renders a self-contained set of
static HTML pages + assets into an output directory (default: ./site), ready to
publish on GitHub Pages, Cloudflare Pages, or any static host.

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
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src import config, site_data as sd

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
SITE_NAME = "Value Flow"


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
                  all_quarters=qs, criteria=criteria)

    # fresh output (preserve nothing stale)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    (out_dir / "funds").mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)

    # static assets (stylesheet, scripts, PWA icons)
    asset_files = ("style.css", "app.js", "icon-192.png", "icon-512.png",
                   "icon-512-maskable.png", "apple-touch-icon.png", "favicon-32.png")
    for name in asset_files:
        shutil.copyfile(WEB / "static" / name, out_dir / "assets" / name)

    # PWA manifest + service worker live at the site ROOT so the worker's scope
    # covers every page (including /funds/*), making the site installable.
    for name in ("manifest.webmanifest", "sw.js"):
        shutil.copyfile(WEB / "static" / name, out_dir / name)

    # data
    universe = sd.universe(conn, quarter)
    funds = sd.directory(conn, quarter)
    stock_rows = sd.stocks(conn, quarter)

    pages = 0
    # home
    _write(out_dir / "index.html",
           env.get_template("index.html").render(root="", active="home",
                                                 u=universe, **common))
    pages += 1
    # managers directory
    _write(out_dir / "funds.html",
           env.get_template("funds.html").render(root="", active="funds",
                                                 funds=funds, **common))
    pages += 1
    # stocks
    _write(out_dir / "stocks.html",
           env.get_template("stocks.html").render(root="", active="stocks",
                                                  stocks=stock_rows, **common))
    pages += 1
    # methodology
    _write(out_dir / "methodology.html",
           env.get_template("methodology.html").render(root="", active="methodology",
                                                       **common))
    pages += 1
    # this quarter's money moves (needs a prior quarter to compare against)
    moves = sd.quarter_moves(conn, quarter)
    if moves:
        _write(out_dir / "moves.html",
               env.get_template("moves.html").render(root="", active="moves",
                                                     m=moves, **common))
        pages += 1
    # CSV export
    _write(out_dir / "data" / f"managers-{_quarter_slug(quarter)}.csv",
           _managers_csv(funds))

    # per-fund pages — one for every manager with stored history, so a manager
    # that qualified only in an earlier quarter still has a complete page.
    fund_tpl = env.get_template("fund.html")
    for cik in sd.all_manager_ciks(conn):
        detail = sd.fund_detail(conn, cik, quarter)
        if not detail:
            continue
        _write(out_dir / "funds" / f"{cik}.html",
               fund_tpl.render(root="../", active="funds", f=detail, **common))
        pages += 1

    # per-stock pages — one for every company held by a screened manager this
    # quarter, so every company name on the most-held page links to its holders.
    stock_tpl = env.get_template("stock.html")
    stock_pages = 0
    for cusip in sd.all_stock_cusips(conn, quarter):
        detail = sd.stock_detail(conn, cusip, quarter)
        if not detail:
            continue
        _write(out_dir / "stocks" / f"{cusip}.html",
               stock_tpl.render(root="../", active="stocks", s=detail, **common))
        pages += 1
        stock_pages += 1

    # a .nojekyll so GitHub Pages serves files/dirs starting with _ untouched
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    return {"quarter": quarter, "pages": pages, "funds": len(funds),
            "stocks": stock_pages, "out": str(out_dir)}


def main() -> None:
    p = argparse.ArgumentParser(description="Build the static 13F website.")
    p.add_argument("--out", default="site", help="Output directory (default: site)")
    p.add_argument("--quarter", help="Quarter label, e.g. 2026-Q1 (default: latest)")
    args = p.parse_args()
    res = build((ROOT / args.out).resolve(), quarter=args.quarter)
    print(f"Built {res['pages']} pages ({res['funds']} managers) for "
          f"{res['quarter']} -> {res['out']}")


if __name__ == "__main__":
    main()
