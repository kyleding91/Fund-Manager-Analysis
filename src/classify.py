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

# Categories (also the display order / legend).
MANAGER = "Investment Manager"
FOUNDATION = "Foundation / Endowment"
PENSION = "Pension / Sovereign"
BANK = "Bank / Insurance"
MARKET_MAKER = "Market Maker / Broker"
OPERATING = "Operating Company"

CATEGORY_EMOJI = {
    MANAGER: "💼",
    FOUNDATION: "🎓",
    PENSION: "🏛️",
    BANK: "🏦",
    MARKET_MAKER: "🔁",
    OPERATING: "🏢",
}

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
