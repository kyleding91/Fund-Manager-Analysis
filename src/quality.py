"""Phase 6 — Data-quality checks over the loaded database.

These catch the kinds of problems that creep into scraped filings: bad units,
missing periods, screen-invariant violations, or holdings that don't add up.
"""
from __future__ import annotations

from . import config


def check_db(conn) -> list[str]:
    """Return a list of human-readable warnings (empty list = all good)."""
    issues: list[str] = []
    rows = conn.execute(
        """SELECT f.id, fn.manager_name, f.quarter_label, f.period_of_report,
                  f.total_aum_usd, f.num_issuers, f.num_positions, f.top_n_pct
           FROM filings f JOIN funds fn ON fn.cik = f.cik
           WHERE f.is_current = 1 AND f.passes_screen = 1"""
    ).fetchall()

    for r in rows:
        tag = f"{r['manager_name']} [{r['quarter_label']}]"

        if not r["period_of_report"]:
            issues.append(f"{tag}: missing period_of_report")

        # Screen invariants: above the AUM floor AND concentrated by either
        # measure (few enough issuers, or a heavy top-N weight).
        if r["total_aum_usd"] is None or r["total_aum_usd"] <= config.MIN_AUM_USD:
            issues.append(f"{tag}: AUM ${r['total_aum_usd']:,.0f} not above the screen floor")
        few_issuers = r["num_issuers"] is not None and 0 < r["num_issuers"] <= config.MAX_HOLDINGS
        heavy_top = (r["top_n_pct"] or 0) >= config.TOP_N_MIN_PCT
        if not (few_issuers or heavy_top):
            issues.append(
                f"{tag}: not concentrated — {r['num_issuers']} issuers and top-"
                f"{config.TOP_N} weight {r['top_n_pct'] or 0:.1f}% "
                f"(need <= {config.MAX_HOLDINGS} issuers or >= {config.TOP_N_MIN_PCT:.0f}%)")

        # Holdings should sum to the reported AUM and to ~100%.
        agg = conn.execute(
            """SELECT COALESCE(SUM(value_usd),0) AS sv,
                      COALESCE(SUM(pct_of_portfolio),0) AS sp,
                      COUNT(*) AS n,
                      SUM(CASE WHEN value_usd <= 0 THEN 1 ELSE 0 END) AS bad_val
               FROM holdings WHERE filing_id = ?""",
            (r["id"],),
        ).fetchone()

        if agg["n"] == 0:
            issues.append(f"{tag}: no holdings rows")
            continue
        if r["total_aum_usd"] and abs(agg["sv"] - r["total_aum_usd"]) > 0.01 * r["total_aum_usd"]:
            issues.append(
                f"{tag}: holdings sum ${agg['sv']:,.0f} != stored AUM ${r['total_aum_usd']:,.0f}")
        if abs(agg["sp"] - 100.0) > 1.0:
            issues.append(f"{tag}: portfolio % sums to {agg['sp']:.1f}% (expected ~100%)")
        if agg["bad_val"]:
            issues.append(f"{tag}: {agg['bad_val']} holding(s) with value <= 0")

        # A possible units mistake: a fund reporting in thousands looks ~1000x small,
        # so a "passing" $2B+ fund with a top holding under $1M is suspicious.
        top = conn.execute(
            "SELECT MAX(value_usd) FROM holdings WHERE filing_id = ?", (r["id"],)
        ).fetchone()[0]
        if top and top < 1_000_000:
            issues.append(f"{tag}: largest holding only ${top:,.0f} — possible units problem")

    return issues
