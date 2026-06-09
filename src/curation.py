"""Manual curation layer — human overrides on top of the mechanical screen.

The screen (see `screener.py` / `config.py`) decides who *mechanically* qualifies
and records that in the `quarter_screen` ledger and each filing's `passes_screen`
flag. Those stay untouched — they're the audit trail of the algorithm.

This module sits one level above that: it reads `config/curation.yaml` and lets a
human **exclude** managers that pass but shouldn't be shown (index funds,
market-makers, duplicates…) or **include** managers that don't pass but should be
tracked anyway. The result is applied at the *query layer* (in queries.py /
insights.py / site_data.py), so an exclusion takes effect the moment the site is
rebuilt — no SEC re-download required.

CIKs are compared as strings with leading zeros stripped, so `1067983`,
`0001067983`, and the integer `1067983` all refer to the same manager.
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from . import config

CURATION_PATH = config.CONFIG_DIR / "curation.yaml"


def _norm(cik) -> str:
    """Normalise a CIK to a canonical string (digits, no leading zeros)."""
    s = str(cik).strip()
    if s.isdigit():
        s = s.lstrip("0") or "0"
    return s


def _norm_set(entries) -> set[str]:
    out: set[str] = set()
    if not entries:
        return out
    for entry in entries:
        if isinstance(entry, dict):
            cik = entry.get("cik")
        else:
            cik = entry
        if cik is None:
            continue
        out.add(_norm(cik))
    return out


@lru_cache(maxsize=1)
def _load() -> dict:
    try:
        raw = yaml.safe_load(CURATION_PATH.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raw = {}
    except (yaml.YAMLError, OSError):
        raw = {}
    return {
        "exclude": _norm_set(raw.get("exclude")),
        "include": _norm_set(raw.get("include")),
    }


def reload() -> None:
    """Drop the cached curation lists (call after editing the YAML in-process)."""
    _load.cache_clear()


def excluded_ciks() -> set[str]:
    """Normalised CIKs a human has chosen to hide."""
    return set(_load()["exclude"])


def included_ciks() -> set[str]:
    """Normalised CIKs a human has chosen to force-track."""
    return set(_load()["include"])


def is_excluded(cik) -> bool:
    return _norm(cik) in excluded_ciks()


def filter_ciks(ciks) -> set[str]:
    """Apply curation to a set of candidate CIKs: drop excludes, add includes.

    Returns normalised CIK strings.
    """
    keep = {_norm(c) for c in ciks}
    keep -= excluded_ciks()
    keep |= included_ciks()
    return keep


def _sql_cik_list(ciks: set[str], alias: str) -> str:
    """Build a `CAST(<col> AS TEXT) IN (...)` test with leading zeros stripped.

    We strip leading zeros from the stored CIK in SQL too so the comparison
    matches our normalised, zero-stripped curation values.
    """
    col = f"LTRIM({alias}cik, '0')"
    quoted = ", ".join("'" + c.replace("'", "''") + "'" for c in sorted(ciks))
    return f"{col} IN ({quoted})"


def screen_predicate(alias: str = "f.") -> str:
    """Return a SQL boolean expression for 'shown in the curated universe'.

    Combines the mechanical screen flag with the human overrides:

        (passes_screen = 1 OR cik in include) AND cik not in exclude

    `alias` is the table alias prefix for the columns, e.g. "f." (default) or
    "" when the query has no alias. The expression is safe to drop into a WHERE
    clause and always returns a valid boolean even when both lists are empty.
    """
    excl = excluded_ciks()
    incl = included_ciks()

    passes = f"{alias}passes_screen = 1"
    if incl:
        passes = f"({passes} OR {_sql_cik_list(incl, alias)})"

    if excl:
        return f"{passes} AND NOT ({_sql_cik_list(excl, alias)})"
    return passes
