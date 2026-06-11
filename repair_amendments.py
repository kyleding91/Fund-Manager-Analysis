#!/usr/bin/env python3
"""One-off repair for two historical ingest bugs in data/13f.db.

1. Partial-amendment displacement: a partial 13F-HR/A ("new holdings" add-on,
   or an untyped amendment under half the size of the fullest sibling) was
   marked is_current=1, displacing the full filing for that (cik, period) —
   e.g. Berkshire 2025-Q1 showed a 4-position/$1.1B amendment instead of the
   36-position/$258.7B original. This script re-picks the current filing per
   the new rule (src.database.pick_current_filing), then repairs the
   quarter_screen ledger row for each affected (cik, quarter) from the
   now-current filing's stored metrics, and finally re-syncs the stored
   filings' screen flags from the ledger (sync_filings_screen).

2. Double-escaped names: some rows hold literal HTML entities
   ("VANGUARD S&amp;P 500 ETF", &#039;...). html.unescape() is applied to
   holdings.name_of_issuer, holdings.title_of_class, funds.manager_name and
   quarter_screen.manager_name wherever it changes the value.

Usage:
    python3 repair_amendments.py --dry-run   # report only, write nothing
    python3 repair_amendments.py             # apply the fixes
"""
from __future__ import annotations

import argparse
import html
import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

from src import classify, config
from src.database import init_db, pick_current_filing, sync_filings_screen
from src.screener import reject_reason

NAME_TARGETS = [
    ("holdings", "name_of_issuer"),
    ("holdings", "title_of_class"),
    ("funds", "manager_name"),
    ("quarter_screen", "manager_name"),
]


def _connect(db_path, dry_run: bool) -> sqlite3.Connection:
    if dry_run:  # read-only: a dry run must not write a single byte
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # SQL-callable unescape so the name repair is a single UPDATE per column.
    conn.create_function("unesc", 1,
                         lambda s: html.unescape(s) if isinstance(s, str) else s)
    return conn


def _filing_rows(conn, cik: str, period: str):
    """All filings for (cik, period), tolerating a pre-migration schema."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(filings)")}
    atype = "amendment_type" if "amendment_type" in cols else "'' AS amendment_type"
    return conn.execute(
        f"""SELECT id, accession, form_type, quarter_label, date_filed, {atype},
                   num_positions, num_issuers, top_n_pct, total_aum_usd, is_current
            FROM filings WHERE cik = ? AND period_of_report = ?""",
        (cik, period),
    ).fetchall()


def _etf_pct(conn, filing_id: int) -> float:
    """Value-weighted % of a stored filing's holdings that are ETFs/index funds."""
    rows = conn.execute(
        "SELECT name_of_issuer, value_usd FROM holdings WHERE filing_id = ?",
        (filing_id,),
    ).fetchall()
    total = sum(r["value_usd"] or 0 for r in rows)
    if not total:
        return 0.0
    etf = sum(r["value_usd"] or 0 for r in rows
              if classify.is_etf_name(html.unescape(r["name_of_issuer"] or "")))
    return etf / total * 100.0


def _screen_verdict(aum: float, num_issuers: int, top_n_pct: float,
                    etf_pct: float) -> tuple[bool, bool, bool, str]:
    """Re-derive (meets_count, meets_weight, passes, reject_reason) from stored
    metrics, mirroring src.screener.screen_filing's gates."""
    aum = aum or 0
    num_issuers = num_issuers or 0
    top_n_pct = top_n_pct or 0.0
    big_enough = (aum > config.MIN_AUM_USD
                  and num_issuers >= config.MIN_HOLDINGS and num_issuers > 0)
    meets_count = big_enough and num_issuers <= config.MAX_HOLDINGS
    meets_weight = (big_enough and num_issuers <= config.MAX_HOLDINGS_WEIGHTED
                    and top_n_pct >= config.TOP_N_MIN_PCT)
    passes = (big_enough and (meets_count or meets_weight)
              and etf_pct < config.MAX_ETF_PCT)
    stand_in = SimpleNamespace(total_aum_usd=aum, num_issuers=num_issuers,
                               top_n_pct=top_n_pct, etf_pct=etf_pct,
                               passes_screen=passes)
    return meets_count, meets_weight, passes, reject_reason(stand_in)


def _fmt(row) -> str:
    aum = (row["total_aum_usd"] or 0) / 1e9
    return (f"{row['accession']}  {row['form_type'] or '?':9s} "
            f"{row['num_positions'] or 0:>4d} pos  ${aum:,.2f}B "
            f"(filed {row['date_filed']})")


def repair_names(conn, dry_run: bool) -> int:
    """Apply html.unescape to stored name/title columns where it changes them."""
    total = 0
    for table, col in NAME_TARGETS:
        where = f"{col} IS NOT NULL AND {col} != unesc({col})"
        if dry_run:
            n = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]
            sample = conn.execute(
                f"SELECT {col} FROM {table} WHERE {where} LIMIT 3").fetchall()
            extra = "".join(f"\n      e.g. {r[0]!r} -> {html.unescape(r[0])!r}"
                            for r in sample)
        else:
            n = conn.execute(
                f"UPDATE {table} SET {col} = unesc({col}) WHERE {where}").rowcount
            extra = ""
        print(f"  {table}.{col}: {n} row(s)"
              f"{' would be' if dry_run else ''} un-escaped{extra}")
        total += n
    return total


def repair_currents(conn, dry_run: bool) -> tuple[int, set[str]]:
    """Re-pick is_current per (cik, period); return (#flips, affected quarters)."""
    groups = conn.execute(
        """SELECT cik, period_of_report FROM filings
           GROUP BY cik, period_of_report HAVING COUNT(*) > 1
           ORDER BY cik, period_of_report""").fetchall()
    flips = 0
    quarters: set[str] = set()
    for g in groups:
        cik, period = g["cik"], g["period_of_report"]
        rows = _filing_rows(conn, cik, period)
        winner = pick_current_filing(rows)
        old = next((r for r in rows if r["is_current"]), None)
        if winner is None or (old is not None and old["id"] == winner["id"]):
            continue
        name = (conn.execute("SELECT manager_name FROM funds WHERE cik = ?",
                             (cik,)).fetchone() or [""])[0] or "?"
        print(f"\n  cik {cik}  {html.unescape(name)}  "
              f"{winner['quarter_label']} ({period}):")
        print(f"    was current: {_fmt(old) if old else '(none)'}")
        print(f"    now current: {_fmt(winner)}")
        flips += 1
        if winner["quarter_label"]:
            quarters.add(winner["quarter_label"])
        if not dry_run:
            conn.execute(
                "UPDATE filings SET is_current = (id = ?) "
                "WHERE cik = ? AND period_of_report = ?",
                (winner["id"], cik, period))
        _repair_ledger(conn, cik, winner, dry_run)
    return flips, quarters


def _repair_ledger(conn, cik: str, winner, dry_run: bool) -> None:
    """Rewrite the (cik, quarter) quarter_screen row from the now-current filing."""
    etf_pct = _etf_pct(conn, winner["id"])
    meets_count, meets_weight, passes, reason = _screen_verdict(
        winner["total_aum_usd"], winner["num_issuers"],
        winner["top_n_pct"], etf_pct)
    name_row = conn.execute("SELECT manager_name FROM funds WHERE cik = ?",
                            (cik,)).fetchone()
    manager = html.unescape(name_row[0]) if name_row and name_row[0] else None
    verdict = "PASS" if passes else f"fail ({reason})"
    summary = (f"{winner['num_positions']} pos, "
               f"${(winner['total_aum_usd'] or 0)/1e9:,.2f}B, screen {verdict}")
    if dry_run:
        print(f"    ledger: would be rewritten -> {summary}")
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        """UPDATE quarter_screen SET
               manager_name = COALESCE(?, manager_name),
               total_aum_usd = ?, num_positions = ?, num_issuers = ?,
               top_n_pct = ?, meets_count = ?, meets_weight = ?,
               passes_screen = ?, reject_reason = ?, updated_at = ?
           WHERE cik = ? AND quarter_label = ?""",
        (manager, winner["total_aum_usd"], winner["num_positions"],
         winner["num_issuers"], winner["top_n_pct"], int(meets_count),
         int(meets_weight), int(passes), reason, now,
         cik, winner["quarter_label"]))
    print(f"    ledger: {cur.rowcount} row(s) updated -> {summary}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would change without writing anything")
    ap.add_argument("--db", default=str(config.DB_PATH),
                    help="path to the SQLite database (default: data/13f.db)")
    args = ap.parse_args()

    conn = _connect(args.db, args.dry_run)
    try:
        if not args.dry_run:
            init_db(conn)  # forward-only migration adds filings.amendment_type

        print("== Bug 2: un-escaping doubly-escaped names ==")
        n_names = repair_names(conn, args.dry_run)

        print("\n== Bug 1: partial amendments displacing full filings ==")
        flips, quarters = repair_currents(conn, args.dry_run)
        print(f"\n  {flips} (cik, quarter) pair(s) "
              f"{'would be' if args.dry_run else ''} re-pointed to the full filing.")

        if quarters:
            if args.dry_run:
                print(f"  (would re-sync filings.passes_screen for: "
                      f"{', '.join(sorted(quarters))})")
            else:
                synced = sync_filings_screen(conn, sorted(quarters))
                print(f"  Re-synced screen flags on {synced} filing row(s) "
                      f"in: {', '.join(sorted(quarters))}")

        if args.dry_run:
            print(f"\n[dry-run] nothing written. Totals: {n_names} name row(s), "
                  f"{flips} is_current flip(s).")
        else:
            conn.commit()
            print(f"\nDone. Totals: {n_names} name row(s) fixed, "
                  f"{flips} is_current flip(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
