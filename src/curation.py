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

from . import classify, config, roster

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


def _sql_excluded_firm_types(alias: str) -> str:
    """`COALESCE(<alias>filer_type,'') IN ('Market Maker / Broker', ...)`.

    COALESCE so a NULL filer_type (e.g. an old row not yet re-screened) is treated
    as "not an excluded type" — i.e. it stays shown rather than silently dropping.
    """
    types = classify.excluded_firm_types()
    quoted = ", ".join("'" + t.replace("'", "''") + "'" for t in types)
    return f"COALESCE({alias}filer_type, '') IN ({quoted})"


def screen_predicate(alias: str = "f.") -> str:
    """Return a SQL boolean expression for 'shown in the curated universe'.

    One source of truth for "shown". With a membership roster present
    (config/roster.yaml — the STICKY universe), the rule is:

        cik in include
        OR ( cik in <active roster members>
             AND cik not in exclude
             AND filer_type not in <excluded firm types> )

    i.e. membership (decided by the screen at admission time, kept until a human
    removes it) replaces the per-quarter `passes_screen` check, so a member that
    lapses below the criteria stays shown — by design. Force-include still WINS
    over every exclusion path (R3), and the firm-type / curation excludes still
    apply on top of membership.

    Without a roster (fresh checkout, tests), this falls back to the original
    per-quarter mechanical rule:

        cik in include
        OR ( passes_screen = 1 AND cik not in exclude AND filer_type not in ... )

    `alias` is the table alias prefix for the columns, e.g. "f." (default) or ""
    when the query has no alias. Safe to drop into a WHERE clause; always a valid
    boolean even when the curation lists are empty.
    """
    excl = excluded_ciks()
    incl = included_ciks()
    excluded_types = classify.excluded_firm_types()

    if roster.has_roster():
        base = _sql_cik_list(roster.active_ciks(), alias)
    else:
        base = f"{alias}passes_screen = 1"
    clauses = [base]
    if excl:
        clauses.append(f"NOT ({_sql_cik_list(excl, alias)})")
    if excluded_types:
        clauses.append(f"NOT ({_sql_excluded_firm_types(alias)})")
    mechanical = " AND ".join(clauses)
    if len(clauses) > 1:
        mechanical = f"({mechanical})"

    if incl:
        return f"({_sql_cik_list(incl, alias)} OR {mechanical})"
    return mechanical


def explain(conn, cik, quarter: str) -> str:
    """One-line answer to 'why is (or isn't) this filer shown in this quarter?'.

    Reconciles the three layers using the per-quarter ledger (quarter_screen):
    the mechanical reject_reason, the stored filer_type, and the curation lists.
    Returns a human-readable sentence. Used by the audit harness and ad-hoc Qs.
    """
    norm = _norm(cik)
    incl = norm in included_ciks()
    excl = norm in excluded_ciks()

    row = conn.execute(
        """SELECT passes_screen, reject_reason, filer_type, manager_name
           FROM quarter_screen
           WHERE LTRIM(cik, '0') = ? AND quarter_label = ?""",
        (norm, quarter),
    ).fetchone()
    if row is None:
        if incl:
            return "force-included (config/curation.yaml), but no screen record this quarter"
        return "no screen record for this quarter"

    passes = bool(row["passes_screen"])
    reason = row["reject_reason"] or ""
    ftype = row["filer_type"] or ""
    ft_excluded = ftype in set(classify.excluded_firm_types())

    if roster.has_roster():
        member = norm in roster.active_ciks()
        shown = incl or (member and not excl and not ft_excluded)
        if shown:
            if incl and not (member and not excl and not ft_excluded):
                return "shown — force-included via config/curation.yaml"
            if not passes:
                return (f"shown — roster member, lapsed this quarter "
                        f"({reason or 'not_concentrated'}); kept pending review")
            return "shown — roster member, passes the screen"
        if member and ft_excluded:
            return f"hidden — firm type '{ftype}' is excluded"
        if member and excl:
            return "hidden — excluded in config/curation.yaml"
        if not member and passes:
            return ("hidden — passes the screen but not on the roster "
                    "(removed, or not yet admitted)")
        return f"hidden — did not pass the screen ({reason or 'not_concentrated'})"

    shown = incl or (passes and not excl and not ft_excluded)
    if shown:
        if incl and not (passes and not excl and not ft_excluded):
            return "shown — force-included via config/curation.yaml"
        return "shown — passes the screen"

    # Not shown: report the most decisive reason first.
    if not passes:
        return f"hidden — did not pass the screen ({reason or 'not_concentrated'})"
    if excl:
        return "hidden — excluded in config/curation.yaml"
    if ft_excluded:
        return f"hidden — firm type '{ftype}' is excluded"
    return "hidden"
