"""Read-side queries used by the dashboard (Phase 4) and insights (Phase 5).

Every function takes an open sqlite3 connection and returns a pandas DataFrame
(or simple Python value), so the UI layer stays thin.
"""
from __future__ import annotations

import pandas as pd

# Only ever show filings that passed the screen and are the latest for their period.
_CURRENT = "f.is_current = 1 AND f.passes_screen = 1"


def list_quarters(conn) -> list[str]:
    rows = conn.execute(
        f"SELECT DISTINCT f.quarter_label FROM filings f WHERE {_CURRENT} "
        "ORDER BY f.quarter_label DESC"
    ).fetchall()
    return [r[0] for r in rows if r[0]]


def data_freshness(conn, quarter: str | None = None) -> dict:
    """When this data was loaded and how many screened funds it covers."""
    sql = (
        f"SELECT COUNT(*) AS n, MAX(f.loaded_at) AS last_loaded "
        f"FROM filings f WHERE {_CURRENT}"
    )
    params: dict = {}
    if quarter:
        sql += " AND f.quarter_label = :quarter"
        params["quarter"] = quarter
    row = conn.execute(sql, params).fetchone()
    return {"num_funds": row[0] or 0, "last_loaded": row[1]}


def list_funds(conn, *, quarter: str | None = None, min_aum: float = 0,
               max_issuers: int = 10_000, search: str = "") -> pd.DataFrame:
    """Funds passing the screen, newest filing per period, sorted by AUM desc."""
    sql = f"""
        SELECT f.id AS filing_id, f.cik, fn.manager_name, f.quarter_label,
               f.period_of_report, f.total_aum_usd, f.num_positions, f.num_issuers,
               f.form_type, f.date_filed, f.accession
        FROM filings f JOIN funds fn ON fn.cik = f.cik
        WHERE {_CURRENT}
          AND f.total_aum_usd >= :min_aum
          AND f.num_issuers <= :max_issuers
    """
    params: dict = {"min_aum": min_aum, "max_issuers": max_issuers}
    if quarter:
        sql += " AND f.quarter_label = :quarter"
        params["quarter"] = quarter
    if search:
        sql += " AND fn.manager_name LIKE :search"
        params["search"] = f"%{search}%"
    sql += " ORDER BY f.total_aum_usd DESC"
    return pd.read_sql_query(sql, conn, params=params)


def fund_holdings(conn, filing_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT name_of_issuer, title_of_class, cusip, value_usd, shares,
                  shares_type, put_call, pct_of_portfolio
           FROM holdings WHERE filing_id = :fid
           ORDER BY value_usd DESC""",
        conn, params={"fid": filing_id},
    )


def fund_timeline(conn, cik: str) -> pd.DataFrame:
    """All current filings for one manager, oldest->newest (for AUM-over-time).

    Includes quarters where the manager did NOT pass the screen but whose
    holdings we backfilled for history, so a manager's deep-dive shows a
    continuous timeline. `passes_screen` is returned so the UI can mark which
    quarters actually met the selection criteria.
    """
    return pd.read_sql_query(
        """SELECT id AS filing_id, quarter_label, period_of_report, total_aum_usd,
                  num_positions, num_issuers, top_n_pct, passes_screen,
                  form_type, date_filed, accession
           FROM filings
           WHERE cik = :cik AND is_current = 1
           ORDER BY period_of_report ASC""",
        conn, params={"cik": cik},
    )


def search_by_stock(conn, text: str, quarter: str | None = None) -> pd.DataFrame:
    """Which screened funds hold a given stock (by issuer name)?"""
    sql = f"""
        SELECT fn.manager_name, f.quarter_label, h.name_of_issuer, h.value_usd,
               h.shares, h.pct_of_portfolio
        FROM holdings h
        JOIN filings f ON f.id = h.filing_id
        JOIN funds fn ON fn.cik = f.cik
        WHERE {_CURRENT} AND h.name_of_issuer LIKE :text
    """
    params = {"text": f"%{text}%"}
    if quarter:
        sql += " AND f.quarter_label = :quarter"
        params["quarter"] = quarter
    sql += " ORDER BY h.value_usd DESC"
    return pd.read_sql_query(sql, conn, params=params)
