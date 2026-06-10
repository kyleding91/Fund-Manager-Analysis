"""Central configuration for the 13F Fund Tracker.

Everything tunable lives here so there's one obvious place to change settings.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

# --- Project paths -------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"            # cached raw filings from EDGAR
DB_PATH = DATA_DIR / "13f.db"         # the SQLite database file
CONFIG_DIR = PROJECT_ROOT / "config"  # human-editable policy/curation YAML

# --- SEC EDGAR access ----------------------------------------------------
# The SEC requires a descriptive User-Agent that includes a contact email.
# See https://www.sec.gov/os/accessing-edgar-data
# Overridable via the SEC_CONTACT_EMAIL env var (used by the CI workflow so the
# address can live in a repo secret instead of in source).
CONTACT_EMAIL = os.environ.get("SEC_CONTACT_EMAIL", "kyleding91@gmail.com")
USER_AGENT = f"Fund Manager Analysis (personal research) {CONTACT_EMAIL}"

# SEC fair-access policy: stay at/under 10 requests/second. We aim lower.
REQUESTS_PER_SECOND = 6
REQUEST_TIMEOUT = 30          # seconds
MAX_RETRIES = 4

EDGAR_BASE = "https://www.sec.gov/Archives"
FULL_INDEX_URL = EDGAR_BASE + "/edgar/full-index/{year}/QTR{quarter}/form.idx"

# Form types that contain holdings we care about.
FORM_TYPES = {"13F-HR", "13F-HR/A"}

# --- Screening criteria --------------------------------------------------
# Keep value-oriented, concentrated managers. A filing passes if its total 13F
# AUM is above the floor AND it is "concentrated" by EITHER measure:
#   * holds at most MAX_HOLDINGS distinct issuers, OR
#   * its TOP_N largest positions make up at least TOP_N_MIN_PCT of AUM *and* it
#     holds at most MAX_HOLDINGS_WEIGHTED issuers (so a 1,400-name mutual-fund
#     complex that happens to be top-heavy is NOT mistaken for a focused book).
# The second branch catches managers who hold a moderate tail of small positions
# but still run a genuinely concentrated book in their top names.
# A small MIN_HOLDINGS floor (default 1 = no-op) screens out 1-2 stock vehicles
# if you choose to raise it.
#
# These thresholds are POLICY, so they live in a human-editable YAML file
# (config/screen.yaml) that anyone can change from GitHub's web editor without
# touching Python. The values below are the built-in defaults / fallbacks used
# when the file (or a given key) is missing. After changing screen.yaml, re-run
# `python3 rebuild_universe.py` to re-screen everything under the new rules.
SCREEN_PATH = CONFIG_DIR / "screen.yaml"

_SCREEN_DEFAULTS = {
    "min_aum_usd": 2_000_000_000,
    "max_holdings": 30,            # "few names" branch: at most this many issuers
    "max_holdings_weighted": 50,   # weight branch also caps issuers at this many
    "min_holdings": 1,             # floor on issuers (1 = no-op; raise to drop 1-2 stock vehicles)
    "top_n": 10,                   # how many largest positions define "top holdings"
    "top_n_min_pct": 80.0,         # top-N must be >= this % of AUM to count as concentrated
    "max_etf_pct": 50.0,           # if >= this % of AUM is in ETFs/index funds, it's a passive basket, not a stock-picker
}


def _load_screen() -> dict:
    """Read screen thresholds from config/screen.yaml, falling back to defaults.

    Unknown keys are ignored; missing keys use the built-in default. A malformed
    or absent file degrades gracefully to the defaults so the pipeline never
    breaks on a typo in the policy file.
    """
    values = dict(_SCREEN_DEFAULTS)
    try:
        raw = yaml.safe_load(SCREEN_PATH.read_text(encoding="utf-8")) or {}
        for key in _SCREEN_DEFAULTS:
            if key in raw and raw[key] is not None:
                values[key] = raw[key]
    except FileNotFoundError:
        pass
    except (yaml.YAMLError, OSError):
        # Bad YAML or unreadable file: keep defaults rather than crash.
        pass
    return values


_screen = _load_screen()
MIN_AUM_USD = int(_screen["min_aum_usd"])
MAX_HOLDINGS = int(_screen["max_holdings"])
MAX_HOLDINGS_WEIGHTED = int(_screen["max_holdings_weighted"])
MIN_HOLDINGS = int(_screen["min_holdings"])
TOP_N = int(_screen["top_n"])
TOP_N_MIN_PCT = float(_screen["top_n_min_pct"])
MAX_ETF_PCT = float(_screen["max_etf_pct"])

# --- Units handling ------------------------------------------------------
# Before the SEC's amendment effective 2023-01-03, 13F "value" was reported in
# THOUSANDS of dollars. On/after that date it is reported in WHOLE dollars.
# We normalize everything to whole dollars using the filing date.
DOLLARS_CUTOVER_DATE = "2023-01-03"


def ensure_dirs() -> None:
    """Create the data directories if they don't exist yet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
