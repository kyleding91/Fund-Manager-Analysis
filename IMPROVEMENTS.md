# Platform Review & Improvement Plan

_Reviewed as PM + UI/UX designer after the first full 2026-Q1 load (165 funds)._

## What works today
- End-to-end pipeline (SEC → screen → SQLite → dashboard) is solid and tested.
- Three functional tabs: Funds, Find a stock, Insights.
- Real, correct data; data-quality checks catch bad filings.

## Problems & opportunities found in review
1. **Filer types are mixed together** — foundations, pensions, sovereign funds,
   operating companies, and market-makers sit next to real stock-pickers with no
   way to tell them apart or filter. *(User-reported.)*
2. **`usd()` breaks above $1T** — combined AUM renders as "$1,405…B" (truncated).
3. **No "universe" view** — the app lands straight on a table; there's no
   at-a-glance read on the whole screened set (size distribution, conviction
   names, type mix, concentration).
4. **Plain default theme** — no brand identity or visual hierarchy.
5. **Tables show AUM as text** — not numerically sortable; no visual weighting.
6. **No data export** — can't pull a list to a spreadsheet.
7. **No data-freshness indicator** — user can't see which quarter/when loaded.
8. **Raw issuer names** — no ticker symbols (needs external mapping).

## Prioritized backlog

### P0 — doing now
- [x] **Filer-type classifier** (`src/classify.py`): Investment Manager, Foundation/
      Endowment, Pension/Sovereign, Bank/Insurance, Market-Maker/Broker, Operating Co.
- [x] **Filer-type filter + "Investment managers only" toggle** + type badges.
- [x] **Fix `usd()`** to format trillions (and a numeric, sortable AUM column).
- [x] **New "Overview" tab**: universe KPIs + charts (AUM distribution, filer-type
      mix, holdings-count distribution, most-held names, most concentrated).
- [x] **CSV export** of the current fund list.
- [x] **Brand theme** (`.streamlit/config.toml`) + cleaner layout & freshness caption.

### P1 — next
- [ ] Universe-wide quarter-over-quarter "biggest buys/sells" (needs more history loaded).
- [ ] Per-holding % shown as visual bars; sortable numeric columns everywhere.
- [ ] Fund comparison (side-by-side two managers).

### P2 — later
- [ ] CUSIP → ticker mapping (OpenFIGI / SEC mapping) for friendly symbols.
- [ ] Sector/industry tags and sector exposure charts.
- [ ] Watchlist + email alerts on new filings; scheduled quarterly auto-refresh.
- [ ] Simple performance proxy (price change since filing).
