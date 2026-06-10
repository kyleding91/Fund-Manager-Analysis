"""Classify a 13F filer by the kind of institution it is.

13F filings come from many institution types, not just hedge funds: sovereign
wealth funds, pensions, university endowments, foundations, insurers, operating
companies (treasury stakes), and market-makers. They all pass a mechanical
"AUM + holdings count" screen, so we classify them to let users focus on real
stock-pickers ("Investment Manager") vs. everything else.

Classification is a name-based heuristic — good enough to filter the list, and
transparent. A small allow-list protects famous managers that look like operating
companies (e.g. Berkshire Hathaway).
"""
from __future__ import annotations

import re
from functools import lru_cache

import yaml

from . import config

# Categories (also the display order / legend).
MANAGER = "Investment Manager"
FOUNDATION = "Foundation / Endowment"
PENSION = "Pension / Sovereign"
BANK = "Bank / Insurance"
MARKET_MAKER = "Market Maker / Broker"
OPERATING = "Operating Company"
HOLDING_COMPANY = "Holding Company"
MUTUAL_FUND = "Mutual Fund / Advisor Complex"

CATEGORY_EMOJI = {
    MANAGER: "💼",
    FOUNDATION: "🎓",
    PENSION: "🏛️",
    BANK: "🏦",
    MARKET_MAKER: "🔁",
    OPERATING: "🏢",
    HOLDING_COMPANY: "🏗️",
    MUTUAL_FUND: "📚",
}

# All known category constants, for validating YAML overrides.
ALL_CATEGORIES = frozenset(CATEGORY_EMOJI)

# Firm types that are excluded from the curated universe by default. Extensible
# via config/firm_types.yaml (excluded_types:). Market-makers are excluded per
# the user's decision; PE/buyout shops stay (handled via per-CIK tagging instead).
_DEFAULT_EXCLUDED_TYPES = (MARKET_MAKER,)

# Well-known stock-pickers that would otherwise be misread as operating companies.
_ALLOW_MANAGER = ("BERKSHIRE HATHAWAY", "ICAHN", "GREENLIGHT", "MARKEL",
                  "CARLYLE", "PAULSON", "LINDSELL TRAIN", "FUNDSMITH",
                  "MATSON MONEY", "BAUPOST")

_FOUNDATION = ("FOUNDATION", "ENDOWMENT", "UNIVERSITY", "COLLEGE", "REGENTS",
               "CHARITABLE", "PHILANTHROP", "INSTITUTE", "HOSPITAL", "HEALTH SYSTEM",
               "HEALTHCARE CORP", "MUSEUM")
_PENSION = ("PENSION", "RETIREMENT", "RETIREE", "TEACHERS", "EMPLOYEES",
            "PSPRS", "SOVEREIGN", "PUBLIC INVESTMENT FUND", "STATE OF ",
            "STATE TREASURER", "TREASURER OF", "PROVIDENT", "SUPERANNUATION",
            "NATIONAL PENSION", "PERMANENT SCHOOL FUND", "PERMANENT FUND")
_MARKET_MAKER = ("SECURITIES LLC", "SECURITIES, LLC", "SECURITIES INC",
                 "SECURITIES, INC", "CITADEL SECURITIES", "SUSQUEHANNA",
                 "JANE STREET", "AKUNA", "OPTIVER", "FLOW TRADERS", "DRW ",
                 "VIRTU", "IMC ", "TWO SIGMA SECURITIES", "JUMP TRADING",
                 "WOLVERINE", "BELVEDERE", "GTS ", "HRT ", "OLD MISSION")
_BANK = ("BANCORP", "BANCSHARES", " BANK", "BANK ", "INSURANCE", "ASSURANCE",
         "FINANCIAL GROUP", "LIFE INS", "MUTUAL INS", "REINSURANCE")
# Strong signals that a name is a real investment manager.
_MANAGER_KW = ("CAPITAL", "MANAGEMENT", "MANAGEMENT", "ADVISOR", "ADVISER",
               "PARTNERS", "ASSET MGMT", "ASSET MANAGEMENT", "INVESTMENT MANAGE",
               "INVESTMENTS", "INVESTMENT MGMT", "FUND MANAGEMENT", "ASSOCIATES",
               "WEALTH", "GLOBAL INVESTORS", "INVESTMENT COUNSEL", "FAMILY OFFICE",
               "HOLDINGS LLC", "MANAGERS", "INVESTORS", "INVESTMENT")
# Suffixes that suggest a public operating company when no manager keyword present.
_CORP_SUFFIX = re.compile(r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|PLC|AG|SA|"
                          r"NV|SE|LTD|LIMITED|GROUP|GMBH)\b\.?\s*$")


def _has(name: str, needles) -> bool:
    return any(n in name for n in needles)


def classify_manager(name: str) -> str:
    """Return one of the category constants for a filer name."""
    n = (name or "").upper().strip()
    if not n:
        return MANAGER
    if _has(n, _ALLOW_MANAGER):
        return MANAGER
    if _has(n, _FOUNDATION):
        return FOUNDATION
    if _has(n, _PENSION):
        return PENSION
    if _has(n, _MARKET_MAKER):
        return MARKET_MAKER
    if _has(n, _MANAGER_KW):
        return MANAGER
    if _has(n, _BANK):
        return BANK
    # No manager signal and looks like a public company → operating company.
    if _CORP_SUFFIX.search(n):
        return OPERATING
    return MANAGER


def label(name: str) -> str:
    """An emoji-prefixed short label for display, e.g. '💼 Investment Manager'."""
    cat = classify_manager(name)
    return f"{CATEGORY_EMOJI[cat]} {cat}"


def is_investment_manager(name: str) -> bool:
    return classify_manager(name) == MANAGER


# --- Firm-type resolution (heuristic + per-CIK overrides) -----------------
# `firm_type(cik, name)` is the stored, queryable tag. It layers human-supplied
# per-CIK corrections (config/firm_types.yaml) on top of the name heuristic, so
# the heuristic's misses (mutual-fund complexes, holding companies, PE vehicles)
# can be fixed without code changes. The mechanical screen is unaffected — this
# is a separate fact about the filer used by the curation overlay.

FIRM_TYPES_PATH = config.CONFIG_DIR / "firm_types.yaml"

# Strong, conservative signals for a broad mutual-fund / advisor complex. Kept
# narrow on purpose: most long-tail complexes are caught by the numeric holdings
# ceiling, and genuine focused managers often contain "FUND" too (Fundsmith), so
# we only flag unmistakable complex names here and rely on overrides for the rest.
_MUTUAL_FUND = ("MUTUAL FUND", "INDEX FUND", "INDEX FUNDS", "FUNDS TRUST",
                "FUNDS, INC", "FUNDS INC", "INVESTMENT TRUST", "MUTUAL FUNDS",
                "VARIABLE INSURANCE", "ETF TRUST")


def _norm(cik) -> str:
    """Normalise a CIK to digits with no leading zeros (matches curation._norm)."""
    s = str(cik).strip()
    if s.isdigit():
        s = s.lstrip("0") or "0"
    return s


@lru_cache(maxsize=1)
def _load_overrides() -> dict:
    """Read config/firm_types.yaml → {overrides: {cik: type}, excluded: (types,)}.

    Degrades gracefully (empty overrides, default excluded set) if the file is
    missing or malformed, so the pipeline never breaks on a typo in policy.
    """
    overrides: dict[str, str] = {}
    excluded = set(_DEFAULT_EXCLUDED_TYPES)
    try:
        raw = yaml.safe_load(FIRM_TYPES_PATH.read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, yaml.YAMLError, OSError):
        raw = {}
    for entry in raw.get("overrides") or []:
        if not isinstance(entry, dict):
            continue
        cik, ftype = entry.get("cik"), entry.get("type")
        if cik is None or ftype not in ALL_CATEGORIES:
            continue
        overrides[_norm(cik)] = ftype
    extra = raw.get("excluded_types")
    if extra:
        valid = {t for t in extra if t in ALL_CATEGORIES}
        if valid:
            excluded = valid
    return {"overrides": overrides, "excluded": tuple(sorted(excluded))}


def reload() -> None:
    """Drop the cached firm-type overrides (call after editing the YAML)."""
    _load_overrides.cache_clear()


def firm_type_heuristic(name: str) -> str:
    """Name-only firm type, extending classify_manager with the complex category."""
    n = (name or "").upper().strip()
    if n and not _has(n, _ALLOW_MANAGER) and _has(n, _MUTUAL_FUND):
        return MUTUAL_FUND
    return classify_manager(name)


def firm_type(cik, name: str) -> str:
    """The stored firm-type tag: per-CIK override if present, else the heuristic."""
    ov = _load_overrides()["overrides"].get(_norm(cik))
    if ov:
        return ov
    return firm_type_heuristic(name)


def excluded_firm_types() -> tuple[str, ...]:
    """Firm types hidden from the curated universe (default + YAML additions)."""
    return _load_overrides()["excluded"]


# ETF / index-fund sponsors. A 13F whose value is mostly these is a passive
# basket (a sovereign/advisor parking cash in index funds), not a stock-picker —
# so it should fail the screen regardless of how "concentrated" the basket looks.
# Matched as case-insensitive substrings of the issuer name. The generic tokens
# (" ETF", "INDEX FUND") catch sponsors not named below; the specific sponsor
# names catch funds whose name doesn't contain those tokens (e.g. "ISHARES CORE
# S&P 500").
_ETF_SPONSORS = (
    "ISHARES", "SPDR", "VANGUARD", "INVESCO QQQ", "POWERSHARES", "PROSHARES",
    "DIREXION", "WISDOMTREE", "GLOBAL X", "FIRST TRUST", "VANECK", "XTRACKERS",
    "SCHWAB STRATEGIC", "DIMENSIONAL", "JPMORGAN BETABUILDERS", "SELECT SECTOR",
    "GRANITESHARES", "JANUS HENDERSON DET", " ETF", "ETF ", "INDEX FD",
    "INDEX FUND", "EXCHANGE TRADED", "EXCHANGE-TRADED",
)


def is_etf_name(name: str) -> bool:
    """True if an issuer name is an ETF / index fund rather than an operating company."""
    n = (name or "").upper()
    return any(kw in n for kw in _ETF_SPONSORS)


# Backwards-friendly constant alias (resolved at call time via the function).
EXCLUDED_FIRM_TYPES = frozenset(_DEFAULT_EXCLUDED_TYPES)
