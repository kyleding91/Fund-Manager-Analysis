"""13F Fund Tracker — local dashboard.

Run it with:   streamlit run app.py
(Make sure you've loaded at least one quarter first: python ingest.py --quarter 2025Q2)
"""
from __future__ import annotations

import sqlite3

import altair as alt
import pandas as pd
import streamlit as st

from src import classify, config, insights, queries

st.set_page_config(page_title="13F Fund Tracker", page_icon="📈", layout="wide")


# --- data access ---------------------------------------------------------
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def usd(x: float) -> str:
    if x is None:
        return "-"
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(x) >= div:
            return f"${x/div:,.2f}{unit}"
    return f"${x:,.0f}"


def with_types(funds: pd.DataFrame) -> pd.DataFrame:
    """Attach a filer category + emoji label to each fund (name-based heuristic)."""
    if funds.empty:
        return funds.assign(category=[], type_label=[])
    cats = funds["manager_name"].map(classify.classify_manager)
    return funds.assign(
        category=cats,
        type_label=funds["manager_name"].map(classify.label),
    )


if not config.DB_PATH.exists():
    st.title("📈 13F Fund Tracker")
    st.warning(
        "No database found yet. Load a quarter first, e.g.:\n\n"
        "`python ingest.py --quarter 2025Q2`"
    )
    st.stop()

conn = get_conn()
quarters = queries.list_quarters(conn)
if not quarters:
    st.title("📈 13F Fund Tracker")
    st.warning("The database has no screened funds yet. Run `python ingest.py --quarter 2025Q2`.")
    st.stop()

# --- sidebar (filters) ---------------------------------------------------
st.sidebar.header("Filters")
quarter = st.sidebar.selectbox("Quarter", quarters, index=0)
managers_only = st.sidebar.toggle(
    "Investment managers only", value=True,
    help="Hide pensions, sovereign funds, foundations, banks, market-makers and "
         "operating companies — leaving only real stock-pickers.",
)
type_choices = [
    classify.MANAGER, classify.FOUNDATION, classify.PENSION,
    classify.BANK, classify.MARKET_MAKER, classify.OPERATING,
]
picked_types = st.sidebar.multiselect(
    "Filer types",
    type_choices,
    default=type_choices,
    format_func=lambda c: f"{classify.CATEGORY_EMOJI[c]} {c}",
    disabled=managers_only,
    help="Shown only when the 'Investment managers only' toggle is off.",
)
min_aum_b = st.sidebar.slider("Min AUM ($B)", 2.0, 50.0, 2.0, 0.5)
max_iss = st.sidebar.slider("Max # issuers", 1, 29, 29)
search = st.sidebar.text_input("Search manager name")
st.sidebar.caption(
    f"Screen: AUM > ${config.MIN_AUM_USD/1e9:.0f}B and "
    f"< {config.MAX_HOLDINGS} distinct issuers."
)

st.title("📈 13F Fund Tracker")
fresh = queries.data_freshness(conn, quarter)
loaded = (fresh["last_loaded"] or "")[:10]
st.caption(
    f"Value-oriented, concentrated managers — SEC EDGAR 13F filings · "
    f"**{quarter}** · {fresh['num_funds']} screened filers"
    + (f" · data loaded {loaded}" if loaded else "")
)


# --- shared data: screened funds for the chosen quarter, with types ------
all_funds = with_types(queries.list_funds(
    conn, quarter=quarter, min_aum=min_aum_b * 1e9, max_issuers=max_iss, search=search,
))


def apply_type_filter(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if managers_only:
        return df[df["category"] == classify.MANAGER]
    return df[df["category"].isin(picked_types)]


tab_overview, tab_funds, tab_search, tab_insights = st.tabs(
    ["🌐 Overview", "🏦 Funds", "🔎 Find a stock", "💡 Insights"]
)

# =========================================================================
# TAB 0 — Overview (the universe at a glance)
# =========================================================================
with tab_overview:
    funds = apply_type_filter(all_funds)
    st.subheader(f"The screened universe — {quarter}")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Funds", len(funds))
    k2.metric("Combined AUM", usd(funds["total_aum_usd"].sum()) if len(funds) else "-")
    k3.metric("Median # issuers", int(funds["num_issuers"].median()) if len(funds) else 0)
    k4.metric("Total positions", int(funds["num_positions"].sum()) if len(funds) else 0)

    if funds.empty:
        st.info("No funds match these filters.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**AUM distribution ($B)**")
            aum_chart = (
                alt.Chart(funds.assign(AUM_B=funds["total_aum_usd"] / 1e9))
                .mark_bar(color="#0E7C66")
                .encode(
                    x=alt.X("AUM_B:Q", bin=alt.Bin(maxbins=30), title="AUM ($B)"),
                    y=alt.Y("count()", title="# funds"),
                    tooltip=[alt.Tooltip("count()", title="# funds")],
                )
                .properties(height=260)
            )
            st.altair_chart(aum_chart, use_container_width=True)
        with c2:
            st.markdown("**Holdings-count distribution (# issuers)**")
            iss_chart = (
                alt.Chart(funds)
                .mark_bar(color="#1A2B3C")
                .encode(
                    x=alt.X("num_issuers:Q", bin=alt.Bin(maxbins=29),
                            title="# distinct issuers"),
                    y=alt.Y("count()", title="# funds"),
                    tooltip=[alt.Tooltip("count()", title="# funds")],
                )
                .properties(height=260)
            )
            st.altair_chart(iss_chart, use_container_width=True)

        # Filer-type mix uses the UNFILTERED set so you can see what's being excluded.
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Filer-type mix** (before the type filter)")
            mix = (
                all_funds.groupby("type_label")
                .agg(funds=("cik", "count"), aum=("total_aum_usd", "sum"))
                .reset_index()
                .sort_values("funds", ascending=False)
            )
            mix_chart = (
                alt.Chart(mix)
                .mark_bar(color="#0E7C66")
                .encode(
                    x=alt.X("funds:Q", title="# funds"),
                    y=alt.Y("type_label:N", sort="-x", title=None),
                    tooltip=["type_label", "funds"],
                )
                .properties(height=260)
            )
            st.altair_chart(mix_chart, use_container_width=True)
        with c4:
            st.markdown("**Most concentrated funds** (top position % of portfolio)")
            conc = insights.top_concentration(conn, quarter, limit=10)
            if not conc.empty:
                conc_disp = conc.assign(
                    AUM=conc["total_aum_usd"].map(usd),
                    Top=conc["top_pct"].map(lambda p: f"{p:.0f}%"),
                )[["manager_name", "top_holding", "Top", "AUM"]]
                conc_disp.columns = ["Manager", "Top holding", "Top %", "AUM"]
                st.dataframe(conc_disp, use_container_width=True, hide_index=True,
                             height=260)

        st.markdown("**Most-held stocks** (conviction across screened funds)")
        held = insights.most_held(conn, quarter, limit=15)
        if not held.empty:
            held_chart = (
                alt.Chart(held)
                .mark_bar(color="#0E7C66")
                .encode(
                    x=alt.X("num_funds:Q", title="# funds holding"),
                    y=alt.Y("issuer:N", sort="-x", title=None),
                    tooltip=["issuer", "num_funds",
                             alt.Tooltip("total_value:Q", title="Total $", format=",.0f")],
                )
                .properties(height=380)
            )
            st.altair_chart(held_chart, use_container_width=True)

# =========================================================================
# TAB 1 — Funds list + detail
# =========================================================================
with tab_funds:
    funds = apply_type_filter(all_funds)
    c1, c2, c3 = st.columns(3)
    c1.metric("Funds in screen", len(funds))
    c2.metric("Combined AUM", usd(funds["total_aum_usd"].sum()) if len(funds) else "-")
    c3.metric("Median # issuers", int(funds["num_issuers"].median()) if len(funds) else 0)

    if funds.empty:
        st.info("No funds match these filters.")
    else:
        show = funds.assign(AUM_B=funds["total_aum_usd"] / 1e9)[
            ["manager_name", "type_label", "AUM_B", "num_issuers",
             "num_positions", "form_type", "date_filed"]
        ].rename(columns={
            "manager_name": "Manager", "type_label": "Type",
            "num_issuers": "# Issuers", "num_positions": "# Positions",
            "form_type": "Form", "date_filed": "Filed",
        })
        st.dataframe(
            show, use_container_width=True, hide_index=True,
            column_config={
                "AUM_B": st.column_config.NumberColumn(
                    "AUM ($B)", format="$%.2fB",
                    help="13F assets under management, in billions (click to sort).",
                ),
            },
        )
        # CSV keeps the exact dollar AUM (not the rounded $B display value).
        csv = funds.assign(category=funds["category"])[
            ["manager_name", "category", "total_aum_usd", "num_issuers",
             "num_positions", "form_type", "date_filed", "quarter_label"]
        ]
        st.download_button(
            "⬇️ Download this list (CSV)",
            data=csv.to_csv(index=False).encode("utf-8"),
            file_name=f"13f_funds_{quarter}.csv",
            mime="text/csv",
        )

        st.subheader("Fund detail")
        pick = st.selectbox(
            "Pick a manager",
            funds["filing_id"],
            format_func=lambda fid: funds.set_index("filing_id").loc[fid, "manager_name"],
        )
        frow = funds.set_index("filing_id").loc[pick]
        st.caption(frow["type_label"])
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("AUM", usd(frow["total_aum_usd"]))
        m2.metric("# Issuers", int(frow["num_issuers"]))
        m3.metric("# Positions", int(frow["num_positions"]))
        m4.metric("Quarter", frow["quarter_label"])

        holds = queries.fund_holdings(conn, int(pick))
        left, right = st.columns([3, 2])
        with left:
            st.markdown("**Holdings**")
            disp = holds.assign(Value_M=holds["value_usd"] / 1e6, Shares=holds["shares"])[
                ["name_of_issuer", "title_of_class", "Value_M", "Shares",
                 "shares_type", "pct_of_portfolio"]
            ]
            disp.columns = ["Issuer", "Class", "Value_M", "Shares", "Type", "% Port."]
            st.dataframe(
                disp, use_container_width=True, hide_index=True, height=430,
                column_config={
                    "Value_M": st.column_config.NumberColumn("Value ($M)", format="$%.1f"),
                    "Shares": st.column_config.NumberColumn("Shares", format="%.0f"),
                    "% Port.": st.column_config.ProgressColumn(
                        "% Port.", format="%.1f%%", min_value=0.0,
                        max_value=float(holds["pct_of_portfolio"].max() or 100.0),
                    ),
                },
            )
        with right:
            st.markdown("**Portfolio weights (top 12)**")
            top = holds.head(12)
            chart = (
                alt.Chart(top)
                .mark_bar(color="#0E7C66")
                .encode(
                    x=alt.X("pct_of_portfolio:Q", title="% of portfolio"),
                    y=alt.Y("name_of_issuer:N", sort="-x", title=None),
                    tooltip=["name_of_issuer", "pct_of_portfolio"],
                )
                .properties(height=430)
            )
            st.altair_chart(chart, use_container_width=True)

        # AUM-over-time (Phase 5 enrichment, shown here when >1 quarter exists)
        tl = queries.fund_timeline(conn, frow["cik"])
        if len(tl) > 1:
            st.markdown("**AUM over time**")
            tl2 = tl.assign(AUM_B=tl["total_aum_usd"] / 1e9)
            line = (
                alt.Chart(tl2).mark_line(point=True, color="#0E7C66")
                .encode(x="quarter_label:N", y=alt.Y("AUM_B:Q", title="AUM ($B)"),
                        tooltip=["quarter_label", "num_issuers", "AUM_B"])
            )
            st.altair_chart(line, use_container_width=True)

# =========================================================================
# TAB 2 — Find a stock across funds
# =========================================================================
with tab_search:
    st.markdown("See which screened managers hold a given stock.")
    term = st.text_input("Stock / issuer name contains", "")
    if term:
        hits = queries.search_by_stock(conn, term, quarter=quarter)
        if hits.empty:
            st.info(f"No screened fund in {quarter} holds a stock matching '{term}'.")
        else:
            st.caption(f"{len(hits)} holdings across {hits['manager_name'].nunique()} funds in {quarter}.")
            disp = hits.assign(Value_M=hits["value_usd"] / 1e6, Shares=hits["shares"])[
                ["manager_name", "name_of_issuer", "Value_M", "Shares",
                 "pct_of_portfolio"]
            ]
            disp.columns = ["Manager", "Issuer", "Value_M", "Shares", "% Port."]
            st.dataframe(
                disp, use_container_width=True, hide_index=True,
                column_config={
                    "Value_M": st.column_config.NumberColumn("Value ($M)", format="$%.1f"),
                    "Shares": st.column_config.NumberColumn("Shares", format="%.0f"),
                    "% Port.": st.column_config.NumberColumn("% Port.", format="%.1f%%"),
                },
            )

# =========================================================================
# TAB 3 — Insights (Phase 5)
# =========================================================================
with tab_insights:
    insights.render(st, conn, quarter, usd)
