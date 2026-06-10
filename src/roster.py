"""The membership roster — sticky universe with human-only removal.

The mechanical screen (screener.py) decides who *qualifies* each quarter; this
module decides who is *shown*. The rule, chosen by the project owner:

    Once a manager is admitted to the universe, it STAYS by default — even if a
    later quarter's screen would exclude it. Members who fail the latest screen
    are flagged as "lapsed" for human review; only a human removes a member, by
    editing config/roster.yaml with a reason. New qualifiers join automatically.

config/roster.yaml is the single registry: one entry per member with the CIK,
name, the quarter it joined, how it was added (screen / grandfathered / manual)
and its status (active / removed + reason). Git history is the audit trail of
every membership decision.

Fallback: if the roster file is missing or empty, curation.screen_predicate
falls back to the per-quarter mechanical screen — so a fresh checkout, the
offline test-suite, and the pre-roster behavior all keep working.

NOTE: this module must not import curation (curation imports us); callers pass
in any exclusion sets they need (see add_members' caller in rebuild_universe).
"""
from __future__ import annotations

from functools import lru_cache

import yaml

from . import config

ROSTER_PATH = config.CONFIG_DIR / "roster.yaml"

_HEADER = """\
# Universe membership roster (STICKY) ------------------------------------------
#
# One entry per manager ever admitted to the curated universe. The mechanical
# screen is the ADMISSION test: new qualifiers are appended automatically each
# quarter (added_by: screen). NOBODY is removed automatically — a member that
# stops meeting the criteria is only flagged as "lapsed" for review.
#
# To REMOVE a member (the only manual step), edit its entry:
#     status: removed
#     removed_quarter: 2026-Q2
#     reason: drifted into an index-like book, no longer a concentrated manager
# A removed member is never auto-re-added, even if it qualifies again.
#
# Fields: cik (SEC id), name, joined (first qualifying quarter),
#         added_by (screen | grandfathered | manual), status (active | removed).
# Git tracks every change, so membership decisions are permanently auditable.
"""


def _norm(cik) -> str:
    """Normalize a CIK to its no-leading-zeros string form."""
    s = str(cik).strip().lstrip("0")
    return s or "0"


@lru_cache(maxsize=1)
def _load() -> list[dict]:
    try:
        raw = yaml.safe_load(ROSTER_PATH.read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, OSError, yaml.YAMLError):
        return []
    members = raw.get("members") or []
    return [m for m in members if isinstance(m, dict) and m.get("cik") is not None]


def reload() -> None:
    """Drop the cache (call after editing roster.yaml or changing ROSTER_PATH)."""
    _load.cache_clear()


def members() -> list[dict]:
    return list(_load())


def has_roster() -> bool:
    """True when a roster exists — i.e. sticky membership is in effect."""
    return bool(_load())


def active_ciks() -> set[str]:
    """Normalized CIKs of all active members."""
    return {_norm(m["cik"]) for m in _load()
            if (m.get("status") or "active") == "active"}


def all_ciks() -> set[str]:
    """Every CIK ever on the roster, any status (removed members stay removed)."""
    return {_norm(m["cik"]) for m in _load()}


def joined_in(quarter: str) -> set[str]:
    """Active members whose first qualifying quarter is `quarter`."""
    return {_norm(m["cik"]) for m in _load()
            if (m.get("status") or "active") == "active"
            and m.get("joined") == quarter}


def _write(members_list: list[dict]) -> None:
    body = yaml.safe_dump({"members": members_list}, sort_keys=False,
                          default_flow_style=False, allow_unicode=True)
    ROSTER_PATH.write_text(_HEADER + "\n" + body, encoding="utf-8")
    reload()


def add_members(entries: list[dict]) -> int:
    """Append new members (skipping any CIK already on the roster, any status).

    Each entry: {cik, name, joined, added_by}. Returns how many were added.
    Removed members are never resurrected here — that's a human decision.
    """
    existing = all_ciks()
    fresh = []
    for e in entries:
        if _norm(e["cik"]) in existing:
            continue
        fresh.append({
            "cik": int(_norm(e["cik"])) if _norm(e["cik"]).isdigit() else str(e["cik"]),
            "name": e.get("name") or "",
            "joined": e.get("joined") or "",
            "added_by": e.get("added_by") or "screen",
            "status": "active",
        })
        existing.add(_norm(e["cik"]))
    if fresh:
        _write(members() + fresh)
    return len(fresh)
