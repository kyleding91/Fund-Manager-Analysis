#!/usr/bin/env python3
"""Re-screen the tracked quarters and backfill full history for the universe.

Why this exists
---------------
A manager only "qualifies" in a quarter where it meets the selection criteria
(>$2B AUM and either <=30 issuers or a heavy top-10 weight). Because those
criteria drift quarter to quarter, a manager can pop in and out of the screen —
which left gaps in the per-manager deep-dive timeline.

This script makes each tracked manager's history complete in three passes:

  1. **Re-screen** every tracked quarter end-to-end. This refreshes each filing's
     metrics under the current criteria, stores everything that qualifies, and
     records a row in the `quarter_screen` ledger for *every* filer scanned.
  2. **Find the universe** — every CIK that qualifies in at least one tracked
     quarter (read from the ledger).
  3. **Backfill** — for each tracked quarter, store the actual 13F holdings of
     every universe manager, even quarters where it didn't qualify, so the
     timeline and quarter-over-quarter moves are continuous.

Raw filings are cached under data/raw, so re-scanning is mostly local disk reads.

Usage
-----
  # Rebuild for whatever quarters are already in the database:
  python rebuild_universe.py

  # Rebuild for an explicit set of holdings quarters:
  python rebuild_universe.py --quarters 2025Q1 2025Q2 2025Q3 2025Q4 2026Q1
"""
from __future__ import annotations

import argparse
import logging
import re

from src import config
from src.database import connect, init_db
from src.pipeline import run_quarter
from src.quality import check_db

log = logging.getLogger("rebuild")


def parse_quarter(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{4})[-_ ]?[Qq]([1-4])\s*", text)
    if not m:
        raise argparse.ArgumentTypeError(f"Bad quarter '{text}'. Use e.g. 2025Q1.")
    return int(m.group(1)), int(m.group(2))


def quarters_in_db() -> list[tuple[int, int]]:
    """Holdings quarters currently present in the database, oldest first."""
    with connect() as conn:
        init_db(conn)
        labels = [r[0] for r in conn.execute(
            "SELECT DISTINCT quarter_label FROM filings "
            "WHERE quarter_label IS NOT NULL ORDER BY quarter_label")]
    out = []
    for lab in labels:
        m = re.fullmatch(r"(\d{4})-Q([1-4])", lab)
        if m:
            out.append((int(m.group(1)), int(m.group(2))))
    return out


def universe_ciks(quarters: list[tuple[int, int]]) -> set[str]:
    """CIKs that qualify (passes_screen=1) in at least one tracked quarter."""
    labels = [f"{y}-Q{q}" for (y, q) in quarters]
    placeholders = ",".join("?" for _ in labels)
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT DISTINCT cik FROM quarter_screen
                WHERE passes_screen = 1 AND quarter_label IN ({placeholders})""",
            labels,
        ).fetchall()
    return {str(r[0]) for r in rows}


def rebuild(quarters: list[tuple[int, int]], *, backfill_only: bool = False) -> dict:
    qlabels = ", ".join(f"{y}Q{q}" for (y, q) in quarters)
    if backfill_only:
        log.info("=== Skipping re-screen (using existing ledger) ===")
    else:
        log.info("=== Pass 1/3: re-screen %d quarter(s): %s ===", len(quarters), qlabels)
        for (y, q) in quarters:
            run_quarter(y, q)  # records ledger for all, stores qualifiers

    universe = universe_ciks(quarters)
    log.info("=== Pass 2/3: universe = %d managers qualifying in >=1 quarter ===",
             len(universe))

    log.info("=== Pass 3/3: backfill full history for the universe ===")
    for (y, q) in quarters:
        run_quarter(y, q, only_ciks=universe, store_all=True, record_all=False)

    with connect() as conn:
        issues = check_db(conn)
    log.info("Data-quality check: %s",
             "no issues" if not issues else f"{len(issues)} issue(s)")
    for i in issues[:20]:
        log.info("  - %s", i)
    return {"quarters": quarters, "universe": len(universe), "issues": len(issues)}


def main() -> None:
    p = argparse.ArgumentParser(description="Rebuild the screened universe + history.")
    p.add_argument("--quarters", nargs="+", type=parse_quarter,
                   help="Holdings quarters, e.g. 2025Q1 2025Q2 ... (default: those in DB)")
    p.add_argument("--backfill-only", action="store_true",
                   help="Skip the full re-screen; just backfill the universe using "
                        "the existing screen ledger (much cheaper, for scheduled runs).")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.ensure_dirs()

    quarters = args.quarters or quarters_in_db()
    if not quarters:
        raise SystemExit("No quarters to rebuild. Load some first with ingest.py.")
    res = rebuild(quarters, backfill_only=args.backfill_only)
    print(f"Rebuilt {len(res['quarters'])} quarter(s); "
          f"universe = {res['universe']} managers; "
          f"{res['issues']} data-quality issue(s).")


if __name__ == "__main__":
    main()
