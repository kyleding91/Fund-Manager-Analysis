"""Assemble template-ready data for the static website (build_site.py).

This is the read-model for the published site. It reuses the same screened data
the Streamlit app uses (queries / classify / insights) but returns plain, JSON-
friendly dicts and lists so the Jinja2 templates stay dumb. Every monetary value
is provided both as a raw number (for client-side sorting) and a formatted string.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from . import classify, config, curation, insights, queries, roster


# --- formatting ----------------------------------------------------------
def usd_headline(x: float | None) -> str:
    """Coarse format for headline KPIs: $983B, $1.05T — 3 significant figures.

    Editorial-numbers convention: a hero number shouldn't carry cents-level
    precision its own subtitle rounds away; detail lives in the tables.
    """
    if x is None:
        return "-"
    ax = abs(x)
    if ax >= 1e12:
        return f"${x / 1e12:,.2f}T"
    if ax >= 1e10:
        return f"${x / 1e9:,.0f}B"
    return usd(x)


def usd(x: float | None) -> str:
    if x is None:
        return "-"
    sign = "−" if x < 0 else ""        # "−$3.41B", never "$-3.41B"
    ax = abs(x)
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if ax >= div:
            return f"{sign}${ax/div:,.2f}{unit}"
    return f"{sign}${ax:,.0f}"


def pct(x: float | None) -> str:
    return "-" if x is None else f"{x:.1f}%"


def sec_filing_url(cik: str, accession: str) -> str:
    """Link to the original filing's index page on SEC EDGAR.

    EDGAR's URL uses the CIK with no leading zeros and the accession number both
    with dashes (the filename) and without (the folder), e.g.
    .../edgar/data/1517857/000091957426003541/0000919574-26-003541-index.htm
    """
    if not cik or not accession:
        return ""
    acc_nodash = accession.replace("-", "")
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{acc_nodash}/{accession}-index.htm")


def connect_ro() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# --- small chart helpers (CSS/SVG, no JS chart lib) ----------------------
def _bars(rows: list[dict], value_key: str) -> list[dict]:
    """Attach a 0-100 `width` to each row, relative to the max value."""
    mx = max((r[value_key] for r in rows), default=0) or 1
    for r in rows:
        r["width"] = round(r[value_key] / mx * 100, 2)
    return rows


def _histogram(values: list[float], edges: list[float], labels: list[str]) -> list[dict]:
    """Bucket `values` into bins defined by `edges` (len labels == len edges-1)."""
    counts = [0] * (len(edges) - 1)
    for v in values:
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            last = i == len(edges) - 2
            if (lo <= v < hi) or (last and v == hi):
                counts[i] += 1
                break
    mx = max(counts, default=0) or 1
    return [{"label": labels[i], "count": counts[i],
             "height": round(counts[i] / mx * 100, 2)} for i in range(len(counts))]


def aum_timeline_svg(points: list[dict], width=520, height=140, pad=24, fmt=usd) -> dict:
    """Build an inline-SVG line chart over time. `points`=[{label,value}].

    `fmt` formats the value shown in each point's tooltip (defaults to USD; pass
    a different formatter, e.g. for a plain count).
    """
    if len(points) < 2:
        return {}
    vals = [p["value"] for p in points]
    vmin, vmax = min(vals), max(vals)
    span = (vmax - vmin) or 1
    n = len(points)
    coords = []
    for i, p in enumerate(points):
        x = pad + (width - 2 * pad) * (i / (n - 1))
        y = height - pad - (height - 2 * pad) * ((p["value"] - vmin) / span)
        coords.append((round(x, 1), round(y, 1)))
    line = " ".join(f"{x},{y}" for x, y in coords)
    return {
        "width": width, "height": height,
        "polyline": line,
        "dots": [{"x": x, "y": y, "label": points[i]["label"],
                  "value": fmt(points[i]["value"])} for i, (x, y) in enumerate(coords)],
        "first_label": points[0]["label"], "last_label": points[-1]["label"],
    }


# --- public read-model ---------------------------------------------------
def quarters(conn) -> list[str]:
    return queries.list_quarters(conn)


def _fund_rows(conn, quarter: str) -> list[dict]:
    df = queries.list_funds(conn, quarter=quarter, min_aum=0, max_issuers=100000)
    rows = []
    for r in df.itertuples(index=False):
        # Skip "notice" filings that disclose no holdings (e.g. positions
        # reported by another manager): a $0 / 0-name row is noise in the
        # directory and the homepage stats.
        if not (r.num_positions or 0) and not (r.total_aum_usd or 0):
            continue
        # Prefer the stored firm-type tag (honors per-CIK overrides) so the
        # charts match the screen's actual decision; fall back to the name
        # heuristic only for older rows with no stored tag.
        stored = getattr(r, "filer_type", "") or ""
        cat = stored if stored in classify.CATEGORY_EMOJI else classify.classify_manager(r.manager_name)
        rows.append({
            "cik": str(r.cik),
            "manager_name": r.manager_name,
            "category": cat,
            "type_label": f"{classify.CATEGORY_EMOJI[cat]} {cat}",
            "emoji": classify.CATEGORY_EMOJI[cat],
            "is_manager": cat == classify.MANAGER,
            "aum_usd": float(r.total_aum_usd),
            "aum": usd(float(r.total_aum_usd)),
            "aum_b": round(float(r.total_aum_usd) / 1e9, 2),
            "num_issuers": int(r.num_issuers),
            "num_positions": int(r.num_positions),
            "form_type": r.form_type,
            "date_filed": r.date_filed,
            "quarter_label": r.quarter_label,
        })
    return rows


def directory(conn, quarter: str) -> list[dict]:
    """All screened filers for a quarter (template + client-side JSON)."""
    return _fund_rows(conn, quarter)


def all_manager_ciks(conn) -> list[str]:
    """Every manager with at least one stored (current) filing.

    We generate a deep-dive page for each, so a manager that qualified in an
    earlier quarter (but not the anchor quarter) still has a browsable page with
    its full backfilled history.
    """
    rows = conn.execute(
        "SELECT DISTINCT cik FROM filings WHERE is_current = 1"
    ).fetchall()
    # Don't build deep-dive pages for managers a human has excluded in
    # config/curation.yaml (they're hidden everywhere else on the site too).
    excluded = curation.excluded_ciks()
    return [str(r[0]) for r in rows if curation._norm(r[0]) not in excluded]


def universe(conn, quarter: str) -> dict:
    """Headline stats + chart data for the home page (one quarter).

    Every universe member is presented as an investment manager: firm type
    remains a database fact (used by the screen and kept in the CSV export),
    but the site doesn't split members by it — the owner's call.
    """
    rows = _fund_rows(conn, quarter)
    managers = rows  # all members are presented as managers

    # Bins cover EVERY member, including lapsed ones currently below the $2B
    # floor or above 30 names — the histograms must sum to the universe size.
    aum_hist = _histogram(
        [r["aum_b"] for r in rows],
        [0, 2, 5, 10, 25, 50, 100, 1e9],
        ["<$2B", "$2–5B", "$5–10B", "$10–25B", "$25–50B", "$50–100B", "$100B+"],
    )
    iss_hist = _histogram(
        [r["num_issuers"] for r in rows],
        [0, 5, 10, 15, 20, 25, 31, 100000],
        ["1–4", "5–9", "10–14", "15–19", "20–24", "25–30", "31+"],
    )

    mh = insights.most_held(conn, quarter, limit=15)
    most_held = _bars([
        {"issuer": row.issuer, "cusip": row.cusip, "num_funds": int(row.num_funds),
         "total_value": usd(float(row.total_value)),
         "avg_pct": pct(float(row.avg_pct))}
        for row in mh.itertuples(index=False)
    ], "num_funds")

    # "Highest single-position conviction": every member counts (they're all
    # presented as managers); just skip near-single-stake books, where a 100%
    # top position is trivial rather than a conviction signal.
    tc = insights.top_concentration(conn, quarter, limit=150)
    top_conc = [
        {"manager_name": row.manager_name, "top_holding": row.top_holding,
         "top_pct": pct(float(row.top_pct)), "top_pct_val": round(float(row.top_pct), 1),
         "aum": usd(float(row.total_aum_usd)),
         "cik": str(_cik_for(conn, row.manager_name, quarter))}
        for row in tc.itertuples(index=False)
        if int(row.num_issuers) >= 2
    ][:12]

    # New members this quarter — same definition as the This-quarter page
    # (roster joins), so the two lists can never disagree.
    chg = insights.screen_changes(conn, quarter) or {"entered": []}
    new_mgrs = [
        {"manager_name": r["manager_name"], "cik": str(r["cik"]),
         "aum": usd(float(r["total_aum_usd"] or 0)),
         "num_issuers": int(r["num_issuers"] or 0)}
        for r in chg["entered"]
    ][:12]

    total_aum = sum(r["aum_usd"] for r in rows)
    mgr_aum = sum(r["aum_usd"] for r in managers)
    med_iss = _median([r["num_issuers"] for r in managers]) if managers else 0
    return {
        "quarter": quarter,
        "prev_quarter": insights.previous_quarter(conn, quarter),
        "num_filers": len(rows),
        "num_managers": len(managers),
        "total_aum": usd_headline(total_aum),
        "manager_aum": usd_headline(mgr_aum),
        "median_issuers": med_iss,
        "total_positions": sum(r["num_positions"] for r in rows),
        "aum_hist": aum_hist,
        "issuer_hist": iss_hist,
        "most_held": most_held,
        "top_concentration": top_conc,
        "new_managers": new_mgrs,
    }


def stocks(conn, quarter: str, limit: int = 300) -> list[dict]:
    """Full most-held list for the stocks page, with raw values for sorting."""
    mh = insights.most_held(conn, quarter, limit=limit)
    return [{
        "cusip": row.cusip,
        "issuer": row.issuer,
        "num_funds": int(row.num_funds),
        "total_value": usd(float(row.total_value)),
        "total_value_usd": float(row.total_value),
        "avg_pct": pct(float(row.avg_pct)),
        "avg_pct_val": round(float(row.avg_pct), 2),
    } for row in mh.itertuples(index=False)]


def all_stock_cusips(conn, quarter: str) -> list[str]:
    """Issuer CUSIPs held by >=1 shown manager in the quarter (one page each)."""
    rows = conn.execute(
        f"""SELECT DISTINCT h.issuer_cusip
            FROM holdings h JOIN filings f ON f.id = h.filing_id
            WHERE f.is_current = 1 AND {curation.screen_predicate('f.')}
              AND f.quarter_label = ?
              AND h.issuer_cusip IS NOT NULL AND h.issuer_cusip != ''""",
        (quarter,),
    ).fetchall()
    return [str(r[0]) for r in rows]


def _shown_manager_count(conn, quarter: str) -> int:
    row = conn.execute(
        f"""SELECT COUNT(DISTINCT f.cik) FROM filings f
            WHERE f.is_current = 1 AND {curation.screen_predicate('f.')}
              AND f.quarter_label = ?""",
        (quarter,),
    ).fetchone()
    return int(row[0] or 0)


def stock_detail(conn, issuer_cusip: str, quarter: str, max_quarters: int = 5) -> dict | None:
    """Everything one stock page needs: holders, QoQ moves, and the 5-quarter trend.

    Mirrors `fund_detail`, pivoted to a single company: who in the screened
    universe holds it now, how each position changed since last quarter (by share
    count, like the manager pages), who newly bought or fully exited, and the
    combined position size + holder count over time.

    A company nobody holds anymore but that WAS held last quarter still gets a
    page — the "fully exited" story (who sold out, the trend dropping to zero).
    Returns None only when there's nothing to tell in either quarter.
    """
    cur = insights.holders_of(conn, issuer_cusip, quarter)
    prev_q = insights.previous_quarter(conn, quarter)
    prev = insights.holders_of(conn, issuer_cusip, prev_q) if prev_q else None
    if cur.empty and (prev is None or prev.empty):
        return None
    prev_val = {str(r.cik): float(r.value_usd or 0) for r in prev.itertuples(index=False)} if prev is not None else {}
    prev_sh = {str(r.cik): float(r.shares or 0) for r in prev.itertuples(index=False)} if prev is not None else {}
    prev_name = {str(r.cik): r.manager_name for r in prev.itertuples(index=False)} if prev is not None else {}

    issuer = cur.iloc[0].issuer if not cur.empty else prev.iloc[0].issuer
    emoji = _CHANGE_GLYPHS

    holders, new_buyers = [], []
    counts = {"new": 0, "added": 0, "trimmed": 0, "exited": 0}
    cur_ciks, total_value = set(), 0.0
    for r in cur.itertuples(index=False):
        cik = str(r.cik); cur_ciks.add(cik)
        v = float(r.value_usd or 0); sh = float(r.shares or 0)
        total_value += v
        psh = prev_sh.get(cik)
        if psh is None:
            change = "new"
        elif sh > psh:
            change = "added"
        elif sh < psh:
            change = "trimmed"
        else:
            change = "unchanged"
        if change in counts:
            counts[change] += 1
        delta = v - prev_val.get(cik, 0.0)
        row = {
            "cik": cik, "name": r.manager_name,
            "value": usd(v), "value_usd": v,
            "shares": f"{sh:,.0f}",
            "pct": pct(float(r.pct_of_portfolio or 0)),
            "pct_val": round(float(r.pct_of_portfolio or 0), 2),
            "change_type": change, "emoji": emoji.get(change, ""),
            "was": usd(prev_val[cik]) if cik in prev_val else "—",
            "delta": usd(delta), "delta_val": delta,
        }
        holders.append(row)
        if change == "new":
            new_buyers.append(row)

    # Exits: managers shown holding it last quarter but not this quarter.
    exits = [{
        "cik": cik, "name": prev_name[cik],
        "was": usd(prev_val.get(cik, 0.0)), "emoji": emoji["exited"],
    } for cik in prev_val if cik not in cur_ciks]
    counts["exited"] = len(exits)

    # 5-quarter trend: combined value + holder count + total shares (shown
    # universe only). A fully-exited company has no row for the anchor quarter,
    # so append an explicit zero point — the charts should drop to 0, not stop.
    trend_rows = [{"quarter": t.quarter, "total_value": float(t.total_value or 0),
                   "holders": int(t.holders or 0),
                   "total_shares": float(t.total_shares or 0)}
                  for t in insights.issuer_trend(conn, issuer_cusip).itertuples(index=False)]
    if cur.empty and (not trend_rows or trend_rows[-1]["quarter"] != quarter):
        trend_rows.append({"quarter": quarter, "total_value": 0.0,
                           "holders": 0, "total_shares": 0.0})
    tr = trend_rows[-max_quarters:]
    value_pts = [{"label": t["quarter"], "value": t["total_value"]} for t in tr]
    holder_pts = [{"label": t["quarter"], "value": t["holders"]} for t in tr]
    share_pts = [{"label": t["quarter"], "value": t["total_shares"]} for t in tr]

    universe = _shown_manager_count(conn, quarter)
    return {
        "cusip": issuer_cusip,
        "issuer": issuer,
        "quarter": quarter,
        "prev_quarter": prev_q,
        "num_holders": len(holders),
        "universe": universe,
        "total_value": usd(total_value),
        "total_shares": _shares(share_pts[-1]["value"]) if share_pts else "0",
        "holders": holders,
        "new_buyers": new_buyers,
        "exits": exits,
        "counts": [{"kind": k, "emoji": emoji[k], "n": counts[k]}
                   for k in ("new", "added", "trimmed", "exited")],
        "value_svg": aum_timeline_svg(value_pts),
        "holders_svg": aum_timeline_svg(holder_pts, fmt=lambda v: f"{int(v)}"),
        "shares_svg": aum_timeline_svg(share_pts, fmt=_shares),
        "trend": [{"quarter": t["quarter"], "value": usd(t["total_value"]),
                   "holders": t["holders"],
                   "shares": _shares(t["total_shares"])} for t in tr],
    }


def stock_page_cusips(conn, quarter: str) -> set[str]:
    """Issuers that get a stock page this build: held by a member in the anchor
    quarter OR in the prior one — so a company everyone just exited still has a
    page telling that story (and the moves page can link to it)."""
    cusips = set(all_stock_cusips(conn, quarter))
    prev_q = insights.previous_quarter(conn, quarter)
    if prev_q:
        cusips |= set(all_stock_cusips(conn, prev_q))
    return cusips


def _shares(x: float) -> str:
    """Compact share count: 59,700,000 -> '59.7M'."""
    ax = abs(x)
    if ax >= 1e9:
        return f"{x / 1e9:,.2f}B"
    if ax >= 1e6:
        return f"{x / 1e6:,.1f}M"
    if ax >= 1e4:
        return f"{x / 1e3:,.0f}K"
    return f"{x:,.0f}"


def _share_change(now: float, prev: float) -> str:
    """Human-readable share-count move: '+13.2M sh (+41%)'."""
    delta = now - prev
    if delta == 0:
        return "unchanged"
    sign = "+" if delta > 0 else "−"
    txt = f"{sign}{_shares(abs(delta))} sh"
    if prev > 0:
        txt += f" ({sign}{abs(delta) / prev * 100:,.0f}%)"
    return txt


# Change-indicator glyphs (B5): plain text, not emoji — emoji render
# inconsistently across platforms, read badly in screen readers, and encode
# meaning in hue alone. Color comes from the .chg-* pill styles; these glyphs
# add a shape signal and the templates pair them with the word itself.
_CHANGE_GLYPHS = {"new": "+", "added": "\u25b2", "trimmed": "\u25bc", "exited": "\u00d7"}


# Plain-English versions of the mechanical reject reasons, for the lapsed list.
_LAPSE_REASONS = {
    "aum_below_floor": "dipped below $2B",
    "not_concentrated": "drifted past the concentration limits",
    "below_min_holdings": "fewer than 3 names",
    "mostly_etfs": "book is now mostly ETFs",
    "too_many_holdings_for_weight": "top-heavy but holds more than 50 names",
    "confidential": "filed confidentially",
}


def _universe_stats(conn, quarter: str) -> dict:
    row = conn.execute(
        f"""SELECT COUNT(DISTINCT f.cik) AS n, SUM(f.total_aum_usd) AS aum
            FROM filings f
            WHERE f.is_current = 1 AND {curation.screen_predicate('f.')}
              AND f.quarter_label = ?""",
        (quarter,),
    ).fetchone()
    return {"count": int(row["n"] or 0), "aum_usd": float(row["aum"] or 0)}


def _holder_counts(conn, quarter: str) -> dict[str, int]:
    """Holders per issuer across the FULL shown universe in one quarter."""
    rows = conn.execute(
        f"""SELECT h.issuer_cusip AS cusip, COUNT(DISTINCT f.cik) AS n
            FROM holdings h JOIN filings f ON f.id = h.filing_id
            WHERE f.is_current = 1 AND {curation.screen_predicate('f.')}
              AND f.quarter_label = ?
            GROUP BY h.issuer_cusip""",
        (quarter,),
    ).fetchall()
    return {r["cusip"]: int(r["n"]) for r in rows}


def quarter_moves(conn, quarter: str, top_stocks: int = 12, top_moves: int = 10) -> dict | None:
    """Everything the "This quarter" money-moves page needs, or None if there
    is no prior quarter to compare against."""
    flows = insights.quarter_money_flows(conn, quarter)
    if flows is None:
        return None
    pairs = flows["pairs"]
    prev_q = flows["prev_quarter"]

    # Only link companies that actually get a stock page this build (held in
    # the anchor or the prior quarter — which includes full exits).
    linkable = stock_page_cusips(conn, quarter)
    # Holder counts shown to visitors use the FULL universe (matching the stock
    # pages), not just the members compared in the flow math.
    holders_now_all = _holder_counts(conn, quarter)
    holders_prev_all = _holder_counts(conn, prev_q)

    stocks_agg = insights.aggregate_stock_flows(pairs)

    def _stock_row(s):
        return {
            "cusip": s["cusip"], "issuer": s["issuer"],
            "linked": s["cusip"] in linkable,
            "net_flow": usd(abs(s["net_flow_usd"])),
            "net_flow_usd": s["net_flow_usd"],
            "share_change": _share_change(s["shares_now"], s["shares_prev"]),
            "n_new": s["n_new"], "n_added": s["n_added"],
            "n_trimmed": s["n_trimmed"], "n_exited": s["n_exited"],
            "holders_now": holders_now_all.get(s["cusip"], 0),
            "holders_prev": holders_prev_all.get(s["cusip"], 0),
            "value": usd(s["value_usd"]),
        }

    money_in = [_stock_row(s) for s in stocks_agg if s["net_flow_usd"] > 0][:top_stocks]
    money_out = [_stock_row(s) for s in reversed(stocks_agg)
                 if s["net_flow_usd"] < 0][:top_stocks]

    emoji = _CHANGE_GLYPHS

    def _pair_row(m):
        return {
            "cik": m["cik"], "manager_name": m["manager_name"],
            "cusip": m["cusip"], "issuer": m["issuer"],
            "linked": m["cusip"] in linkable,
            "change_type": m["change_type"], "emoji": emoji.get(m["change_type"], ""),
            "flow": usd(abs(m["flow_usd"])), "flow_usd": m["flow_usd"],
            "share_change": _share_change(m["shares"], m["prev_shares"]),
        }

    moved = sorted(pairs, key=lambda m: m["flow_usd"], reverse=True)
    biggest_buys = [_pair_row(m) for m in moved[:top_moves] if m["flow_usd"] > 0]
    biggest_sells = [_pair_row(m) for m in reversed(moved[-top_moves:])
                     if m["flow_usd"] < 0]

    gross_in = sum(m["flow_usd"] for m in pairs if m["flow_usd"] > 0)
    gross_out = sum(m["flow_usd"] for m in pairs if m["flow_usd"] < 0)

    chg = insights.screen_changes(conn, quarter) or {"entered": [], "left": [],
                                                     "lapsed": []}
    uni_now = _universe_stats(conn, quarter)
    uni_prev = _universe_stats(conn, prev_q)
    compared = len({m["cik"] for m in pairs})

    return {
        "quarter": quarter,
        "prev_quarter": prev_q,
        "universe": {
            "count": uni_now["count"], "aum": usd(uni_now["aum_usd"]),
            "prev_count": uni_prev["count"], "prev_aum": usd(uni_prev["aum_usd"]),
            "compared": compared,
        },
        "gross_in": usd(gross_in),
        "gross_out": usd(abs(gross_out)),
        "net": usd(abs(gross_in + gross_out)),
        "net_positive": (gross_in + gross_out) >= 0,
        "money_in": money_in,
        "money_out": money_out,
        "biggest_buys": biggest_buys,
        "biggest_sells": biggest_sells,
        "entered": [{"cik": str(r["cik"]), "name": r["manager_name"],
                     "aum": usd(float(r["total_aum_usd"] or 0)),
                     "num_issuers": int(r["num_issuers"] or 0)}
                    for r in chg["entered"]],
        "left": [{"cik": str(r["cik"]), "name": r["manager_name"],
                  "aum": usd(float(r["total_aum_usd"] or 0)),
                  "num_issuers": int(r["num_issuers"] or 0)}
                 for r in chg["left"]],
        "lapsed": [{"cik": str(r["cik"]), "name": r["manager_name"],
                    "aum": usd(float(r["total_aum_usd"] or 0)),
                    "num_issuers": int(r["num_issuers"] or 0),
                    "reason": ("filed without disclosing holdings"
                               if not (r["num_issuers"] or 0)
                               else _LAPSE_REASONS.get(r.get("reject_reason") or "",
                                                       r.get("reject_reason") or ""))}
                   for r in chg.get("lapsed", [])],
    }


def _cik_for(conn, manager_name: str, quarter: str) -> str:
    row = conn.execute(
        f"""SELECT f.cik FROM filings f JOIN funds fn ON fn.cik=f.cik
           WHERE fn.manager_name=? AND f.quarter_label=? AND f.is_current=1
             AND {curation.screen_predicate("f.")} LIMIT 1""",
        (manager_name, quarter),
    ).fetchone()
    return row[0] if row else ""


def _median(xs: list[int]) -> int:
    if not xs:
        return 0
    s = sorted(xs)
    n = len(s)
    return int(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def _holdings_for(conn, filing_id: int, linkable: set[str] | None = None) -> list[dict]:
    holds = queries.fund_holdings(conn, int(filing_id))
    max_pct = float(holds["pct_of_portfolio"].max() or 1) if len(holds) else 1
    linkable = linkable or set()
    out = []
    for h in holds.itertuples(index=False):
        cusip6 = (h.cusip or "")[:6].upper()
        out.append({
            "issuer": h.name_of_issuer, "title": h.title_of_class,
            "cusip6": cusip6,
            "linked": cusip6 in linkable,   # only link issuers that get a stock page
            "value": usd(float(h.value_usd)), "value_usd": float(h.value_usd),
            "shares": f"{float(h.shares):,.0f}", "shares_type": h.shares_type,
            "put_call": h.put_call or "",
            "pct": pct(float(h.pct_of_portfolio)),
            "pct_val": round(float(h.pct_of_portfolio), 2),
            "width": round(float(h.pct_of_portfolio) / max_pct * 100, 2),
        })
    return out


def _moves_for(conn, cik: str, quarter: str) -> dict | None:
    """QoQ moves for one fund/quarter, or None if there's no prior filing."""
    qoq = insights.qoq_changes(conn, str(cik), quarter)
    if qoq is None:
        return None
    nonzero = qoq[qoq["change_type"] != "unchanged"]
    counts = qoq["change_type"].value_counts().to_dict()
    emoji = _CHANGE_GLYPHS
    return {
        "counts": [{"kind": k, "emoji": emoji[k], "n": int(counts.get(k, 0))}
                   for k in ("new", "added", "trimmed", "exited")],
        "rows": [{
            "issuer": m.issuer, "change_type": m.change_type,
            "emoji": emoji.get(m.change_type, ""),
            "now": usd(float(m.value_usd_cur)), "was": usd(float(m.value_usd_prev)),
            "delta": usd(float(m.value_delta)),
            "delta_val": float(m.value_delta),
        } for m in nonzero.itertuples(index=False)],
    }


def fund_detail(conn, cik: str, quarter: str, max_quarters: int = 5,
                linkable: set[str] | None = None) -> dict | None:
    """Everything one fund page needs.

    Returns header info, the full AUM timeline (sparkline), and a list of the
    most recent `max_quarters` quarter snapshots (newest first). Each snapshot
    carries its own holdings and quarter-over-quarter moves, so the page can let
    the visitor switch between quarters client-side. All quarters we've ever
    loaded for the fund stay in the database; we simply surface the latest few.
    `linkable` is the set of issuer CUSIPs that get a stock page this build.
    """
    tl = queries.fund_timeline(conn, str(cik))
    if tl.empty:
        return None

    row = conn.execute("SELECT manager_name, filer_type FROM funds WHERE cik = ?",
                       (str(cik),)).fetchone()
    manager_name = row[0] if row else str(cik)
    stored = (row[1] if row else "") or ""
    cat = stored if stored in classify.CATEGORY_EMOJI else classify.classify_manager(manager_name)
    is_member = curation._norm(str(cik)) in roster.active_ciks()

    # Full history for the sparkline (oldest -> newest).
    timeline = [{"label": t.quarter_label, "value": float(t.total_aum_usd)}
                for t in tl.itertuples(index=False)]

    # Per-quarter mechanical reject reasons (plain English) for the callouts.
    reasons = {r["quarter_label"]: (r["reject_reason"] or "")
               for r in conn.execute(
                   "SELECT quarter_label, reject_reason FROM quarter_screen "
                   "WHERE cik = ?", (str(cik),))}

    # Newest -> oldest; display the most recent `max_quarters`, but look up each
    # quarter's predecessor in the FULL history (the oldest *displayed* quarter
    # usually still has an earlier filing on record — its moves compare to that).
    rows_all = list(tl.itertuples(index=False))[::-1]
    quarters = []
    for i, t in enumerate(rows_all[:max_quarters]):
        prev_label = rows_all[i + 1].quarter_label if i + 1 < len(rows_all) else None
        meets = bool(getattr(t, "passes_screen", 1))
        top_n_pct = float(getattr(t, "top_n_pct", 0.0) or 0.0)
        raw_reason = reasons.get(t.quarter_label, "")
        quarters.append({
            "quarter": t.quarter_label,
            "slug": t.quarter_label.replace("-", "").lower(),
            "period_of_report": t.period_of_report,
            "aum": usd(float(t.total_aum_usd)),
            "aum_usd": float(t.total_aum_usd),
            "num_issuers": int(t.num_issuers),
            "num_positions": int(t.num_positions),
            "top_n_pct": pct(top_n_pct),
            "meets_criteria": meets,
            "lapse_reason": _LAPSE_REASONS.get(raw_reason, raw_reason)
                            if not meets else "",
            "form_type": t.form_type,
            "date_filed": t.date_filed,
            "accession": t.accession,
            "sec_url": sec_filing_url(str(cik), str(t.accession)),
            "holdings": _holdings_for(conn, t.filing_id, linkable),
            "moves": _moves_for(conn, str(cik), t.quarter_label),
            "prev_quarter": prev_label,
        })

    return {
        "cik": str(cik),
        "manager_name": manager_name,
        "category": cat,
        "type_label": f"{classify.CATEGORY_EMOJI[cat]} {cat}",
        "emoji": classify.CATEGORY_EMOJI[cat],
        "is_member": is_member,
        "latest_quarter": quarters[0]["quarter"],
        "num_quarters_total": len(timeline),
        "timeline": timeline,
        "aum_svg": aum_timeline_svg(timeline),
        "quarters": quarters,
    }


def freshness(conn, quarter: str) -> dict:
    f = queries.data_freshness(conn, quarter)
    loaded = (f["last_loaded"] or "")[:10]
    return {"loaded": loaded, "num_funds": f["num_funds"],
            "generated": datetime.utcnow().strftime("%Y-%m-%d")}
