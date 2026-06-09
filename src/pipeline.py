"""Orchestration — ingest a quarter end to end: download -> parse -> screen -> load.

This is the glue between Phases 1-3. The quarterly CLI (Phase 6) calls run_quarter().
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import config
from .database import connect, init_db, upsert_fund, record_screen, stats
from .edgar_client import EdgarClient, FilingRef
from .parser import parse_submission
from .screener import screen_filing, ScreenedFund

log = logging.getLogger(__name__)


@dataclass
class RunSummary:
    year: int
    quarter: int
    scanned: int = 0
    passed: int = 0
    errors: int = 0
    passers: list[str] = field(default_factory=list)  # "manager (cik)"


def index_quarter_for_holdings(year: int, quarter: int) -> tuple[int, int]:
    """Map a holdings quarter to the EDGAR index quarter it is filed in.

    13F holdings as of the end of a quarter are filed (due ~45 days later) in the
    *following* calendar quarter's filing window. E.g. holdings as of 2025-03-31
    (2025-Q1) appear in the 2025-QTR2 index.
    """
    if quarter == 4:
        return year + 1, 1
    return year, quarter + 1


def process_ref(conn, client: EdgarClient, ref: FilingRef, *,
                store_all: bool = False, record_all: bool = True) -> ScreenedFund | None:
    """Download + parse + screen one filing.

    Always records the screen result in the per-quarter ledger (unless
    ``record_all`` is False). Stores the filing's holdings if it passes the
    screen, or unconditionally when ``store_all`` is set (used to backfill the
    full history of managers that qualify in *some* quarter).
    """
    text = client.fetch_submission(ref)
    parsed = parse_submission(
        text, cik=ref.cik, form_type=ref.form_type,
        date_filed=ref.date_filed, accession=ref.accession,
    )
    if parsed is None:
        return None
    sf = screen_filing(parsed)
    if record_all:
        record_screen(conn, sf)
    if sf.passes_screen or store_all:
        upsert_fund(conn, sf)
    return sf


def run_quarter(year: int, quarter: int, *, limit: int | None = None,
                max_passes: int | None = None, only_ciks: set[str] | None = None,
                store_all: bool = False, record_all: bool = True,
                db_path=None, client: EdgarClient | None = None) -> RunSummary:
    """Scan a quarter's 13F filings and load the ones passing the screen.

    Note:
        `year`/`quarter` are the HOLDINGS quarter you want (e.g. 2025, 1 means
        "holdings as of 2025-03-31"). We fetch the EDGAR index for the quarter
        those filings are actually filed in.

    Args:
        limit:      stop after scanning this many filings (for quick smoke tests).
        max_passes: stop early once this many funds have passed (quick tests).
        only_ciks:  restrict to these CIKs (used to backfill specific funds).
    """
    client = client or EdgarClient()
    summary = RunSummary(year=year, quarter=quarter)
    idx_year, idx_q = index_quarter_for_holdings(year, quarter)

    with connect(db_path) as conn:
        init_db(conn)
        refs = client.quarterly_filings(idx_year, idx_q)
        if only_ciks is not None:
            refs = [r for r in refs if r.cik in only_ciks]

        for i, ref in enumerate(refs, 1):
            if limit and summary.scanned >= limit:
                break
            if max_passes and summary.passed >= max_passes:
                break
            try:
                sf = process_ref(conn, client, ref,
                                 store_all=store_all, record_all=record_all)
                summary.scanned += 1
                if sf and sf.passes_screen:
                    summary.passed += 1
                    summary.passers.append(f"{sf.manager_name} ({sf.cik})")
                    conn.commit()   # persist each passer so a kill can't lose it
                    log.info("  PASS [%d] %s  $%.1fB  %d issuers",
                             summary.passed, sf.manager_name,
                             sf.total_aum_usd / 1e9, sf.num_issuers)
            except Exception as exc:  # noqa: BLE001 — keep going past bad filings
                summary.errors += 1
                log.warning("  error on %s (%s): %s", ref.company, ref.accession, exc)
            if summary.scanned % 250 == 0:
                conn.commit()   # periodic checkpoint for durability/resumability
                log.info("...scanned %d filings, %d passed", summary.scanned, summary.passed)

        db_stats = stats(conn)

    log.info("Done %dQ%d: scanned=%d passed=%d errors=%d | DB now: %s",
             year, quarter, summary.scanned, summary.passed, summary.errors, db_stats)
    return summary
