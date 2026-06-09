#!/usr/bin/env python3
"""13F Fund Tracker — command-line tool to load and check data.

Common uses
-----------
  # Load one holdings quarter (everything that passes the screen):
  python ingest.py --quarter 2025Q1

  # Backfill the last 4 available quarters in one go:
  python ingest.py --backfill 4

  # Quick test (stop after 15 funds pass) — good for a first try:
  python ingest.py --quarter 2025Q1 --max-passes 15

  # See what's in the database / run data-quality checks:
  python ingest.py --stats
  python ingest.py --check

After loading, view it with:   streamlit run app.py
"""
from __future__ import annotations

import argparse
import logging
import re
from datetime import date

from src import config
from src.database import connect, init_db, stats
from src.pipeline import run_quarter
from src.quality import check_db

log = logging.getLogger("ingest")


def parse_quarter(text: str) -> tuple[int, int]:
    """Accept '2025Q1', '2025-Q1', '2025q1' -> (2025, 1)."""
    m = re.fullmatch(r"\s*(\d{4})[-_ ]?[Qq]([1-4])\s*", text)
    if not m:
        raise argparse.ArgumentTypeError(f"Bad quarter '{text}'. Use e.g. 2025Q1.")
    return int(m.group(1)), int(m.group(2))


def latest_available_holdings_quarter(today: date | None = None) -> tuple[int, int]:
    """Most recent quarter whose 13F filings are due (>=46 days after quarter end)."""
    today = today or date.today()
    ends = []
    for y in (today.year, today.year - 1):
        for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
            qend = date(y, m, d)
            if (today - qend).days >= 46:
                ends.append(qend)
    qend = max(ends)
    return qend.year, (qend.month - 1) // 3 + 1


def quarters_back(n: int) -> list[tuple[int, int]]:
    """The latest n holdings quarters, oldest first."""
    y, q = latest_available_holdings_quarter()
    out = []
    for _ in range(n):
        out.append((y, q))
        q -= 1
        if q == 0:
            q, y = 4, y - 1
    return list(reversed(out))


def cmd_load(quarters: list[tuple[int, int]], *, max_passes=None, limit=None) -> None:
    for (y, q) in quarters:
        log.info("=== Loading holdings %dQ%d ===", y, q)
        s = run_quarter(y, q, max_passes=max_passes, limit=limit)
        log.info("  scanned=%d passed=%d errors=%d", s.scanned, s.passed, s.errors)


def cmd_stats() -> None:
    if not config.DB_PATH.exists():
        log.info("No database yet at %s", config.DB_PATH)
        return
    with connect() as conn:
        init_db(conn)
        s = stats(conn)
        quarters = conn.execute(
            "SELECT DISTINCT quarter_label FROM filings WHERE is_current=1 AND passes_screen=1 "
            "ORDER BY quarter_label DESC"
        ).fetchall()
    log.info("Database: %s", config.DB_PATH)
    for k, v in s.items():
        log.info("  %-16s %s", k, v)
    log.info("  quarters loaded: %s", ", ".join(r[0] for r in quarters) or "(none)")


def cmd_check() -> None:
    if not config.DB_PATH.exists():
        log.info("No database yet — nothing to check.")
        return
    with connect() as conn:
        issues = check_db(conn)
    if not issues:
        log.info("Data-quality check: ✅ no issues found.")
    else:
        log.info("Data-quality check: %d issue(s):", len(issues))
        for i in issues:
            log.info("  - %s", i)


def main() -> None:
    p = argparse.ArgumentParser(description="Load & check 13F data from SEC EDGAR.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--quarter", type=parse_quarter, help="Holdings quarter, e.g. 2025Q1")
    g.add_argument("--backfill", type=int, metavar="N", help="Load the latest N quarters")
    g.add_argument("--stats", action="store_true", help="Show database stats and exit")
    g.add_argument("--check", action="store_true", help="Run data-quality checks and exit")
    p.add_argument("--max-passes", type=int, help="Stop after this many funds pass (quick test)")
    p.add_argument("--limit", type=int, help="Stop after scanning this many filings (quick test)")
    p.add_argument("-q", "--quiet", action="store_true", help="Less logging")
    args = p.parse_args()

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(message)s")
    config.ensure_dirs()

    if args.stats:
        cmd_stats()
    elif args.check:
        cmd_check()
    elif args.backfill:
        cmd_load(quarters_back(args.backfill), max_passes=args.max_passes, limit=args.limit)
        cmd_check()
    elif args.quarter:
        cmd_load([args.quarter], max_passes=args.max_passes, limit=args.limit)
        cmd_check()
    else:
        p.print_help()


if __name__ == "__main__":
    main()
