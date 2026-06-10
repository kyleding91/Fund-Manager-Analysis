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
    manager_name  TEXT,
    filer_type    TEXT
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
    filer_type        TEXT,
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
    filer_type        TEXT,
    reject_reason     TEXT,
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
    """Add columns/tables introduced after a database was first created.

    Forward-only: each block checks PRAGMA table_info and adds any missing column
    with a plain ALTER TABLE (no version numbers). Existing rows get NULL, which
    a re-screen (rebuild_universe.py) backfills.
    """
    filing_cols = {r[1] for r in conn.execute("PRAGMA table_info(filings)")}
    if "top_n_pct" not in filing_cols:
        conn.execute("ALTER TABLE filings ADD COLUMN top_n_pct REAL")
    if "filer_type" not in filing_cols:
        conn.execute("ALTER TABLE filings ADD COLUMN filer_type TEXT")

    fund_cols = {r[1] for r in conn.execute("PRAGMA table_info(funds)")}
    if "filer_type" not in fund_cols:
        conn.execute("ALTER TABLE funds ADD COLUMN filer_type TEXT")

    qs_cols = {r[1] for r in conn.execute("PRAGMA table_info(quarter_screen)")}
    if "filer_type" not in qs_cols:
        conn.execute("ALTER TABLE quarter_screen ADD COLUMN filer_type TEXT")
    if "reject_reason" not in qs_cols:
        conn.execute("ALTER TABLE quarter_screen ADD COLUMN reject_reason TEXT")


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
        "INSERT INTO funds(cik, manager_name, filer_type) VALUES(?, ?, ?) "
        "ON CONFLICT(cik) DO UPDATE SET manager_name = excluded.manager_name, "
        "filer_type = excluded.filer_type",
        (sf.cik, sf.manager_name, sf.filer_type),
    )

    row = conn.execute("SELECT id FROM filings WHERE accession = ?",
                       (sf.accession,)).fetchone()
    fields = (sf.cik, sf.accession, sf.form_type, sf.quarter_label,
              sf.period_of_report, sf.date_filed, sf.total_aum_usd,
              sf.num_positions, sf.num_issuers, sf.top_n_pct,
              int(sf.passes_screen), sf.filer_type, now)
    if row:
        filing_id = row["id"]
        conn.execute(
            """UPDATE filings SET cik=?, accession=?, form_type=?, quarter_label=?,
               period_of_report=?, date_filed=?, total_aum_usd=?, num_positions=?,
               num_issuers=?, top_n_pct=?, passes_screen=?, filer_type=?,
               loaded_at=? WHERE id=?""",
            (*fields, filing_id),
        )
        conn.execute("DELETE FROM holdings WHERE filing_id = ?", (filing_id,))
    else:
        cur = conn.execute(
            """INSERT INTO filings(cik, accession, form_type, quarter_label,
               period_of_report, date_filed, total_aum_usd, num_positions,
               num_issuers, top_n_pct, passes_screen, filer_type, loaded_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
               meets_count, meets_weight, passes_screen, filer_type, reject_reason,
               updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
               filer_type=excluded.filer_type,
               reject_reason=excluded.reject_reason,
               updated_at=excluded.updated_at""",
        (sf.cik, sf.quarter_label, sf.period_of_report, sf.manager_name,
         sf.total_aum_usd, sf.num_positions, sf.num_issuers, sf.top_n_pct,
         int(sf.meets_count), int(sf.meets_weight), int(sf.passes_screen),
         sf.filer_type, sf.reject_reason, now),
    )


def sync_filings_screen(conn: sqlite3.Connection,
                        quarters: list[str] | None = None) -> int:
    """Reconcile `filings.passes_screen`/`filer_type` with the fresh ledger.

    `quarter_screen` is re-screened end-to-end every rebuild, so it is the
    authoritative current verdict for each (cik, quarter). `filings`, by
    contrast, only gets its screen columns refreshed when a filing is (re)stored
    — qualifiers in pass 1, universe members in pass 3. A filer that *used to*
    qualify (so its holdings were stored with passes_screen=1) but no longer
    qualifies under tightened rules is therefore left with a STALE
    passes_screen=1 on its filing row, and would wrongly stay in the curated
    "shown" universe (which keys off filings via curation.screen_predicate).

    This copies the ledger's verdict onto every current filing that has a
    matching ledger row, so the stored screen flag can never drift from the
    re-screen. Returns the number of filing rows updated. Idempotent.
    """
    where_q = ""
    params: list = []
    if quarters:
        placeholders = ",".join("?" for _ in quarters)
        where_q = f" AND f.quarter_label IN ({placeholders})"
        params = list(quarters)
    cur = conn.execute(
        f"""UPDATE filings AS f
            SET passes_screen = (
                    SELECT qs.passes_screen FROM quarter_screen qs
                    WHERE qs.cik = f.cik AND qs.quarter_label = f.quarter_label),
                filer_type = (
                    SELECT qs.filer_type FROM quarter_screen qs
                    WHERE qs.cik = f.cik AND qs.quarter_label = f.quarter_label)
            WHERE EXISTS (
                    SELECT 1 FROM quarter_screen qs
                    WHERE qs.cik = f.cik AND qs.quarter_label = f.quarter_label){where_q}""",
        params,
    )
    conn.commit()
    return cur.rowcount


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
