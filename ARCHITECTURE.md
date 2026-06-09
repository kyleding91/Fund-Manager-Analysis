# Architecture & Progress Notes

A working reference for how the **13F Fund Tracker** ("Value Flow") is built,
how data flows through it, how to update it, and the non-obvious details worth
remembering. Written to be readable without deep coding knowledge.

Last updated: 2026-06-08.

---

## 1. What the project does, in one paragraph

Every quarter, the SEC publishes **13F filings** — the stock holdings of large
investment managers. This project downloads them, keeps only the
**value-oriented, concentrated** managers (the "screen"), stores them in a small
local database, and turns that database into both a **local dashboard**
(Streamlit) and a **public static website** (plain HTML for GitHub Pages). The
whole thing is Python and runs on your Mac; the website is free to host.

---

## 2. The screen (selection criteria)

A manager's filing **passes the screen** for a quarter when:

> **AUM > $2 billion** **AND** ( **≤ 30 distinct issuers** **OR** **top-10 positions ≥ 80% of AUM** )

- The first branch (`≤ 30 issuers`) catches the classic concentrated book.
- The second branch (`top-10 ≥ 80%`) catches managers who hold a long tail of
  tiny positions but still run a genuinely concentrated book in their big names.
- All thresholds live in **`src/config.py`** (`MIN_AUM_USD`, `MAX_HOLDINGS`,
  `TOP_N`, `TOP_N_MIN_PCT`). Change them there, then run `rebuild_universe.py`.

**Full-history backfill:** if a manager passes the screen in *at least one* of
the tracked quarters, we store its holdings for *all* tracked quarters — even
quarters where it briefly dropped below the screen — so its deep-dive timeline
and quarter-over-quarter moves are continuous. This is what `rebuild_universe.py`
does.

---

## 3. Code map (where things live)

```
Fund Manager Analysis/
├── ingest.py            # CLI: load/screen a quarter, --stats, --check
├── rebuild_universe.py  # CLI: re-screen + backfill full history for the universe
├── prune_quarters.py    # CLI: keep only chosen quarters, delete the rest
├── build_site.py        # generate the static website into ./site
├── app.py               # the local Streamlit dashboard
├── requirements.txt     # Python libraries
│
├── src/                 # the building blocks
│   ├── config.py        # ALL tunable settings (screen thresholds, SEC access)
│   ├── edgar_client.py  # download SEC index + filings, rate-limit, cache to data/raw
│   ├── parser.py        # read a filing's cover page + holdings table
│   ├── screener.py      # compute AUM/issuers/top-10 and apply the screen
│   ├── database.py      # SQLite schema, migrations, upserts, the screen ledger
│   ├── pipeline.py      # glue: download → parse → screen → store, for a quarter
│   ├── queries.py       # read queries for the dashboard (fund list, timeline)
│   ├── insights.py      # quarter-over-quarter, most-held, concentration
│   ├── classify.py      # label filer type (manager vs pension vs market-maker…)
│   ├── site_data.py     # shape DB rows into the dict the website templates expect
│   └── quality.py       # automated data-quality / invariant checks
│
├── web/                 # website source (used by build_site.py)
│   ├── templates/       # Jinja2 HTML: base, index, funds, fund, stocks, methodology
│   └── static/          # style.css, app.js (search/sort/filter in the browser)
│
├── data/
│   ├── 13f.db           # the SQLite database  (TRACKED in git — see §6)
│   └── raw/             # cached SEC filings (~12 GB, NOT in git, local only)
│
├── site/                # generated website (NOT in git, rebuilt by CI)
├── tests/               # unittest suite
└── .github/workflows/   # update-site.yml — the quarterly auto-update automation
```

---

## 4. The database (data/13f.db)

Four tables. The first three are the classic fund→filing→holding chain; the
fourth is the new criteria ledger.

| Table | Rows (≈) | One row = | Key columns |
|---|---|---|---|
| `funds` | 302 | a manager | `cik` (SEC id), name, latest AUM |
| `filings` | 1,498 | a manager's filing for one quarter | `cik`, `quarter_label`, `total_aum_usd`, `num_issuers`, `top_n_pct`, `passes_screen`, `is_current` |
| `holdings` | 118,113 | one stock position in a filing | `filing_id`, issuer, value, shares |
| `quarter_screen` | 42,129 | **every** filer scanned in a quarter | `(cik, quarter_label)` PK, `meets_count`, `meets_weight`, `passes_screen`, AUM, top-10 % |

**Relationships:** `funds.cik` → `filings.cik` → `holdings.filing_id`.
`quarter_screen` is a standalone ledger keyed by `(cik, quarter_label)`.

**Two flags that are easy to confuse:**
- **`passes_screen`** — did this filing meet the selection criteria that quarter?
- **`is_current`** — is this the live filing for that manager+period? An
  amendment (`13F-HR/A`) supersedes the original, so the original's
  `is_current` flips to 0.

**Why `quarter_screen` exists:** it records the screen result for *every* filer
we scan, not just the ones that pass. That lets `rebuild_universe.py` cheaply
answer "who qualified in any tracked quarter?" without re-downloading, and gives
you an auditable record of why each manager is or isn't in the universe.

---

## 5. How data flows (the pipeline)

```
SEC EDGAR  ──download──▶  data/raw/ (cache)
                              │
                          parser.py  ──▶  cover page (manager, period) + holdings
                              │
                         screener.py  ──▶  AUM, # issuers, top-10 %, pass/fail
                              │
                         pipeline.py  ──▶  record_screen() into quarter_screen
                              │            upsert_fund() into funds/filings/holdings
                              ▼
                          data/13f.db
                         /            \
                  app.py (dashboard)   build_site.py ──▶ site/ ──▶ GitHub Pages
```

**Quarter labels follow the holdings date, not the filing date.** Holdings as of
2025-03-31 are "2025-Q1", even though they're filed ~45 days later in the SEC's
2025-QTR2 index window. `pipeline.index_quarter_for_holdings()` does this mapping.

---

## 6. How to make updates

**Add the newest quarter (manual):**
```bash
python3 ingest.py --backfill 1          # load the latest available quarter
python3 rebuild_universe.py             # re-screen + backfill full history
python3 build_site.py                   # regenerate ./site
```

**Add the newest quarter (automatic):** `.github/workflows/update-site.yml`
runs a few times around each 13F deadline (mid Feb/May/Aug/Nov). It loads the
latest quarter, runs `rebuild_universe.py --backfill-only` (reuses the committed
ledger, so it only downloads the universe's filings), rebuilds the site, commits
the refreshed `data/13f.db` back to the repo, and publishes to Pages. You can
also trigger it by hand from the **Actions** tab.

**Change the screen thresholds:** edit `src/config.py`, then
`python3 rebuild_universe.py` to re-screen everything under the new rules.

**Keep only specific quarters:**
```bash
python3 prune_quarters.py --keep 2025-Q1 2025-Q2 2025-Q3 2025-Q4 2026-Q1
python3 prune_quarters.py --keep 2026-Q1 --dry-run    # preview, change nothing
```

**Why `data/13f.db` is committed to git:** so the CI job can add each new quarter
*incrementally* instead of re-scanning years of SEC filings every run. The large
`data/raw/` cache stays local only (`.gitignore`).

---

## 7. Details worth noticing / tracking

- **Units gotcha (handled):** before 2023-01-03 the SEC reported values in
  *thousands*; after, in *whole dollars*. `config.DOLLARS_CUTOVER_DATE` + the
  parser normalize everything to whole dollars. Get this wrong and AUM is 1000× off.
- **Distinct issuers, not rows:** a manager can list the same company on several
  lines (stock + call + put). The screen counts unique issuers, not raw rows.
- **Amendments can be for old periods:** a `13F-HR/A` filed in this quarter's
  index can restate an *old* quarter. During a `store_all` backfill these can
  pull in unwanted historical quarters — that's why `prune_quarters.py` exists to
  trim the DB back to the tracked window.
- **Partial-amendment quirk (KNOWN ISSUE, not yet fixed):** some `13F-HR/A`
  filings amend only a few lines, not the whole book. Because `is_current` makes
  the amendment supersede the original, a manager's quarter can look sparse (e.g.
  Berkshire's 2025-Q1 current filing is a 3-holding amendment, while the full
  33-issuer original sits with `is_current=0`). This inflates the next quarter's
  "new buys" count. Flagged for a follow-up; the fix is to treat partial
  amendments as overlays on the original rather than full replacements.
- **SEC politeness:** `config.py` caps requests at 6/sec (under the SEC's 10/sec
  limit). A full quarter scan is intentionally slow. Contact email is in
  `config.CONTACT_EMAIL`, overridable via the `SEC_CONTACT_EMAIL` env var / repo
  secret.
- **Current tracked window:** 2025-Q1, 2025-Q2, 2025-Q3, 2025-Q4, 2026-Q1
  (five quarters). 268 managers now have all five quarters of history.

---

## 8. Tests & checks

```bash
python3 -m unittest discover -s tests     # full suite
python3 ingest.py --check                 # data-quality invariants on the live DB
python3 ingest.py --stats                 # counts per table / quarter
```

`src/quality.py` enforces the screen invariant (a passer must have AUM above the
floor AND meet at least one concentration measure) and flags zero/negative
holding values.
