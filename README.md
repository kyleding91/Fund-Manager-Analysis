# 📈 13F Fund Tracker

A small, all-local app that downloads quarterly **13F filings** from the SEC,
keeps only **value-oriented, concentrated managers**
(**AUM > $2 billion AND (≤ 30 holdings OR (top-10 positions ≥ 80% of AUM AND
≤ 50 holdings))**), stores them in a database, and lets you explore the holdings
and quarter-over-quarter changes in your browser.

It also **tags each filer's type** (genuine manager, market-maker, mutual-fund
complex, holding company…), keeps a **sticky membership roster** (qualify once,
stay until a human removes you), and records **why every filer is or isn't
shown** — so the curated universe stays honest and reviewable.

**→ The complete selection methodology is documented in [SCREENING.md](SCREENING.md).**

Everything is Python and runs on your own Mac — no accounts, servers, or fees.

---

## 1. One-time setup

Open the **Terminal** app, then copy-paste these two lines (one at a time):

```bash
cd "/Users/xuehui/Fund Manager Analysis"
pip3 install -r requirements.txt
```

That installs the libraries the app needs. You only do this once.

---

## 2. Load some data

The tool talks to the SEC for you. Pick **one** of these:

```bash
# Quick first try — stops after 15 funds pass the screen (a couple of minutes):
python3 ingest.py --quarter 2025Q1 --max-passes 15

# A full quarter (all funds that pass — takes ~20-30 min, it's polite to the SEC):
python3 ingest.py --quarter 2025Q1

# The last 4 available quarters at once (best for the change-over-time views):
python3 ingest.py --backfill 4
```

`2025Q1` means **holdings as of March 31, 2025**. (The app figures out which SEC
filing window that corresponds to.)

Check what you have, or look for data problems, any time:

```bash
python3 ingest.py --stats     # how many funds / quarters are loaded
python3 ingest.py --check     # runs automatic data-quality checks
```

---

## 3. Open the dashboard

```bash
streamlit run app.py
```

Your browser opens automatically. You'll see three tabs:

- **🏦 Funds** — every manager that passed the screen, sorted by size. Click one
  to see its full holdings, portfolio weights, and AUM over time. Use the sliders
  on the left to filter.
- **🔎 Find a stock** — type a company name to see which managers own it.
- **💡 Insights** — most widely-held stocks, the most concentrated portfolios,
  managers newly entering the screen, and quarter-over-quarter buys/sells.

To stop the dashboard, go back to Terminal and press `Ctrl + C`.

---

## How it works (the short version)

1. **Download** — `src/edgar_client.py` pulls the SEC's quarterly filing index
   and each fund's filing (cached under `data/raw/` so it's only fetched once).
2. **Parse** — `src/parser.py` reads the cover page (manager, period) and the
   holdings table (company, value, shares).
3. **Screen** — `src/screener.py` normalizes the numbers and keeps funds with
   AUM > $2B that are concentrated by either measure: ≤ 30 distinct companies,
   or top-10 positions ≥ 80% of AUM *and* no more than 50 companies (the holdings
   ceiling keeps long-tail index/mutual-fund complexes out). It also records a
   short **reject reason** for every filer that doesn't pass.
4. **Classify** — `src/classify.py` tags each filer's type from its name (plus
   per-CIK overrides in `config/firm_types.yaml`). Excluded types — market-makers
   by default — are hidden even if they pass the numbers.
5. **Store** — `src/database.py` saves passing funds into `data/13f.db` (SQLite),
   and logs every filer's screen result, firm type and reject reason per quarter
   in the `quarter_screen` table.
6. **Explore** — `app.py` (the dashboard) and `src/insights.py` read that database.

To make each manager's deep-dive show a continuous history, `rebuild_universe.py`
re-screens the tracked quarters and backfills the holdings of every qualifying
manager across all of them (even quarters where it briefly dropped below the
screen). Run it after loading new quarters: `python rebuild_universe.py`.

A couple of real-world details handled for you:

- **Quarter labels** follow the *holdings* date, the way analysts think
  ("2025-Q1 holdings"), not the filing date.
- **Units**: before 2023 the SEC reported values in thousands; after, in whole
  dollars. The app normalizes both to whole dollars.
- **Amendments** (`13F-HR/A`) automatically supersede the original filing.

---

## Updating each quarter

13F filings appear ~45 days after a quarter ends. To add the newest quarter:

```bash
python3 ingest.py --backfill 1
```

Re-running is safe — already-loaded filings are refreshed, not duplicated.

---

## Publishing it as a website

The project can generate a polished, public **website** (separate from the local
dashboard). It's a set of plain HTML files — fast, free to host, and works on
phones. Search, filtering and sorting still work in the browser.

The site is **bilingual**: Chinese by default, English under `/en/`, with a
language switcher on every page. All UI text lives in `src/i18n.py` as
side-by-side en/zh pairs (company names and financial terms stay in English).

It cross-links both ways: each **manager** has a deep-dive page (holdings +
quarter-over-quarter moves), and each **company** on the *Most-held stocks* page
links to a per-stock page showing every screened manager holding it, how each
position changed last quarter, who newly bought or exited, and the combined
position size + holder count over the last five quarters.

### Build it on your computer

```bash
python3 build_site.py          # writes the site into ./site
```

Then preview it locally:

```bash
python3 -m http.server 8620 --directory site
# open http://localhost:8620 in your browser
```

### Put it online for free (GitHub Pages)

This repo includes an automation that **rebuilds and republishes the site by
itself** a few times around each quarterly 13F deadline (mid Feb / May / Aug /
Nov). You set it up once:

1. **Create a GitHub account** (free) at <https://github.com> if you don't have one.
2. **Upload this project** to a new repository (GitHub's "Add file → Upload
   files", or the desktop app — no command line needed).
3. In the repo, open **Settings → Pages**, and under *Build and deployment* set
   **Source = GitHub Actions**.
4. That's it. The schedule in `.github/workflows/update-site.yml` takes over.
   To publish immediately, open the **Actions** tab, pick **"Update 13F site"**,
   and click **Run workflow**.

Your site will be live at `https://<your-username>.github.io/<repo-name>/`.

A few notes:

- The small database file (`data/13f.db`) is kept *in the repo* so the automation
  can add each new quarter to it without re-downloading years of filings. The
  large raw-filings cache (`data/raw/`) stays on your computer only.
- Optional: add a repo **secret** named `SEC_CONTACT_EMAIL` (Settings → Secrets
  and variables → Actions) to use your own contact address in the SEC requests.
  If you skip it, the default in `src/config.py` is used.

### Install it on your phone (no App Store needed)

The website is a **Progressive Web App (PWA)** — it can be added to your phone's
home screen and opens full-screen with its own icon, just like a native app, and
keeps working offline after the first visit.

- **iPhone (Safari):** open your site URL → tap **Share** → **Add to Home Screen**.
- **Android (Chrome):** open the site → menu **⋮** → **Install app** / **Add to
  Home screen**.

The app icon, name ("Value Flow"), colours, and offline caching come from
`web/static/manifest.webmanifest`, `web/static/sw.js`, and the icons generated by
`make_icons.py` (re-run that script if you change the brand). No Apple Developer
account or App Store submission is required.

---

## Project layout

```
Fund Manager Analysis/
├── app.py              # the dashboard (run with: streamlit run app.py)
├── ingest.py           # the data loader / checker (run with: python3 ingest.py ...)
├── build_site.py       # generates the public website into ./site
├── requirements.txt    # libraries to install
├── ROADMAP.md          # the project plan & phases
├── .github/workflows/  # the auto-update-and-publish automation
├── config/             # editable policy (all GitHub-web-editable):
│   │                   #   screen.yaml     — numeric criteria
│   │                   #   curation.yaml   — force exclude / include by CIK
│   │                   #   firm_types.yaml — per-CIK type overrides + excluded types
│   │                   #   roster.yaml     — sticky member registry (auto-joins; human removals)
│   │                   #   benchmark.yaml  — must-pass / must-exclude regression lists
├── evaluate_screen.py  # read-only audit: writes data/audit/ report + checks the benchmark
├── data/
│   ├── 13f.db          # your database (created on first load)
│   ├── audit/          # the screen audit report (JSON + markdown)
│   └── raw/            # cached filings from the SEC
├── src/                # the building blocks (client, parser, screener, db, insights, site_data)
├── web/                # website templates + styles (templates/, static/)
└── tests/              # automated tests  (run with: python3 -m unittest discover -s tests)
```

---

## Troubleshooting

- **"No database found"** in the dashboard → load a quarter first (step 2).
- **Downloads seem slow** → that's intentional; the app stays under the SEC's
  rate limit. A full quarter scans thousands of filings.
- **Want to change the screen** (e.g. $1B, or 40 holdings, or a different top-N
  concentration cutoff) → edit `config/screen.yaml` (`min_aum_usd`,
  `max_holdings`, `max_holdings_weighted`, `min_holdings`, `top_n`,
  `top_n_min_pct`, `max_etf_pct`), then re-run `python rebuild_universe.py`. You
  can edit it right in GitHub's web editor.
- **Want to hide or force-add a specific manager** → edit `config/curation.yaml`:
  add a CIK under `exclude:` to hide it (rebuild the site — no download needed),
  or under `include:` to track a manager that doesn't pass the screen (run
  `python rebuild_universe.py` first so its holdings get loaded).
- **A filer is mis-typed** (e.g. a holding company or mutual-fund complex slips
  in, or a genuine manager is wrongly excluded) → add its CIK under `overrides:`
  in `config/firm_types.yaml` with the correct `type`. To exclude a whole
  category, list it under `excluded_types:`. A force-`include:` in
  `curation.yaml` always wins over a firm-type exclusion.
- **Want to see why a manager is / isn't shown** → run `python3 evaluate_screen.py`
  and open `data/audit/screen_audit.md`. It lists the shown universe, suspected
  false positives, and any benchmark violations with the exact reason for each.
