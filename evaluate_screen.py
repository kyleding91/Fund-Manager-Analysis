#!/usr/bin/env python3
"""Evaluate the screen against a labeled benchmark — a READ-ONLY audit.

Reads the live database (data/13f.db) and config/benchmark.yaml, then reports:

  * the shown ("curated universe") count + AUM for a quarter, and the shown list
    with each filer's metrics, firm type, and which branch admitted it;
  * suspected false positives still in the shown universe (very few names, or an
    excluded firm type that somehow slipped through);
  * benchmark violations — any must_pass that is hidden, or must_exclude that is
    shown — each with the one-line "why" from curation.explain();
  * a PASS/FAIL verdict on the mechanical acceptance criteria.

It writes JSON + Markdown to data/audit/ and prints a short summary. It NEVER
writes to the database or to any config file — the auto-iteration loop edits the
YAML policy files, re-screens, and re-runs this script.

Usage:
  python3 evaluate_screen.py                 # latest quarter in the DB
  python3 evaluate_screen.py --quarter 2026-Q1
  python3 evaluate_screen.py --strict        # exit non-zero if criteria fail
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src import classify, config, curation
from src.database import connect

AUDIT_DIR = config.DATA_DIR / "audit"
BENCHMARK_PATH = config.CONFIG_DIR / "benchmark.yaml"

# A shown filer with fewer than this many distinct issuers is suspected to be a
# single-stake operating/holding/PE vehicle rather than a real portfolio.
MIN_REASONABLE_ISSUERS = 3
# Acceptance criterion #3: suspected false positives must be under this fraction.
MAX_FP_FRACTION = 0.05


def _load_benchmark() -> dict:
    try:
        raw = yaml.safe_load(BENCHMARK_PATH.read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, yaml.YAMLError, OSError):
        raw = {}
    return {
        "must_pass": raw.get("must_pass") or [],
        "must_exclude": raw.get("must_exclude") or [],
    }


def _latest_quarter(conn) -> str | None:
    row = conn.execute(
        "SELECT MAX(quarter_label) FROM filings WHERE quarter_label IS NOT NULL"
    ).fetchone()
    return row[0] if row else None


def is_rescreened(conn) -> bool:
    """True if the DB has the firm-type column (added by the new screen pipeline).

    A DB created before this change must be re-screened (rebuild_universe.py)
    before the audit can run, since the column it queries won't exist yet.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(filings)")}
    return "filer_type" in cols


def _shown_rows(conn, quarter: str) -> list[dict]:
    """The curated, shown universe for a quarter (what the site/dashboard show)."""
    rows = conn.execute(
        f"""SELECT f.cik, fn.manager_name, f.num_issuers, f.num_positions,
                   f.total_aum_usd, f.top_n_pct, f.filer_type,
                   qs.meets_count, qs.meets_weight, qs.passes_screen,
                   qs.reject_reason
            FROM filings f
            JOIN funds fn ON fn.cik = f.cik
            LEFT JOIN quarter_screen qs
                   ON qs.cik = f.cik AND qs.quarter_label = f.quarter_label
            WHERE f.quarter_label = ? AND f.is_current = 1
              AND {curation.screen_predicate("f.")}
            ORDER BY f.total_aum_usd DESC""",
        (quarter,),
    ).fetchall()
    out = []
    for r in rows:
        lapsed = (r["passes_screen"] is not None) and not r["passes_screen"]
        if r["meets_count"]:
            branch = "count (<= max_holdings)"
        elif r["meets_weight"]:
            branch = "weight (top-N concentration)"
        elif lapsed:
            branch = "roster (lapsed)"
        else:
            branch = "include/override"
        out.append({
            "cik": str(r["cik"]),
            "name": r["manager_name"],
            "num_issuers": r["num_issuers"],
            "num_positions": r["num_positions"],
            "aum_usd": r["total_aum_usd"] or 0.0,
            "top_n_pct": r["top_n_pct"] or 0.0,
            "filer_type": r["filer_type"] or "",
            "branch": branch,
            "lapsed": lapsed,
            "reject_reason": r["reject_reason"] or "",
        })
    return out


def _is_shown(conn, cik, quarter: str) -> bool:
    norm = curation._norm(cik)
    row = conn.execute(
        f"""SELECT 1 FROM filings f
            WHERE LTRIM(f.cik, '0') = ? AND f.quarter_label = ?
              AND f.is_current = 1 AND {curation.screen_predicate("f.")}
            LIMIT 1""",
        (norm, quarter),
    ).fetchone()
    return row is not None


def _duplicate_books(conn, quarter: str, shown: list[dict]) -> list[dict]:
    """Pairs of shown filers reporting byte-identical books.

    A fund and its adviser/GP sometimes BOTH file a 13F covering the same
    positions — two CIKs, one portfolio — which double-counts AUM, holder
    counts and flows. Cheap detection: only filers with the same rounded AUM
    and issuer count are candidates; their (issuer, value) sets are compared.
    """
    from collections import defaultdict
    groups = defaultdict(list)
    for s in shown:
        groups[(round(s["aum_usd"]), s["num_issuers"])].append(s)

    def book(cik):
        return {(h["issuer_cusip"], round(h["value_usd"] or 0)) for h in conn.execute(
            """SELECT h.issuer_cusip, h.value_usd
               FROM holdings h JOIN filings f ON f.id = h.filing_id
               WHERE f.cik = ? AND f.quarter_label = ? AND f.is_current = 1""",
            (str(cik), quarter))}

    out = []
    for rs in groups.values():
        if len(rs) < 2:
            continue
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = book(rs[i]["cik"]), book(rs[j]["cik"])
                if a and a == b:
                    out.append({
                        "name_a": rs[i]["name"], "cik_a": rs[i]["cik"],
                        "name_b": rs[j]["name"], "cik_b": rs[j]["cik"],
                        "aum_usd": rs[i]["aum_usd"],
                        "num_issuers": rs[i]["num_issuers"],
                    })
    return out


def evaluate(conn, quarter: str) -> dict:
    bench = _load_benchmark()
    shown = _shown_rows(conn, quarter)
    shown_norm = {curation._norm(s["cik"]) for s in shown}
    excluded_types = set(classify.excluded_firm_types())

    total_aum = sum(s["aum_usd"] for s in shown)
    duplicate_books = _duplicate_books(conn, quarter, shown)

    # Suspected false positives still inside the shown universe. Lapsed roster
    # members are knowingly kept (sticky universe) — they go to the separate
    # review list below rather than counting as false positives.
    suspected_fp, lapsed_members = [], []
    for s in shown:
        if s.get("lapsed"):
            lapsed_members.append(s)
            continue
        flags = []
        if s["num_issuers"] is not None and s["num_issuers"] < MIN_REASONABLE_ISSUERS:
            flags.append(f"only {s['num_issuers']} issuer(s)")
        if s["num_issuers"] is not None and s["num_issuers"] > config.MAX_HOLDINGS_WEIGHTED:
            flags.append(f"{s['num_issuers']} issuers > weighted ceiling")
        if s["filer_type"] in excluded_types:
            flags.append(f"excluded firm type '{s['filer_type']}'")
        if flags:
            suspected_fp.append({**s, "flags": flags})

    # Benchmark violations.
    must_pass_hidden, mechanical_hidden = [], []
    for entry in bench["must_pass"]:
        norm = curation._norm(entry.get("cik"))
        if norm not in shown_norm:
            why = curation.explain(conn, entry.get("cik"), quarter)
            rec = {"cik": str(entry.get("cik")), "name": entry.get("name"), "why": why}
            must_pass_hidden.append(rec)
            # Criterion #4: hidden by a mechanical rule (not curation/firm-type)?
            if why.startswith("hidden — did not pass the screen"):
                mechanical_hidden.append(rec)

    must_exclude_shown = []
    for entry in bench["must_exclude"]:
        norm = curation._norm(entry.get("cik"))
        if norm in shown_norm:
            why = curation.explain(conn, entry.get("cik"), quarter)
            must_exclude_shown.append(
                {"cik": str(entry.get("cik")), "name": entry.get("name"), "why": why})

    fp_fraction = (len(suspected_fp) / len(shown)) if shown else 0.0
    criteria = {
        "must_pass_all_shown": len(must_pass_hidden) == 0,
        "must_exclude_none_shown": len(must_exclude_shown) == 0,
        "false_positives_under_threshold": fp_fraction < MAX_FP_FRACTION,
        "no_must_pass_hidden_by_rule": len(mechanical_hidden) == 0,
    }
    accepted = all(criteria.values())

    return {
        "quarter": quarter,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shown_count": len(shown),
        "shown_aum_usd": total_aum,
        "shown": shown,
        "suspected_false_positives": suspected_fp,
        "lapsed_members": lapsed_members,
        "duplicate_books": duplicate_books,
        "fp_fraction": fp_fraction,
        "benchmark": {
            "must_pass_total": len(bench["must_pass"]),
            "must_exclude_total": len(bench["must_exclude"]),
            "must_pass_hidden": must_pass_hidden,
            "must_pass_hidden_by_mechanical_rule": mechanical_hidden,
            "must_exclude_shown": must_exclude_shown,
        },
        "criteria": criteria,
        "accepted": accepted,
        "thresholds": {
            "min_aum_usd": config.MIN_AUM_USD,
            "max_holdings": config.MAX_HOLDINGS,
            "max_holdings_weighted": config.MAX_HOLDINGS_WEIGHTED,
            "min_holdings": config.MIN_HOLDINGS,
            "top_n": config.TOP_N,
            "top_n_min_pct": config.TOP_N_MIN_PCT,
            "excluded_firm_types": list(excluded_types),
        },
    }


def _b(x: float) -> str:
    return f"${x / 1e9:,.1f}B"


def _markdown(report: dict) -> str:
    c = report["criteria"]
    tick = lambda ok: "✅" if ok else "❌"  # noqa: E731
    lines = [
        f"# Screen audit — {report['quarter']}",
        "",
        f"_Generated {report['generated_at']}_",
        "",
        "## Acceptance criteria",
        "",
        f"- {tick(c['must_pass_all_shown'])} 100% of must_pass shown",
        f"- {tick(c['must_exclude_none_shown'])} 0% of must_exclude shown",
        f"- {tick(c['false_positives_under_threshold'])} suspected false positives "
        f"< {int(MAX_FP_FRACTION * 100)}% of shown "
        f"({len(report['suspected_false_positives'])}/{report['shown_count']} "
        f"= {report['fp_fraction'] * 100:.1f}%)",
        f"- {tick(c['no_must_pass_hidden_by_rule'])} no must_pass hidden purely by a "
        "mechanical rule",
        "",
        f"**Verdict: {'ACCEPTED ✅' if report['accepted'] else 'NOT YET ❌'}** "
        "(criterion 5 — agent sign-off — is judged separately)",
        "",
        "## Shown universe",
        "",
        f"- **{report['shown_count']}** filers, **{_b(report['shown_aum_usd'])}** total AUM",
        "",
    ]

    viol = report["benchmark"]
    if viol["must_exclude_shown"]:
        lines += ["## ❌ must_exclude that are STILL shown", ""]
        for v in viol["must_exclude_shown"]:
            lines.append(f"- **{v['name']}** (CIK {v['cik']}) — {v['why']}")
        lines.append("")
    if viol["must_pass_hidden"]:
        lines += ["## ❌ must_pass that are HIDDEN", ""]
        for v in viol["must_pass_hidden"]:
            lines.append(f"- **{v['name']}** (CIK {v['cik']}) — {v['why']}")
        lines.append("")

    fps = report["suspected_false_positives"]
    if fps:
        lines += ["## Suspected false positives still shown", "",
                  "| Manager | CIK | Issuers | AUM | Firm type | Flags |",
                  "|---|---|---:|---:|---|---|"]
        for s in fps:
            lines.append(
                f"| {s['name']} | {s['cik']} | {s['num_issuers']} | {_b(s['aum_usd'])} "
                f"| {s['filer_type'] or '—'} | {'; '.join(s['flags'])} |")
        lines.append("")

    dups = report.get("duplicate_books") or []
    if dups:
        lines += [
            "## ⚠ Duplicate books — two filers, one portfolio", "",
            "These pairs report byte-identical holdings (a fund and its "
            "adviser/GP both filing). Each pair double-counts AUM, holder "
            "counts and flows until one is excluded in `config/curation.yaml`.", "",
            "| Filer A | CIK | Filer B | CIK | AUM | Names |", "|---|---|---|---|---|---|"]
        for d in dups:
            lines.append(
                f"| {d['name_a']} | {d['cik_a']} | {d['name_b']} | {d['cik_b']} "
                f"| {_b(d['aum_usd'])} | {d['num_issuers']} |")
        lines.append("")

    lapsed = report.get("lapsed_members") or []
    if lapsed:
        lines += [
            "## ⏸ Lapsed members — kept by default, FOR YOUR REVIEW", "",
            "Sticky-roster members that failed this quarter's mechanical screen. "
            "They stay shown until you act. To remove one, edit its entry in "
            "`config/roster.yaml` (`status: removed` + a reason). To keep it, "
            "do nothing.", "",
            "| Manager | CIK | Issuers | AUM | Lapse reason |",
            "|---|---|---:|---:|---|"]
        for s in lapsed:
            lines.append(
                f"| {s['name']} | {s['cik']} | {s['num_issuers']} | {_b(s['aum_usd'])} "
                f"| {s['reject_reason'] or '—'} |")
        lines.append("")

    lines += ["## Shown filers (by AUM)", "",
              "| Manager | CIK | Issuers | AUM | Top-N % | Firm type | Branch |",
              "|---|---|---:|---:|---:|---|---|"]
    for s in report["shown"]:
        lines.append(
            f"| {s['name']} | {s['cik']} | {s['num_issuers']} | {_b(s['aum_usd'])} "
            f"| {s['top_n_pct']:.0f}% | {s['filer_type'] or '—'} | {s['branch']} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="Audit the screen against the benchmark.")
    p.add_argument("--quarter", help="Holdings quarter label, e.g. 2026-Q1 (default: latest).")
    p.add_argument("--strict", action="store_true",
                   help="Exit non-zero if the mechanical acceptance criteria fail.")
    args = p.parse_args()

    with connect() as conn:
        if not is_rescreened(conn):
            raise SystemExit(
                "This database predates the firm-type screen. Run "
                "`python3 rebuild_universe.py` first to re-screen and add the "
                "audit columns, then re-run this audit.")
        quarter = args.quarter or _latest_quarter(conn)
        if not quarter:
            raise SystemExit("No quarters in the database. Load some first with ingest.py.")
        report = evaluate(conn, quarter)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "screen_audit.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    md = _markdown(report)
    (AUDIT_DIR / "screen_audit.md").write_text(md, encoding="utf-8")

    c = report["criteria"]
    print(f"Quarter {quarter}: {report['shown_count']} shown, "
          f"{_b(report['shown_aum_usd'])} AUM.")
    print(f"  must_pass hidden:      {len(report['benchmark']['must_pass_hidden'])} "
          f"(of {report['benchmark']['must_pass_total']})")
    print(f"  must_exclude shown:    {len(report['benchmark']['must_exclude_shown'])} "
          f"(of {report['benchmark']['must_exclude_total']})")
    print(f"  suspected FPs:         {len(report['suspected_false_positives'])} "
          f"({report['fp_fraction'] * 100:.1f}% of shown)")
    print(f"  lapsed members:        {len(report.get('lapsed_members') or [])} "
          f"(kept by default — see report for review)")
    if report.get("duplicate_books"):
        print(f"  ⚠ duplicate books:     {len(report['duplicate_books'])} pair(s) "
              f"— two filers reporting one portfolio (see report)")
    print(f"  criteria: {sum(c.values())}/4 mechanical passed → "
          f"{'ACCEPTED' if report['accepted'] else 'NOT YET'}")
    print(f"  report: {AUDIT_DIR / 'screen_audit.md'}")

    if args.strict and not report["accepted"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
