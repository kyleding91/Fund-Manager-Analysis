"""Phase 5 — Insights & analysis.

Two layers:
  * pure-data functions (testable, no Streamlit) that compute insights from the DB
  * render() — the Streamlit "Insights" tab that presents them
"""
from __future__ import annotations

import pandas as pd

from . import curation, roster


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
        f"""SELECT h.issuer_cusip AS cusip,
                  MAX(h.name_of_issuer) AS issuer,
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


def holders_of(conn, issuer_cusip: str, quarter: str) -> pd.DataFrame:
    """Every shown manager holding one issuer in a quarter (largest first).

    Aggregates a manager's positions in the issuer (common + any share classes /
    options that share the 6-digit issuer CUSIP) into one row. Only managers in
    the curated, screened universe are counted, matching the rest of the site.
    """
    return pd.read_sql_query(
        f"""SELECT f.cik, fn.manager_name, f.filer_type,
                  MAX(h.name_of_issuer)    AS issuer,
                  SUM(h.value_usd)         AS value_usd,
                  SUM(h.shares)            AS shares,
                  SUM(h.pct_of_portfolio)  AS pct_of_portfolio
           FROM holdings h
           JOIN filings f ON f.id = h.filing_id
           JOIN funds fn  ON fn.cik = f.cik
           WHERE h.issuer_cusip = :cusip AND f.is_current = 1
             AND {curation.screen_predicate("f.")} AND f.quarter_label = :q
           GROUP BY f.cik
           ORDER BY value_usd DESC""",
        conn, params={"cusip": issuer_cusip, "q": quarter},
    )


def issuer_trend(conn, issuer_cusip: str) -> pd.DataFrame:
    """Per-quarter combined position + holder count for one issuer (oldest first).

    Counts only the shown universe each quarter, so a manager parked below the
    screen in some quarter (kept in the DB for history) isn't double-counted.
    """
    return pd.read_sql_query(
        f"""SELECT f.quarter_label AS quarter,
                  COUNT(DISTINCT f.cik) AS holders,
                  SUM(h.value_usd)      AS total_value,
                  SUM(h.shares)         AS total_shares
           FROM holdings h JOIN filings f ON f.id = h.filing_id
           WHERE h.issuer_cusip = :cusip AND f.is_current = 1
             AND {curation.screen_predicate("f.")}
           GROUP BY f.quarter_label
           ORDER BY f.quarter_label""",
        conn, params={"cusip": issuer_cusip},
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


def _positions_by_pair(conn, quarter: str) -> dict:
    """{(cik, issuer_cusip): position} for every shown manager in a quarter.

    One entry per manager x company, with share classes/options aggregated by
    the 6-digit issuer CUSIP (same convention as the rest of the project).
    """
    rows = conn.execute(
        f"""SELECT f.cik, h.issuer_cusip AS cusip,
                  MAX(h.name_of_issuer)  AS issuer,
                  MAX(fn.manager_name)   AS manager_name,
                  SUM(h.value_usd)       AS value_usd,
                  SUM(h.shares)          AS shares
           FROM holdings h
           JOIN filings f ON f.id = h.filing_id
           JOIN funds fn  ON fn.cik = f.cik
           WHERE f.is_current = 1 AND {curation.screen_predicate("f.")}
             AND f.quarter_label = ?
             AND h.issuer_cusip IS NOT NULL AND h.issuer_cusip != ''
           GROUP BY f.cik, h.issuer_cusip""",
        (quarter,),
    ).fetchall()
    return {(str(r["cik"]), r["cusip"]): {
        "issuer": r["issuer"], "manager_name": r["manager_name"],
        "value_usd": float(r["value_usd"] or 0), "shares": float(r["shares"] or 0),
    } for r in rows}


def quarter_money_flows(conn, quarter: str) -> dict | None:
    """Estimated dollar flows for every (manager, company) pair vs last quarter.

    The honest way to measure "money moving": a position's VALUE change mixes
    real buying/selling with price moves, so instead we estimate
        flow = (shares now - shares before) x implied share price
    where the implied price is value/shares from the current filing (or the
    prior one for full exits). Pairs with no share counts (rare: options-only
    or principal-amount lines) fall back to the raw value change.

    "Same-store" rule: flows are computed only across managers shown in BOTH
    quarters. A manager that just entered the screen would otherwise count its
    whole book as "new buying" (and a leaver as selling) — that's universe
    churn, not money moving; entrants/leavers are reported separately by
    screen_changes().

    Returns {"prev_quarter", "pairs": [...]} or None when there is no prior
    quarter to compare against. Each pair: cik, manager_name, cusip, issuer,
    change_type (new/exited/added/trimmed/unchanged), flow_usd, value_usd
    (current, 0 for exits), prev_value_usd.
    """
    prev_q = previous_quarter(conn, quarter)
    if prev_q is None:
        return None
    cur = _positions_by_pair(conn, quarter)
    prev = _positions_by_pair(conn, prev_q)

    # Same-store: only managers present in both quarters' shown universes.
    both = ({cik for (cik, _) in cur} & {cik for (cik, _) in prev})
    cur = {k: v for k, v in cur.items() if k[0] in both}
    prev = {k: v for k, v in prev.items() if k[0] in both}

    pairs = []
    for key in cur.keys() | prev.keys():
        c, p = cur.get(key), prev.get(key)
        sh_c = c["shares"] if c else 0.0
        sh_p = p["shares"] if p else 0.0
        v_c = c["value_usd"] if c else 0.0
        v_p = p["value_usd"] if p else 0.0
        if c and not p:
            change = "new"
        elif p and not c:
            change = "exited"
        elif sh_c > sh_p:
            change = "added"
        elif sh_c < sh_p:
            change = "trimmed"
        else:
            change = "unchanged"
        if sh_c > 0:
            price = v_c / sh_c
        elif sh_p > 0:
            price = v_p / sh_p
        else:
            price = 0.0
        flow = (sh_c - sh_p) * price if price > 0 else (v_c - v_p)
        src = c or p
        pairs.append({
            "cik": key[0], "cusip": key[1],
            "manager_name": src["manager_name"], "issuer": src["issuer"],
            "change_type": change, "flow_usd": flow,
            "value_usd": v_c, "prev_value_usd": v_p,
            "shares": sh_c, "prev_shares": sh_p,
        })
    return {"prev_quarter": prev_q, "pairs": pairs}


def aggregate_stock_flows(pairs: list[dict]) -> list[dict]:
    """Roll per-(manager, company) flows up to one row per company.

    Each row: cusip, issuer, counts of new/exited/added/trimmed managers,
    holders now/before, estimated net flow (and gross in/out), and the combined
    current position value. Sorted by net flow descending.
    """
    by_stock: dict[str, dict] = {}
    for m in pairs:
        s = by_stock.setdefault(m["cusip"], {
            "cusip": m["cusip"], "issuer": m["issuer"],
            "n_new": 0, "n_exited": 0, "n_added": 0, "n_trimmed": 0,
            "holders_now": 0, "holders_prev": 0,
            "inflow_usd": 0.0, "outflow_usd": 0.0, "net_flow_usd": 0.0,
            "value_usd": 0.0, "shares_now": 0.0, "shares_prev": 0.0,
        })
        kind = m["change_type"]
        if kind in ("new", "exited", "added", "trimmed"):
            s[f"n_{kind}"] += 1
        if kind != "exited":
            s["holders_now"] += 1
        if kind != "new":
            s["holders_prev"] += 1
        if m["flow_usd"] >= 0:
            s["inflow_usd"] += m["flow_usd"]
        else:
            s["outflow_usd"] += m["flow_usd"]
        s["net_flow_usd"] += m["flow_usd"]
        s["value_usd"] += m["value_usd"]
        s["shares_now"] += m["shares"]
        s["shares_prev"] += m["prev_shares"]
    return sorted(by_stock.values(), key=lambda s: s["net_flow_usd"], reverse=True)


def screen_changes(conn, quarter: str) -> dict | None:
    """Membership changes for the quarter.

    With a sticky roster (config/roster.yaml): `entered` = members whose first
    qualifying quarter is this one; `lapsed` = active members kept on the
    roster even though they failed this quarter's mechanical screen (each with
    the reject reason — the human review queue). Nobody leaves automatically.

    Without a roster (pre-roster / tests): falls back to the per-quarter
    diff — `entered` / `left` vs the previous quarter.
    """
    prev_q = previous_quarter(conn, quarter)
    if prev_q is None:
        return None

    def shown(q):
        rows = conn.execute(
            f"""SELECT f.cik, fn.manager_name, f.total_aum_usd, f.num_issuers
               FROM filings f JOIN funds fn ON fn.cik = f.cik
               WHERE f.is_current = 1 AND {curation.screen_predicate("f.")}
                 AND f.quarter_label = ?""",
            (q,),
        ).fetchall()
        return {curation._norm(str(r["cik"])): dict(r) for r in rows}

    cur = shown(quarter)

    if roster.has_roster():
        joined = roster.joined_in(quarter)
        entered = sorted((cur[c] for c in cur if c in joined),
                         key=lambda r: r["total_aum_usd"] or 0, reverse=True)
        rows = conn.execute(
            f"""SELECT f.cik, fn.manager_name, f.total_aum_usd, f.num_issuers,
                      qs.reject_reason
               FROM filings f
               JOIN funds fn ON fn.cik = f.cik
               JOIN quarter_screen qs ON qs.cik = f.cik
                    AND qs.quarter_label = f.quarter_label
               WHERE f.is_current = 1 AND f.quarter_label = ?
                 AND {curation.screen_predicate("f.")}
                 AND qs.passes_screen = 0
               ORDER BY f.total_aum_usd DESC""",
            (quarter,),
        ).fetchall()
        lapsed = [dict(r) for r in rows]
        return {"prev_quarter": prev_q, "entered": entered,
                "lapsed": lapsed, "left": []}

    prev = shown(prev_q)
    entered = sorted((cur[c] for c in cur.keys() - prev.keys()),
                     key=lambda r: r["total_aum_usd"] or 0, reverse=True)
    left = sorted((prev[c] for c in prev.keys() - cur.keys()),
                  key=lambda r: r["total_aum_usd"] or 0, reverse=True)
    return {"prev_quarter": prev_q, "entered": entered, "left": left, "lapsed": []}


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
