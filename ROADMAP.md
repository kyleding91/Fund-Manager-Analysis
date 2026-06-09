# 13F Fund Tracker — Project Roadmap

A local app to download quarterly **13F filings** from the SEC, screen for
**value-oriented, concentrated managers**, store everything in a database, and
review the insights in a simple web dashboard.

---

## ✅ Build status — all 6 phases complete

All phases are built, tested, and verified against live SEC data. See `README.md`
to run it.

| Phase | Status | Delivered |
|---|---|---|
| 0 — Setup | ✅ | Project scaffold, `src/config.py`, deps, SEC access confirmed |
| 1 — Ingestion | ✅ | `src/edgar_client.py` — index parse, download, cache, rate-limit |
| 2 — Parse & screen | ✅ | `src/parser.py`, `src/screener.py` — units + screen logic |
| 3 — Database | ✅ | `src/database.py` — SQLite, idempotent, amendment handling |
| 4 — Dashboard | ✅ | `app.py`, `src/queries.py` — funds, detail, filters, search |
| 5 — Insights | ✅ | `src/insights.py` — QoQ, most-held, concentration, new managers |
| 6 — Automation | ✅ | `ingest.py` CLI, `src/quality.py` checks, `README.md` |

**Verification:** 15 automated tests pass; loaded 2 real quarters (15 concentrated
funds incl. Abrams, Akre, Altimeter, Pershing-style books); dashboard + insights
render with no errors; data-quality check clean.

---

## Goal in one sentence

Every quarter, automatically pull 13F filings from SEC EDGAR, keep only funds
with **AUM > $2 billion AND fewer than 30 holdings**, and let me explore their
holdings and quarter-over-quarter changes in a web app.

---

## What gets tracked

| Field | Description |
|---|---|
| Fund name | The investment manager (e.g. "Scion Asset Management") |
| Quarter | The report period (e.g. 2025-Q1) |
| Total 13F AUM | Sum of all holding values in the filing |
| Holding count | Number of distinct positions (used for the < 30 screen) |
| Per holding: company | Issuer name + ticker/CUSIP |
| Per holding: value | Dollar value reported |
| Per holding: shares | Number of shares (or principal amount) |
| Per holding: % of portfolio | Holding value ÷ total portfolio value |

---

## Recommended tech stack (all Python — one language, few moving parts)

- **Python** — downloads and processes the filings
- **SQLite** — the database; a single file on your Mac, zero setup
- **Streamlit** — the web dashboard; runs locally with one command
- **Libraries**: `requests` (download), `lxml` (read filings), `pandas` (tables)

This keeps everything in one language and avoids servers, accounts, or hosting.

---

## How the SEC data works (key facts baked into the plan)

- 13F filings are SEC form types **`13F-HR`** and **`13F-HR/A`** (amendments).
- A quarterly **index file** lists every filing; each filing contains an
  **information table** (the holdings) and a **cover page** (the fund name + period).
- SEC requires a **User-Agent header with your email** and polite rate limiting
  (~10 requests/second max). This is free but the rules must be followed.
- ⚠️ **Units gotcha:** filings before 2023 report values in **thousands** of
  dollars; later filings report **whole dollars**. The code must normalize this
  or AUM will be off by 1000×.
- "Concentrated" = count of **distinct issuers**. A fund may list multiple lines
  for one company (e.g. stock + call options); we'll count unique companies, not
  raw rows, for the < 30 screen.

---

## Phases & key tasks

### Phase 0 — Setup & foundations
*Goal: a working Python environment and project skeleton.*
- [ ] Install Python and a code editor (with step-by-step help)
- [ ] Create the project folder structure
- [ ] Set up a virtual environment and install libraries
- [ ] Save your contact email for the SEC User-Agent header
- [ ] Download **one** sample 13F filing by hand to confirm access works

### Phase 1 — Data ingestion (download from EDGAR)
*Goal: pull all 13F filings for a chosen quarter.*
- [ ] Fetch the SEC quarterly index and filter to `13F-HR` / `13F-HR/A`
- [ ] Download each filing's information table + cover page
- [ ] Respect SEC rate limits and add retries for failed downloads
- [ ] Cache raw files locally so we never re-download the same quarter

### Phase 2 — Parsing & screening
*Goal: turn raw filings into clean rows and apply your filter.*
- [ ] Parse the information table → company, value, shares per holding
- [ ] Parse the cover page → fund name + report period
- [ ] Normalize the thousands-vs-dollars units issue
- [ ] Compute total AUM and distinct holding count per fund
- [ ] **Apply the screen: keep AUM > $2B AND < 30 holdings**
- [ ] Compute each holding's % of portfolio

### Phase 3 — Database
*Goal: store everything so quarters accumulate over time.*
- [ ] Design tables: `funds`, `filings` (one per fund per quarter), `holdings`
- [ ] Load screened data into SQLite
- [ ] Handle re-runs safely (don't duplicate a quarter already loaded)
- [ ] Handle amendments (`13F-HR/A`) overriding the original filing

### Phase 4 — Frontend dashboard (Streamlit)
*Goal: review insights in the browser.*
- [ ] List of funds that passed the screen, sorted by AUM
- [ ] Fund detail page: holdings table with value, shares, % of portfolio
- [ ] Filters: by quarter, by AUM range, by holding count
- [ ] Search by fund name or by a stock they hold

### Phase 5 — Insights & analysis
*Goal: the "so what" — what changed and what's interesting.*
- [ ] Quarter-over-quarter changes per fund: new buys, sells, trims, adds
- [ ] "Most-held stocks" across all screened funds (conviction signals)
- [ ] Biggest position concentration (top holding as % of portfolio)
- [ ] New managers that just entered the screen this quarter

### Phase 6 — Automation & polish
*Goal: one click each quarter.*
- [ ] A single command that ingests, screens, and loads a new quarter
- [ ] A reminder/checklist for when each quarter's filings post (~45 days after
      quarter-end)
- [ ] Basic data-quality checks (flag funds with missing/odd values)
- [ ] Short "how to run it" notes for future you

---

## Suggested build order (milestones)

1. **Prove the pipeline on one quarter, one fund** — download → parse → print.
2. **Scale to a full quarter** — all filings, screen applied, into SQLite.
3. **See it** — Streamlit dashboard reading from the database.
4. **Add history** — load several past quarters; enable change analysis.
5. **Automate** — one-command quarterly refresh.

---

## Open questions to revisit later

- How many **past quarters** of history do you want to backfill (e.g. last 2
  years vs. last 5)?
- Do you want **email/CUSIP→ticker mapping** (nicer names) — needs a free lookup
  source — or are CUSIPs fine to start?
- Should the screen thresholds ($2B, 30 holdings) be **adjustable** in the app so
  you can experiment?
