"""Phase 2b — Normalize units, aggregate holdings, and apply the screen.

Screen (from config): keep funds with total 13F AUM > $2B AND that are
concentrated by EITHER measure — at most 30 distinct issuers, OR the top 10
positions making up >= 80% of AUM (value-oriented, concentrated managers).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import config
from .parser import ParsedFiling


@dataclass
class AggHolding:
    """One position, aggregated across duplicate filing rows, in whole dollars."""
    name_of_issuer: str
    title_of_class: str
    cusip: str
    value_usd: float
    shares: float
    shares_type: str
    put_call: str
    pct_of_portfolio: float = 0.0


@dataclass
class ScreenedFund:
    cik: str
    manager_name: str
    quarter_label: str
    period_of_report: str
    form_type: str
    date_filed: str
    accession: str
    total_aum_usd: float
    num_positions: int        # distinct securities (full CUSIP)
    num_issuers: int          # distinct companies (CUSIP[:6]) -> used by the screen
    passes_screen: bool
    top_n_pct: float = 0.0    # % of AUM in the TOP_N largest positions
    meets_count: bool = False  # passes the "<= MAX_HOLDINGS issuers" branch
    meets_weight: bool = False  # passes the "top-N >= TOP_N_MIN_PCT" branch
    holdings: list[AggHolding] = field(default_factory=list)


def _in_dollars(date_filed: str) -> bool:
    """True if this filing reports values in whole dollars (vs. thousands)."""
    try:
        d = datetime.strptime(date_filed, "%Y-%m-%d")
        cutover = datetime.strptime(config.DOLLARS_CUTOVER_DATE, "%Y-%m-%d")
        return d >= cutover
    except ValueError:
        return True  # assume modern/whole-dollars if date is missing


def screen_filing(filing: ParsedFiling) -> ScreenedFund:
    """Aggregate + normalize a parsed filing and decide if it passes the screen."""
    multiplier = 1.0 if _in_dollars(filing.date_filed) else 1000.0

    # Aggregate rows that share the same security (same CUSIP). Funds list a
    # security multiple times when several managers share discretion over it.
    by_cusip: dict[str, AggHolding] = {}
    for h in filing.holdings:
        # Skip placeholder rows. Confidential-treatment filings (holdings omitted)
        # contain a single dummy row with value 0 / cusip 000000000 — we must not
        # treat those as real positions.
        if h.value <= 0 and h.shares <= 0:
            continue
        key = (h.cusip or h.name_of_issuer).upper()
        val = h.value * multiplier
        if key in by_cusip:
            agg = by_cusip[key]
            agg.value_usd += val
            agg.shares += h.shares
        else:
            by_cusip[key] = AggHolding(
                name_of_issuer=h.name_of_issuer,
                title_of_class=h.title_of_class,
                cusip=h.cusip,
                value_usd=val,
                shares=h.shares,
                shares_type=h.shares_type,
                put_call=h.put_call,
            )

    holdings = list(by_cusip.values())
    # AUM is the sum of REAL, disclosed holdings only. We deliberately do NOT fall
    # back to the cover-page total: a fund that discloses no holdings (e.g. full
    # confidential treatment) cannot be screened for concentration and must not pass.
    total_aum = sum(h.value_usd for h in holdings)

    for h in holdings:
        h.pct_of_portfolio = (h.value_usd / total_aum * 100.0) if total_aum else 0.0
    holdings.sort(key=lambda h: h.value_usd, reverse=True)

    num_positions = len(holdings)
    num_issuers = len({(h.cusip or h.name_of_issuer)[:6].upper() for h in holdings})

    # Concentration of the top-N positions (holdings are already sorted desc).
    top_n_value = sum(h.value_usd for h in holdings[:config.TOP_N])
    top_n_pct = (top_n_value / total_aum * 100.0) if total_aum else 0.0

    big_enough = total_aum > config.MIN_AUM_USD and num_issuers > 0
    meets_count = big_enough and num_issuers <= config.MAX_HOLDINGS
    meets_weight = big_enough and top_n_pct >= config.TOP_N_MIN_PCT
    passes = (
        big_enough
        and (meets_count or meets_weight)
        and not filing.is_confidential
    )

    return ScreenedFund(
        cik=filing.cik,
        manager_name=filing.manager_name,
        quarter_label=filing.quarter_label if filing.period_of_report else "",
        period_of_report=filing.period_of_report,
        form_type=filing.form_type,
        date_filed=filing.date_filed,
        accession=filing.accession,
        total_aum_usd=total_aum,
        num_positions=num_positions,
        num_issuers=num_issuers,
        passes_screen=passes,
        top_n_pct=top_n_pct,
        meets_count=meets_count,
        meets_weight=meets_weight,
        holdings=holdings,
    )
