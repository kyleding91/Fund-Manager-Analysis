#!/usr/bin/env python3
"""Keep only the chosen quarters in the database; delete everything else.

This is a maintenance helper. The website is anchored to a rolling window of
quarters; if older quarters have accumulated and you want the database to hold
only a specific set, run this. Deleting a filing also deletes its holdings
(ON DELETE CASCADE) and any manager that no longer has a filing on record.

Usage
-----
  # Keep exactly these five quarters, drop the rest:
  python prune_quarters.py --keep 2025-Q1 2025-Q2 2025-Q3 2025-Q4 2026-Q1

  # See what would happen without changing anything:
  python prune_quarters.py --keep 2026-Q1 --dry-run
"""
from __future__ import annotations

import argparse

from src.database import connect


def _has_table(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def prune(conn, keep: list[str], dry_run: bool = False) -> dict:
    have = [r[0] for r in conn.execute(
        "SELECT DISTINCT quarter_label FROM filings ORDER BY quarter_label")]
    keep_set = set(keep)
    drop = [q for q in have if q not in keep_set]
    missing = [q for q in keep if q not in have]

    placeholders = ",".join("?" for _ in keep) or "''"
    n_filings = conn.execute(
        f"SELECT COUNT(*) FROM filings WHERE quarter_label NOT IN ({placeholders})",
        keep,
    ).fetchone()[0]

    if not dry_run and drop:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            f"DELETE FROM filings WHERE quarter_label NOT IN ({placeholders})", keep)
        # Keep the per-quarter screen ledger in step with the tracked quarters.
        if _has_table(conn, "quarter_screen"):
            conn.execute(
                f"DELETE FROM quarter_screen WHERE quarter_label NOT IN ({placeholders})",
                keep)
        # Drop managers that no longer have any filing on record.
        conn.execute(
            "DELETE FROM funds WHERE cik NOT IN (SELECT DISTINCT cik FROM filings)")
        conn.commit()
        conn.execute("VACUUM")

    remaining = [r[0] for r in conn.execute(
        "SELECT DISTINCT quarter_label FROM filings ORDER BY quarter_label")]
    return {"kept": keep, "dropped": drop, "missing": missing,
            "filings_deleted": n_filings, "remaining": remaining,
            "dry_run": dry_run}


def main() -> None:
    p = argparse.ArgumentParser(description="Keep only chosen quarters in the DB.")
    p.add_argument("--keep", nargs="+", required=True,
                   help="Quarter labels to keep, e.g. 2025-Q1 2025-Q2 ...")
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would be deleted without deleting.")
    args = p.parse_args()
    with connect() as conn:
        res = prune(conn, args.keep, dry_run=args.dry_run)
    verb = "Would delete" if res["dry_run"] else "Deleted"
    print(f"Keep: {', '.join(res['kept'])}")
    if res["missing"]:
        print(f"WARNING: requested but not in DB: {', '.join(res['missing'])}")
    print(f"{verb} {res['filings_deleted']} filings from quarters: "
          f"{', '.join(res['dropped']) or '(none)'}")
    print(f"Remaining quarters: {', '.join(res['remaining'])}")


if __name__ == "__main__":
    main()
