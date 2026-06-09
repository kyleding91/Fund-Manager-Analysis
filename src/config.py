"""Central configuration for the 13F Fund Tracker.

Everything tunable lives here so there's one obvious place to change settings.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Project paths -------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"            # cached raw filings from EDGAR
DB_PATH = DATA_DIR / "13f.db"         # the SQLite database file

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
#   * its TOP_N largest positions make up at least TOP_N_MIN_PCT of AUM.
# The second branch catches managers who hold a long tail of tiny positions but
# still run a genuinely concentrated book in their top names.
MIN_AUM_USD = 2_000_000_000
MAX_HOLDINGS = 30          # at most this many distinct issuers (inclusive)
TOP_N = 10                 # how many largest positions define "top holdings"
TOP_N_MIN_PCT = 80.0       # top-N must be >= this % of AUM to count as concentrated

# --- Units handling ------------------------------------------------------
# Before the SEC's amendment effective 2023-01-03, 13F "value" was reported in
# THOUSANDS of dollars. On/after that date it is reported in WHOLE dollars.
# We normalize everything to whole dollars using the filing date.
DOLLARS_CUTOVER_DATE = "2023-01-03"


def ensure_dirs() -> None:
    """Create the data directories if they don't exist yet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
