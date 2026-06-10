"""Assemble template-ready data for the static website (build_site.py).

This is the read-model for the published site. It reuses the same screened data
the Streamlit app uses (queries / classify / insights) but returns plain, JSON-
friendly dicts and lists so the Jinja2 templates stay dumb. Every monetary value
is provided both as a raw number (for client-side sorting) and a formatted string.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from . import classify, config, curation, insights, queries


# --- formatting ----------------------------------------------------------
def usd(x: float | None) -> str:
    if x is None:
        return "-"
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(x) >= div:
            return f"${x/div:,.2f}{unit}"
    return f"${x:,.0f}"


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
    """Headline stats + chart data for the home page (one quarter)."""
    rows = _fund_rows(conn, quarter)
    managers = [r for r in rows if r["is_manager"]]

    # filer-type mix (all screened filers)
    by_cat: dict[str, dict] = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], {
            "category": r["category"], "emoji": r["emoji"],
            "label": r["category"], "count": 0, "aum_usd": 0.0})
        c["count"] += 1
        c["aum_usd"] += r["aum_usd"]
    mix = sorted(by_cat.values(), key=lambda d: d["count"], reverse=True)
    _bars(mix, "count")

    aum_hist = _histogram(
        [r["aum_b"] for r in rows],
        [2, 5, 10, 25, 50, 100, 1e9],
        ["$2–5B", "$5–10B", "$10–25B", "$25–50B", "$50–100B", "$100B+"],
    )
    iss_hist = _histogram(
        [r["num_issuers"] for r in rows],
        [0, 5, 10, 15, 20, 25, 30],
        ["1–4", "5–9", "10–14", "15–19", "20–24", "25–29"],
    )

    mh = insights.most_held(conn, quarter, limit=15)
    most_held = _bars([
        {"issuer": row.issuer, "num_funds": int(row.num_funds),
         "total_value": usd(float(row.total_value)),
         "avg_pct": pct(float(row.avg_pct))}
        for row in mh.itertuples(index=False)
    ], "num_funds")

    # "Highest single-position conviction" should showcase real managers, not
    # single-stake filers (an operating company holding one name is trivially
    # 100%). Pull a wide list, keep investment managers holding >= 2 companies,
    # then take the top 12 by concentration.
    tc = insights.top_concentration(conn, quarter, limit=150)
    top_conc = [
        {"manager_name": row.manager_name, "top_holding": row.top_holding,
         "top_pct": pct(float(row.top_pct)), "top_pct_val": round(float(row.top_pct), 1),
         "aum": usd(float(row.total_aum_usd)),
         "cik": str(_cik_for(conn, row.manager_name, quarter))}
        for row in tc.itertuples(index=False)
        if int(row.num_issuers) >= 2
        and classify.classify_manager(row.manager_name) == classify.MANAGER
    ][:12]

    nm = insights.new_managers(conn, quarter)
    new_mgrs = [
        {"manager_name": row.manager_name, "aum": usd(float(row.total_aum_usd)),
         "num_issuers": int(row.num_issuers)}
        for row in nm.itertuples(index=False)
        if classify.classify_manager(row.manager_name) == classify.MANAGER
    ][:12]

    total_aum = sum(r["aum_usd"] for r in rows)
    mgr_aum = sum(r["aum_usd"] for r in managers)
    med_iss = _median([r["num_issuers"] for r in managers]) if managers else 0
    return {
        "quarter": quarter,
        "prev_quarter": insights.previous_quarter(conn, quarter),
        "num_filers": len(rows),
        "num_managers": len(managers),
        "total_aum": usd(total_aum),
        "manager_aum": usd(mgr_aum),
        "median_issuers": med_iss,
        "total_positions": sum(r["num_positions"] for r in rows),
        "type_mix": mix,
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
    """
    cur = insights.holders_of(conn, issuer_cusip, quarter)
    if cur.empty:
        return None
    prev_q = insights.previous_quarter(conn, quarter)
    prev = insights.holders_of(conn, issuer_cusip, prev_q) if prev_q else None
    prev_val = {str(r.cik): float(r.value_usd or 0) for r in prev.itertuples(index=False)} if prev is not None else {}
    prev_sh = {str(r.cik): float(r.shares or 0) for r in prev.itertuples(index=False)} if prev is not None else {}
    prev_name = {str(r.cik): r.manager_name for r in prev.itertuples(index=False)} if prev is not None else {}

    issuer = cur.iloc[0].issuer
    emoji = {"new": "🟢", "added": "🔼", "trimmed": "🔽", "exited": "🔴"}

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

    # 5-quarter trend: combined value + holder count (shown universe only).
    tr = list(insights.issuer_trend(conn, issuer_cusip).itertuples(index=False))[-max_quarters:]
    value_pts = [{"label": t.quarter, "value": float(t.total_value or 0)} for t in tr]
    holder_pts = [{"label": t.quarter, "value": int(t.holders or 0)} for t in tr]

    universe = _shown_manager_count(conn, quarter)
    return {
        "cusip": issuer_cusip,
        "issuer": issuer,
        "quarter": quarter,
        "prev_quarter": prev_q,
        "num_holders": len(holders),
        "universe": universe,
        "total_value": usd(total_value),
        "holders": holders,
        "new_buyers": new_buyers,
        "exits": exits,
        "counts": [{"kind": k, "emoji": emoji[k], "n": counts[k]}
                   for k in ("new", "added", "trimmed", "exited")],
        "value_svg": aum_timeline_svg(value_pts),
        "holders_svg": aum_timeline_svg(holder_pts, fmt=lambda v: f"{int(v)}"),
        "trend": [{"quarter": t.quarter, "value": usd(float(t.total_value or 0)),
                   "holders": int(t.holders or 0)} for t in tr],
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


def _holdings_for(conn, filing_id: int) -> list[dict]:
    holds = queries.fund_holdings(conn, int(filing_id))
    max_pct = float(holds["pct_of_portfolio"].max() or 1) if len(holds) else 1
    return [{
        "issuer": h.name_of_issuer, "title": h.title_of_class,
        "value": usd(float(h.value_usd)), "value_usd": float(h.value_usd),
        "shares": f"{float(h.shares):,.0f}", "shares_type": h.shares_type,
        "put_call": h.put_call or "",
        "pct": pct(float(h.pct_of_portfolio)),
        "pct_val": round(float(h.pct_of_portfolio), 2),
        "width": round(float(h.pct_of_portfolio) / max_pct * 100, 2),
    } for h in holds.itertuples(index=False)]


def _moves_for(conn, cik: str, quarter: str) -> dict | None:
    """QoQ moves for one fund/quarter, or None if there's no prior filing."""
    qoq = insights.qoq_changes(conn, str(cik), quarter)
    if qoq is None:
        return None
    nonzero = qoq[qoq["change_type"] != "unchanged"]
    counts = qoq["change_type"].value_counts().to_dict()
    emoji = {"new": "🟢", "added": "🔼", "trimmed": "🔽", "exited": "🔴"}
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


def fund_detail(conn, cik: str, quarter: str, max_quarters: int = 5) -> dict | None:
    """Everything one fund page needs.

    Returns header info, the full AUM timeline (sparkline), and a list of the
    most recent `max_quarters` quarter snapshots (newest first). Each snapshot
    carries its own holdings and quarter-over-quarter moves, so the page can let
    the visitor switch between quarters client-side. All quarters we've ever
    loaded for the fund stay in the database; we simply surface the latest few.
    """
    tl = queries.fund_timeline(conn, str(cik))
    if tl.empty:
        return None

    row = conn.execute("SELECT manager_name, filer_type FROM funds WHERE cik = ?",
                       (str(cik),)).fetchone()
    manager_name = row[0] if row else str(cik)
    stored = (row[1] if row else "") or ""
    cat = stored if stored in classify.CATEGORY_EMOJI else classify.classify_manager(manager_name)

    # Full history for the sparkline (oldest -> newest).
    timeline = [{"label": t.quarter_label, "value": float(t.total_aum_usd)}
                for t in tl.itertuples(index=False)]

    # Newest -> oldest, keep the most recent `max_quarters`.
    rows = list(tl.itertuples(index=False))[::-1][:max_quarters]
    quarters = []
    for i, t in enumerate(rows):
        # The next item in `rows` is this quarter's predecessor (older).
        prev_label = rows[i + 1].quarter_label if i + 1 < len(rows) else None
        meets = bool(getattr(t, "passes_screen", 1))
        top_n_pct = float(getattr(t, "top_n_pct", 0.0) or 0.0)
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
            "form_type": t.form_type,
            "date_filed": t.date_filed,
            "accession": t.accession,
            "sec_url": sec_filing_url(str(cik), str(t.accession)),
            "holdings": _holdings_for(conn, t.filing_id),
            "moves": _moves_for(conn, str(cik), t.quarter_label),
            "prev_quarter": prev_label,
        })

    return {
        "cik": str(cik),
        "manager_name": manager_name,
        "category": cat,
        "type_label": f"{classify.CATEGORY_EMOJI[cat]} {cat}",
        "emoji": classify.CATEGORY_EMOJI[cat],
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
