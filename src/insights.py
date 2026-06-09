"""Phase 5 — Insights & analysis.

Two layers:
  * pure-data functions (testable, no Streamlit) that compute insights from the DB
  * render() — the Streamlit "Insights" tab that presents them
"""
from __future__ import annotations

import pandas as pd

from . import curation


# --- helpers -------------------------------------------------------------
def previous_quarter(conn, quarter: str) -> str | None:
    """The screened quarter immediately before `quarter` (labels sort lexically)."""
    row = conn.execute(
        f"""SELECT MAX(quarter_label) FROM filings
           WHERE quarter_label < ? AND is_current = 1
             AND {curation.screen_predicate("")}""",
        (quarter,),
    ).fetchone()
    return row[0] if row and row[0] else None


# --- insight computations ------------------------------------------------
def most_held(conn, quarter: str, limit: int = 25) -> pd.DataFrame:
    """Stocks held by the most screened funds in a quarter (conviction signal)."""
    return pd.read_sql_query(
        f"""SELECT MAX(h.name_of_issuer) AS issuer,
                  COUNT(DISTINCT f.cik) AS num_funds,
                  SUM(h.value_usd)       AS total_value,
                  AVG(h.pct_of_portfolio) AS avg_pct
           FROM holdings h JOIN filings f ON f.id = h.filing_id
           WHERE f.is_current = 1 AND {curation.screen_predicate("f.")}
             AND f.quarter_label = :q
           GROUP BY h.issuer_cusip
           ORDER BY num_funds DESC, total_value DESC
           LIMIT :lim""",
        conn, params={"q": quarter, "lim": limit},
    )


def top_concentration(conn, quarter: str, limit: int = 25) -> pd.DataFrame:
    """Funds whose single largest position is the biggest share of the portfolio."""
    return pd.read_sql_query(
        f"""SELECT fn.manager_name, f.total_aum_usd, f.num_issuers,
                  (SELECT h2.name_of_issuer FROM holdings h2
                     WHERE h2.filing_id = f.id
                     ORDER BY h2.pct_of_portfolio DESC LIMIT 1) AS top_holding,
                  (SELECT MAX(h3.pct_of_portfolio) FROM holdings h3
                     WHERE h3.filing_id = f.id) AS top_pct
           FROM filings f JOIN funds fn ON fn.cik = f.cik
           WHERE f.is_current = 1 AND {curation.screen_predicate("f.")}
             AND f.quarter_label = :q
           ORDER BY top_pct DESC
           LIMIT :lim""",
        conn, params={"q": quarter, "lim": limit},
    )


def new_managers(conn, quarter: str) -> pd.DataFrame:
    """Funds that pass the screen this quarter but did not the previous quarter."""
    prev = previous_quarter(conn, quarter)
    if prev is None:
        return pd.DataFrame(columns=["manager_name", "total_aum_usd", "num_issuers"])
    return pd.read_sql_query(
        f"""SELECT fn.manager_name, f.total_aum_usd, f.num_issuers
           FROM filings f JOIN funds fn ON fn.cik = f.cik
           WHERE f.is_current = 1 AND {curation.screen_predicate("f.")}
             AND f.quarter_label = :q
             AND f.cik NOT IN (
                 SELECT cik FROM filings
                 WHERE is_current = 1 AND {curation.screen_predicate("")}
                   AND quarter_label = :prev)
           ORDER BY f.total_aum_usd DESC""",
        conn, params={"q": quarter, "prev": prev},
    )


def qoq_changes(conn, cik: str, quarter: str) -> pd.DataFrame | None:
    """Position-level changes for one fund vs. its previous screened quarter.

    Returns a DataFrame with a `change_type` of new / exited / added / trimmed /
    unchanged, or None if there is no prior quarter on file for this fund.
    """
    # Any current filing for the manager works here (not just screen-passing
    # ones): we backfill non-passing quarters' holdings so the quarter-over-
    # quarter comparison is continuous across a manager's full history.
    cur = conn.execute(
        """SELECT id, period_of_report FROM filings
           WHERE cik = ? AND quarter_label = ? AND is_current = 1""",
        (cik, quarter),
    ).fetchone()
    if not cur:
        return None
    prev = conn.execute(
        """SELECT id FROM filings
           WHERE cik = ? AND period_of_report < ? AND is_current = 1
           ORDER BY period_of_report DESC LIMIT 1""",
        (cik, cur["period_of_report"]),
    ).fetchone()
    if not prev:
        return None

    def _by_issuer(filing_id):
        return pd.read_sql_query(
            """SELECT issuer_cusip, MAX(name_of_issuer) AS issuer,
                      SUM(value_usd) AS value_usd, SUM(shares) AS shares
               FROM holdings WHERE filing_id = ? GROUP BY issuer_cusip""",
            conn, params=(filing_id,),
        ).set_index("issuer_cusip")

    c = _by_issuer(cur["id"])
    p = _by_issuer(prev["id"])
    merged = c.join(p, how="outer", lsuffix="_cur", rsuffix="_prev")
    merged["issuer"] = merged["issuer_cur"].fillna(merged["issuer_prev"])
    for col in ("value_usd_cur", "value_usd_prev", "shares_cur", "shares_prev"):
        merged[col] = merged[col].fillna(0.0)

    def classify(r):
        if r["shares_prev"] == 0 and r["shares_cur"] > 0:
            return "new"
        if r["shares_cur"] == 0 and r["shares_prev"] > 0:
            return "exited"
        if r["shares_cur"] > r["shares_prev"] * 1.001:
            return "added"
        if r["shares_cur"] < r["shares_prev"] * 0.999:
            return "trimmed"
        return "unchanged"

    merged["change_type"] = merged.apply(classify, axis=1)
    merged["value_delta"] = merged["value_usd_cur"] - merged["value_usd_prev"]
    out = merged.reset_index()[
        ["issuer", "change_type", "value_usd_cur", "value_usd_prev",
         "value_delta", "shares_cur", "shares_prev"]
    ].sort_values("value_usd_cur", ascending=False)
    return out


# --- UI ------------------------------------------------------------------
def render(st, conn, quarter: str, usd):  # pragma: no cover - UI glue
    st.markdown(f"### Insights for **{quarter}**")
    prev = previous_quarter(conn, quarter)
    st.caption(
        f"Comparing against **{prev}**." if prev
        else "Only one quarter is loaded — quarter-over-quarter views need a second quarter."
    )

    # -- Most-held stocks --------------------------------------------------
    st.markdown("#### 🏆 Most-held stocks across screened funds")
    mh = most_held(conn, quarter)
    if mh.empty:
        st.info("No holdings for this quarter.")
    else:
        disp = mh.assign(
            **{"Total value": mh["total_value"].map(usd),
               "Avg % of port.": mh["avg_pct"].map(lambda p: f"{p:.1f}%")}
        )[["issuer", "num_funds", "Total value", "Avg % of port."]]
        disp.columns = ["Issuer", "# Funds holding", "Total value", "Avg % of port."]
        st.dataframe(disp, use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    # -- Concentration -----------------------------------------------------
    with col1:
        st.markdown("#### 🎯 Highest single-position concentration")
        tc = top_concentration(conn, quarter, limit=15)
        if not tc.empty:
            disp = tc.assign(
                AUM=tc["total_aum_usd"].map(usd),
                Top=tc["top_pct"].map(lambda p: f"{p:.1f}%"),
            )[["manager_name", "top_holding", "Top", "AUM"]]
            disp.columns = ["Manager", "Top holding", "Top %", "AUM"]
            st.dataframe(disp, use_container_width=True, hide_index=True)

    # -- New managers ------------------------------------------------------
    with col2:
        st.markdown("#### 🆕 New to the screen this quarter")
        nm = new_managers(conn, quarter)
        if prev is None:
            st.info("Need a previous quarter to compute this.")
        elif nm.empty:
            st.info("No new managers entered the screen.")
        else:
            disp = nm.assign(AUM=nm["total_aum_usd"].map(usd))[
                ["manager_name", "AUM", "num_issuers"]
            ]
            disp.columns = ["Manager", "AUM", "# Issuers"]
            st.dataframe(disp, use_container_width=True, hide_index=True)

    # -- Per-fund QoQ ------------------------------------------------------
    st.markdown("#### 🔁 Quarter-over-quarter moves for one fund")
    funds = pd.read_sql_query(
        f"""SELECT fn.cik, fn.manager_name FROM filings f JOIN funds fn ON fn.cik = f.cik
           WHERE f.is_current = 1 AND {curation.screen_predicate("f.")}
             AND f.quarter_label = ?
           ORDER BY fn.manager_name""",
        conn, params=(quarter,),
    )
    if funds.empty:
        return
    pick = st.selectbox(
        "Manager", funds["cik"],
        format_func=lambda c: funds.set_index("cik").loc[c, "manager_name"],
    )
    changes = qoq_changes(conn, pick, quarter)
    if changes is None:
        st.info("No prior quarter on file for this manager, so no comparison yet.")
        return

    st.caption(
        "🟢 new / 🔼 added / 🔽 trimmed / 🔴 exited reflect changes in **share count** "
        "(what the manager actually bought or sold). The value columns can move "
        "differently because the stock price also changed."
    )
    counts = changes["change_type"].value_counts()
    cols = st.columns(4)
    for col, kind, emoji in zip(
        cols, ["new", "added", "trimmed", "exited"], ["🟢", "🔼", "🔽", "🔴"]
    ):
        col.metric(f"{emoji} {kind.title()}", int(counts.get(kind, 0)))

    view = changes[changes["change_type"] != "unchanged"].copy()
    view = view.assign(
        Now=view["value_usd_cur"].map(usd),
        Was=view["value_usd_prev"].map(usd),
        Δ=view["value_delta"].map(usd),
    )[["issuer", "change_type", "Now", "Was", "Δ"]]
    view.columns = ["Issuer", "Change", "Value now", "Value before", "Δ Value"]
    st.dataframe(view, use_container_width=True, hide_index=True)
