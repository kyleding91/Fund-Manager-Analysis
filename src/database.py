"""Phase 3 — SQLite storage for screened 13F funds.

Tables:
  funds     — one row per manager (CIK)
  filings   — one row per fund per filing (a quarter; amendments are separate rows)
  holdings  — the positions inside a filing

Design choices:
  * Only funds that PASS the screen are stored (keeps the DB focused & small).
  * Re-running a quarter is idempotent: filings are keyed by accession number.
  * Amendments (13F-HR/A) are stored as their own filing; the newest filing for a
    (cik, period) is flagged is_current=1 so queries can ignore superseded ones.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config
from .screener import ScreenedFund

SCHEMA = """
CREATE TABLE IF NOT EXISTS funds (
    cik           TEXT PRIMARY KEY,
    manager_name  TEXT
);

CREATE TABLE IF NOT EXISTS filings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cik               TEXT NOT NULL,
    accession         TEXT UNIQUE NOT NULL,
    form_type         TEXT,
    quarter_label     TEXT,
    period_of_report  TEXT,
    date_filed        TEXT,
    total_aum_usd     REAL,
    num_positions     INTEGER,
    num_issuers       INTEGER,
    top_n_pct         REAL,
    passes_screen     INTEGER,
    is_current        INTEGER DEFAULT 1,
    loaded_at         TEXT,
    FOREIGN KEY (cik) REFERENCES funds(cik)
);

-- Per-manager, per-quarter screen ledger: records whether each filer met the
-- selection criteria in a given quarter, with the metrics behind the decision.
-- This is comprehensive (every 13F filer scanned, not only the ones we store),
-- so it answers "which companies met the criteria in each quarter?".
CREATE TABLE IF NOT EXISTS quarter_screen (
    cik               TEXT NOT NULL,
    quarter_label     TEXT NOT NULL,
    period_of_report  TEXT,
    manager_name      TEXT,
    total_aum_usd     REAL,
    num_positions     INTEGER,
    num_issuers       INTEGER,
    top_n_pct         REAL,
    meets_count       INTEGER,
    meets_weight      INTEGER,
    passes_screen     INTEGER,
    updated_at        TEXT,
    PRIMARY KEY (cik, quarter_label)
);

CREATE TABLE IF NOT EXISTS holdings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    filing_id         INTEGER NOT NULL,
    cusip             TEXT,
    issuer_cusip      TEXT,
    name_of_issuer    TEXT,
    title_of_class    TEXT,
    value_usd         REAL,
    shares            REAL,
    shares_type       TEXT,
    put_call          TEXT,
    pct_of_portfolio  REAL,
    FOREIGN KEY (filing_id) REFERENCES filings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_filings_cik_period ON filings(cik, period_of_report);
CREATE INDEX IF NOT EXISTS idx_filings_quarter ON filings(quarter_label);
CREATE INDEX IF NOT EXISTS idx_holdings_filing ON holdings(filing_id);
CREATE INDEX IF NOT EXISTS idx_holdings_issuer ON holdings(issuer_cusip);
CREATE INDEX IF NOT EXISTS idx_qscreen_quarter ON quarter_screen(quarter_label);
"""


@contextmanager
def connect(db_path=None):
    """Open a SQLite connection with foreign keys + Row access enabled."""
    config.ensure_dirs()
    conn = sqlite3.connect(str(db_path or config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns/tables introduced after a database was first created."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(filings)")}
    if "top_n_pct" not in cols:
        conn.execute("ALTER TABLE filings ADD COLUMN top_n_pct REAL")


def _recompute_current(conn: sqlite3.Connection, cik: str, period: str) -> None:
    """Flag the newest filing for (cik, period) as current; others superseded."""
    conn.execute(
        "UPDATE filings SET is_current = 0 WHERE cik = ? AND period_of_report = ?",
        (cik, period),
    )
    conn.execute(
        """UPDATE filings SET is_current = 1
           WHERE id = (
               SELECT id FROM filings
               WHERE cik = ? AND period_of_report = ?
               ORDER BY date_filed DESC, id DESC LIMIT 1)""",
        (cik, period),
    )


def upsert_fund(conn: sqlite3.Connection, sf: ScreenedFund) -> int:
    """Insert/replace a screened fund's filing + holdings. Returns the filing id.

    Idempotent: re-loading the same accession refreshes its row + holdings in place.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO funds(cik, manager_name) VALUES(?, ?) "
        "ON CONFLICT(cik) DO UPDATE SET manager_name = excluded.manager_name",
        (sf.cik, sf.manager_name),
    )

    row = conn.execute("SELECT id FROM filings WHERE accession = ?",
                       (sf.accession,)).fetchone()
    fields = (sf.cik, sf.accession, sf.form_type, sf.quarter_label,
              sf.period_of_report, sf.date_filed, sf.total_aum_usd,
              sf.num_positions, sf.num_issuers, sf.top_n_pct,
              int(sf.passes_screen), now)
    if row:
        filing_id = row["id"]
        conn.execute(
            """UPDATE filings SET cik=?, accession=?, form_type=?, quarter_label=?,
               period_of_report=?, date_filed=?, total_aum_usd=?, num_positions=?,
               num_issuers=?, top_n_pct=?, passes_screen=?, loaded_at=? WHERE id=?""",
            (*fields, filing_id),
        )
        conn.execute("DELETE FROM holdings WHERE filing_id = ?", (filing_id,))
    else:
        cur = conn.execute(
            """INSERT INTO filings(cik, accession, form_type, quarter_label,
               period_of_report, date_filed, total_aum_usd, num_positions,
               num_issuers, top_n_pct, passes_screen, loaded_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            fields,
        )
        filing_id = cur.lastrowid

    conn.executemany(
        """INSERT INTO holdings(filing_id, cusip, issuer_cusip, name_of_issuer,
           title_of_class, value_usd, shares, shares_type, put_call, pct_of_portfolio)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        [
            (filing_id, h.cusip, (h.cusip or "")[:6].upper(), h.name_of_issuer,
             h.title_of_class, h.value_usd, h.shares, h.shares_type, h.put_call,
             h.pct_of_portfolio)
            for h in sf.holdings
        ],
    )

    _recompute_current(conn, sf.cik, sf.period_of_report)
    return filing_id


def record_screen(conn: sqlite3.Connection, sf: ScreenedFund) -> None:
    """Record one filing's screen result in the per-quarter ledger.

    Called for *every* filing scanned (whether or not we keep its holdings), so
    the ledger is a complete record of who met the criteria each quarter. Keyed
    by (cik, quarter); a later amendment for the same quarter overwrites it.
    """
    if not sf.quarter_label:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO quarter_screen(cik, quarter_label, period_of_report,
               manager_name, total_aum_usd, num_positions, num_issuers, top_n_pct,
               meets_count, meets_weight, passes_screen, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(cik, quarter_label) DO UPDATE SET
               period_of_report=excluded.period_of_report,
               manager_name=excluded.manager_name,
               total_aum_usd=excluded.total_aum_usd,
               num_positions=excluded.num_positions,
               num_issuers=excluded.num_issuers,
               top_n_pct=excluded.top_n_pct,
               meets_count=excluded.meets_count,
               meets_weight=excluded.meets_weight,
               passes_screen=excluded.passes_screen,
               updated_at=excluded.updated_at""",
        (sf.cik, sf.quarter_label, sf.period_of_report, sf.manager_name,
         sf.total_aum_usd, sf.num_positions, sf.num_issuers, sf.top_n_pct,
         int(sf.meets_count), int(sf.meets_weight), int(sf.passes_screen), now),
    )


def stats(conn: sqlite3.Connection) -> dict:
    """Quick counts for sanity checks / CLI output."""
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "funds": q("SELECT COUNT(*) FROM funds"),
        "filings": q("SELECT COUNT(*) FROM filings"),
        "current_filings": q("SELECT COUNT(*) FROM filings WHERE is_current=1"),
        "holdings": q("SELECT COUNT(*) FROM holdings"),
        "quarters": q("SELECT COUNT(DISTINCT quarter_label) FROM filings"),
        "screen_ledger": q("SELECT COUNT(*) FROM quarter_screen"),
    }
