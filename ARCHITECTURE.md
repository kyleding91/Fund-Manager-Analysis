# Architecture & Progress Notes

A working reference for how the **13F Fund Tracker** ("Value Flow") is built,
how data flows through it, how to update it, and the non-obvious details worth
remembering. Written to be readable without deep coding knowledge.

Last updated: 2026-06-09.

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

> **AUM > $2 billion** **AND** **≥ min_holdings (3) issuers** **AND**
> **< max_etf_pct (50%) of AUM in ETFs/index funds** **AND**
> ( **≤ 30 distinct issuers** **OR** ( **top-10 ≥ 80% of AUM** **AND** **≤ 50 distinct issuers** ) )

- The first branch (`≤ 30 issuers`) catches the classic concentrated book.
- The second branch (`top-10 ≥ 80%`) catches managers who hold a *modest* tail of
  small positions but still run a genuinely concentrated book in their big names.
  The **`≤ 50 issuers` ceiling on this branch** is the headline fix that keeps out
  long-tail mutual-fund / advisor complexes (hundreds–thousands of names) that are
  merely top-heavy. Without it they slipped in via the weight branch.
- `min_holdings` is a floor on distinct issuers (set to `3`). It drops 1–2-stock
  "portfolios" — operating/holding companies, sovereigns and PE vehicles reporting
  one or two strategic stakes. The target band of concentrated value managers is
  ~3–50 names; every benchmark manager holds 8+, so the floor never touches them.
- **Passive-basket guard** (`max_etf_pct`): a filing with ≥ 50% of AUM in ETFs /
  index funds is a passive basket (a sovereign or advisor parking cash in indexes),
  not a stock-picker, so it fails even when the basket looks "concentrated" (a few
  big sector ETFs). ETF sponsors are matched by issuer name in
  `src/classify.py` `is_etf_name()`. This catches filers a *name*-based firm-type
  tag misses (e.g. an "Investment Manager" that actually holds only iShares).
- All thresholds live in **`config/screen.yaml`** (`min_aum_usd`, `max_holdings`,
  `max_holdings_weighted`, `min_holdings`, `top_n`, `top_n_min_pct`, `max_etf_pct`)
  — a plain-text policy file editable from GitHub's web editor, no code needed.
  `src/config.py` loads it (and falls back to built-in defaults if the file or a
  key is missing). Change it, then run `rebuild_universe.py` to re-screen.

**Firm-type tagging (a fact about each filer):** `src/classify.py` tags every
filer with a firm type — `Investment Manager`, `Holding Company`,
`Mutual Fund / Advisor Complex`, `Market Maker / Broker`, etc. — from a name
heuristic, **overridable per-CIK** in **`config/firm_types.yaml`**. The tag is
*stored in the database* (`funds`, `filings`, `quarter_screen`) so it's queryable.
Firm types in the **excluded set** are hidden from the curated universe. We exclude
the institution types that aren't fundamental, concentrated *fund managers*:
`Market Maker / Broker`, `Operating Company`, `Holding Company`,
`Pension / Sovereign`, and `Bank / Insurance` (all in the YAML's `excluded_types:`).
**Foundations/endowments and PE/VC are kept** — some run genuinely concentrated
books (Gates Foundation Trust, Carlyle). Because the name heuristic is imperfect,
per-CIK overrides correct both directions: tagging mis-read operating companies
(Toyota, Exor, Investor AB) *and* protecting real managers the heuristic mislabels
as operating companies (SC US = Sequoia China, Consulta).

**Curation (editorial show/hide):** the screen is purely mechanical. To hand-tune
the published universe, edit **`config/curation.yaml`**:
- `exclude:` — hide managers that pass but you don't want shown (index funds,
  market-makers, duplicates). Takes effect the moment the site is rebuilt; no SEC
  download needed.
- `include:` — force-track managers that don't pass the screen. You must
  (re)load their holdings with `rebuild_universe.py` first, since we only store
  passing managers' data. **Force-include wins** over both exclusion paths.

`config/firm_types.yaml` (facts) is kept separate from `config/curation.yaml`
(editorial). Both, plus `passes_screen`, combine in **exactly one SQL predicate**
— `src/curation.py` `screen_predicate(alias)`:

> `cik in include  OR  ( passes_screen = 1  AND  cik not in exclude  AND  filer_type not in <excluded types> )`

Because `filings.filer_type` is a stored column, the ~8 existing query call sites
(`queries.py`, `insights.py`, `site_data.py`) inherit the firm-type rule with zero
edits. The mechanical `passes_screen` flag is left untouched — it stays the
algorithm's audit trail; firm-type and curation are separate, git-tracked overlays.

**Full-history backfill:** if a manager passes the screen in *at least one* of
the tracked quarters, we store its holdings for *all* tracked quarters — even
quarters where it briefly dropped below the screen — so its deep-dive timeline
and quarter-over-quarter moves are continuous. This is what `rebuild_universe.py`
does.

**Per-stock pages (the reverse view):** `build_site.py` also generates one page
per company held by a screened manager (`stocks/<issuer_cusip>.html`), built from
`site_data.stock_detail` (which uses `insights.holders_of` + `insights.issuer_trend`).
Each lists every shown holder, the per-manager quarter-over-quarter change (by
share count), who newly bought or exited, and the combined position size + holder
count over the tracked quarters — the mirror image of the manager deep-dive,
keyed by the 6-digit issuer CUSIP. All counts respect `screen_predicate`, so only
the curated universe is reflected.

---

## 3. Code map (where things live)

```
Fund Manager Analysis/
├── ingest.py            # CLI: load/screen a quarter, --stats, --check
├── rebuild_universe.py  # CLI: re-screen + backfill full history for the universe
├── prune_quarters.py    # CLI: keep only chosen quarters, delete the rest
├── evaluate_screen.py   # CLI (READ-ONLY): audit the screen vs the benchmark
├── build_site.py        # generate the static website into ./site
├── app.py               # the local Streamlit dashboard
├── requirements.txt     # Python libraries
│
├── config/              # human-editable policy YAML (TRACKED in git)
│   ├── screen.yaml      # screen thresholds (AUM floor, max holdings, top-N, ceiling…)
│   ├── curation.yaml    # editorial exclude/include overrides on the screen
│   ├── firm_types.yaml  # per-CIK firm-type corrections + excluded_types
│   └── benchmark.yaml   # labeled must_pass / must_exclude answer key for the audit
│
├── src/                 # the building blocks
│   ├── config.py        # SEC access + loads screen.yaml (with code defaults)
│   ├── curation.py      # screen.yaml flag + curation + firm-type → ONE SQL predicate
│   ├── edgar_client.py  # download SEC index + filings, rate-limit, cache to data/raw
│   ├── parser.py        # read a filing's cover page + holdings table
│   ├── screener.py      # compute AUM/issuers/top-10, apply the screen, reject_reason()
│   ├── database.py      # SQLite schema, migrations, upserts, the screen ledger
│   ├── pipeline.py      # glue: download → parse → screen → tag firm type → store
│   ├── queries.py       # read queries for the dashboard (fund list, timeline)
│   ├── insights.py      # quarter-over-quarter, most-held, concentration
│   ├── classify.py      # firm-type heuristic + per-CIK overrides + excluded set
│   ├── site_data.py     # shape DB rows into the dict the website templates expect
│   └── quality.py       # automated data-quality / invariant checks
│
├── make_icons.py        # regenerate the PWA / home-screen app icons (Pillow)
│
├── web/                 # website source (used by build_site.py)
│   ├── templates/       # Jinja2 HTML: base, index, funds, fund, stocks, stock, methodology
│   └── static/          # style.css, app.js, manifest.webmanifest, sw.js, icon-*.png
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
| `funds` | 302 | a manager | `cik` (SEC id), name, `filer_type` |
| `filings` | 1,498 | a manager's filing for one quarter | `cik`, `quarter_label`, `total_aum_usd`, `num_issuers`, `top_n_pct`, `passes_screen`, `is_current`, `filer_type` |
| `holdings` | 118,113 | one stock position in a filing | `filing_id`, issuer, value, shares |
| `quarter_screen` | 42,129 | **every** filer scanned in a quarter | `(cik, quarter_label)` PK, `meets_count`, `meets_weight`, `passes_screen`, AUM, top-10 %, `filer_type`, `reject_reason` |

**Audit columns (added with the firm-type screen):**
- **`filer_type`** (on `funds`, `filings`, `quarter_screen`) — the firm-type tag
  (mild denormalization so the one-line predicate needs no joins; written by
  `record_screen` / `upsert_fund`).
- **`reject_reason`** (on `quarter_screen`) — for a filer that *failed* the
  mechanical screen, which gate it failed, from a fixed vocabulary: `confidential`,
  `aum_below_floor`, `below_min_holdings`, `too_many_holdings_for_weight`,
  `not_concentrated` (empty when it passed). `curation.explain(conn, cik, quarter)`
  combines this with firm-type + curation membership to answer, in one line, "why
  is (or isn't) this filer shown?". Forward-only `_migrate()` adds both columns.

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
                         screener.py  ──▶  AUM, # issuers, top-10 %, pass/fail, reject_reason
                              │
                         classify.py  ──▶  firm_type(cik, name)  (heuristic + overrides)
                              │
                         pipeline.py  ──▶  record_screen() into quarter_screen
                              │            upsert_fund() into funds/filings/holdings
                              ▼
                          data/13f.db
                         /       |       \
        app.py (dashboard)  evaluate_screen.py   build_site.py ──▶ site/ ──▶ Pages
                            (read-only audit →
                             data/audit/*.md,json)
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

**Change the screen thresholds:** edit `config/screen.yaml` (e.g. on GitHub,
pencil icon → Commit), then `python3 rebuild_universe.py` to re-screen everything
under the new rules, rebuild the site, and commit the refreshed DB.

**Hide or force-add a manager:** edit `config/curation.yaml`.
- To **exclude**: add the manager's CIK under `exclude:` and rebuild the site
  (`python3 build_site.py`). No SEC download needed — it takes effect immediately
  because exclusions are applied at query time. The CI run will republish it too.
- To **include** a manager that doesn't pass the screen: add its CIK under
  `include:`, then run `python3 rebuild_universe.py` (to download/store its
  holdings) before rebuilding the site.
Every edit is a git commit, so you have a dated audit trail of who was hidden or
added, and why (keep a short `reason:` on each entry).

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
- **Firm type is a fact, curation is an opinion:** `classify.firm_type(cik, name)`
  guesses a type from the name, then lets `config/firm_types.yaml` `overrides:`
  correct it per-CIK. Excluded types (`excluded_types:`, default just
  `Market Maker / Broker`) are *hidden* from the shown universe. This is kept
  separate from `curation.yaml` on purpose: type answers "what is this filer",
  curation answers "do I want to show it". They meet in exactly one place —
  `curation.screen_predicate()` — so all ~8 query call sites inherit both rules
  with no edits, and a force-`include` always wins over a firm-type exclusion (R3).
- **One predicate, three tables denormalized:** `filer_type` is mirrored onto
  `funds`, `filings` and `quarter_screen` (R5). Mild denormalization, but it lets
  the "shown" rule be one SQL clause (`COALESCE(f.filer_type,'') NOT IN (...)`)
  instead of a join in every query. `COALESCE(...,'')` means a NULL type (a row
  not yet re-screened) is treated as *not excluded* — shown, never silently
  dropped.
- **Audit trail answers "why isn't X shown?":** `quarter_screen.reject_reason`
  records the mechanical reason a filer failed (fixed vocabulary in
  `screener.reject_reason`: `confidential`, `aum_below_floor`,
  `below_min_holdings`, `mostly_etfs`, `too_many_holdings_for_weight`,
  `not_concentrated`, or `""` for passers). Firm-type and curation reasons are derived at query time
  (they depend on YAML the user can edit without re-screening);
  `curation.explain(conn, cik, quarter)` combines all three into one sentence.
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
floor AND meet at least one concentration measure, the weight branch now also
capped at `MAX_HOLDINGS_WEIGHTED`) and flags zero/negative holding values.

### Benchmark regression guard

`config/benchmark.yaml` is a labeled gold set: `must_pass` (famous concentrated
value managers that must always appear) and `must_exclude` (known non-managers
that must never appear). `evaluate_screen.py` is a **read-only** harness that runs
over the live DB and writes `data/audit/screen_audit.{json,md}`: the shown
universe with each filer's firm type and admitting branch, suspected false
positives (issuers < 3 or > 50, or an excluded firm type), and any benchmark
violations with the per-filer reason. Acceptance is encoded as five criteria
(100% must_pass shown, 0% must_exclude shown, false positives < 5%, no must_pass
hidden by a mechanical rule, agent sign-off). `tests/test_benchmark.py` turns the
first four into a regression test that **skips** when `data/13f.db` is absent (so
the offline suite still passes) or when the DB hasn't been re-screened yet with
the firm-type columns.

---

## 9. Phone app (PWA)

The website is also a **Progressive Web App** — installable on an iPhone/Android
home screen, no App Store, no Apple Developer account. Three pieces make it work,
all generated into the published `site/`:

- **`web/static/manifest.webmanifest`** — app name, icons, theme colour,
  `display: standalone`. Copied to the **site root** at build time.
- **`web/static/sw.js`** — a service worker (also at site root, so its scope
  covers `/funds/*`). Network-first for pages (fresh data), cache-first for
  assets, with offline fallback.
- **`make_icons.py`** — regenerates the `icon-*.png` / `apple-touch-icon.png`
  set from the brand colours (navy + emerald "VF"). Re-run if the brand changes.

`web/templates/base.html` adds the `<link rel="manifest">`, Apple home-screen
meta tags, and the service-worker registration (`{{ root }}sw.js`, scoped to
`{{ root }}` so it works from both root and `/funds/` pages).

**If you later want a real App Store app**, the clean path is a native SwiftUI
client that reads a JSON feed emitted from this same database — the Python
pipeline stays the single source of truth either way.
