# User Guide — 13F Fund Tracker ("Value Flow")

A plain-English manual for **using and maintaining** this project. No coding
background assumed. If you only read one file, read this one.

> For the deeper "how it's built" details, see `ARCHITECTURE.md`.
> For the quick install/run steps, see `README.md`.

---

## 1. What this is

Every quarter, large investment managers must tell the SEC what U.S. stocks they
own. These public reports are called **13F filings**. This project:

1. **Downloads** those filings from the SEC (for free).
2. **Keeps only the managers you care about** — big, focused "value" investors.
3. **Stores** them in a small database file.
4. **Shows** them two ways:
   - a **website** anyone can visit (and install on a phone like an app), and
   - a **local dashboard** on your own computer for deeper digging.

Everything is Python and runs on your Mac. The website is free to host on GitHub.

### Who gets included (the "screen")

A manager makes the list for a quarter when:

> **Portfolio over $2 billion** **AND** ( **30 or fewer different companies**
> **OR** ( **its 10 biggest positions are at least 80% of the portfolio**
> **AND** it holds **50 or fewer companies** ) )

In plain terms: **big and concentrated** — managers who bet meaningfully on a
handful of names, not index-huggers who own a little of everything. The "50 or
fewer" cap on the concentration test keeps out giant mutual-fund / index
complexes that happen to be top-heavy but actually own hundreds of names. You can
change these numbers any time (see §4).

On top of the numbers, the project also **tags each filer's type** and hides the
kinds that aren't fundamental, concentrated *fund managers*: market-makers,
operating/holding companies (corporations reporting strategic stakes), sovereign
wealth funds / central banks / pensions, and banks/insurers. **PE/VC firms and
foundations/endowments are kept** — some run genuinely concentrated books. It also
drops **passive ETF baskets** (a filer holding mostly iShares/Vanguard index
funds is parking cash, not picking stocks). These catch the cases numbers alone
miss. You can correct any tag (see §4-C2).

---

## 2. The two ways to view the data

| | **Website** (static site) | **Dashboard** (Streamlit) |
|---|---|---|
| Who it's for | Anyone, anywhere | Just you, on your Mac |
| Where it lives | Online (GitHub Pages) + phone | Your computer only |
| How to open | Visit the URL | `streamlit run app.py` |
| Updates | Automatically each quarter | When you run it |
| Best for | Browsing, sharing, phone | Slicing, filtering, exploring |

Both read from the **same database** (`data/13f.db`). The website is the public,
polished face; the dashboard is your private workshop.

---

## 3. The mental model (important)

There are **three layers**, and keeping them separate is what makes this easy to
manage:

1. **The raw filings** — exactly what the SEC published. Never edited.
2. **The screen (the rule)** — a mechanical pass/fail applied to every filing.
   The result, plus a short **reject reason** for non-passers, is recorded in the
   database and is your **audit trail**: it never gets hand-edited.
3. **Your overlays (your judgment)** — two separate, hand-editable layers on top
   of the screen:
   - **Firm type** — a *fact* about the filer (manager, market-maker, mutual-fund
     complex, holding company…). Guessed from the name, correctable per-CIK.
     Excluded types are hidden.
   - **Curation** — an *editorial* decision: *hide this firm*, *always show that
     one*. A force-include here beats every exclusion.

Everything combines into **one rule for "shown"**, so your opinions never corrupt
the algorithm's record. You control these layers by editing **plain text files**
in the `config/` folder — you never have to touch the Python code day to day.

Whenever you want to know *why* a particular manager is or isn't shown, the
project can print the answer for you (see §6, the audit report).

---

## 4. How to make updates

There are four kinds of update. Each is simple.

### A) Add the newest quarter of data

13F filings appear about 45 days after a quarter ends (mid-Feb, May, Aug, Nov).

**The automatic way (nothing to do):** a GitHub robot wakes up a few times around
each deadline, pulls the new quarter, rebuilds the website, and republishes it.
You can also trigger it by hand: GitHub repo → **Actions** tab → **"Update 13F
site"** → **Run workflow**.

**The manual way (on your Mac):**
```bash
python3 ingest.py --backfill 1      # download the latest quarter
python3 rebuild_universe.py         # re-screen + fill in each manager's history
python3 build_site.py               # rebuild the ./site website folder
```
Then commit and push (see §5).

### B) Change the screening rules

Edit **`config/screen.yaml`**. It looks like this:
```yaml
min_aum_usd: 2000000000      # portfolio must be over $2B (no commas!)
max_holdings: 30             # "concentrated" test #1: at most 30 companies
max_holdings_weighted: 50    # "concentrated" test #2 also caps total companies at 50
min_holdings: 3              # ignore filers with fewer than this many companies
top_n: 10                    # "concentrated" test #2 looks at the 10 biggest...
top_n_min_pct: 80.0          # ...and they must be >= 80% of the portfolio
max_etf_pct: 50.0            # drop filers with >= 50% of AUM in index ETFs
```
Change a number, then re-screen everything:
```bash
python3 rebuild_universe.py
python3 build_site.py
```
You can edit this file **directly on GitHub** (open the file → pencil icon →
Commit). The robot will republish with the new rules.

### C) Hide or force-add a specific manager

Edit **`config/curation.yaml`**:
```yaml
exclude:
  - cik: 102909
    name: Vanguard Group
    reason: index funds, not a concentrated value manager

include:
  - cik: 1067983
    name: Berkshire Hathaway
    reason: flagship value manager, always show
```
- **`exclude`** hides a manager that technically passes but you don't want shown.
  This takes effect the **instant** you rebuild the site — no SEC download needed:
  ```bash
  python3 build_site.py
  ```
- **`include`** force-tracks a manager that *doesn't* pass the screen. Because we
  only store passing managers' data, you must load its holdings first:
  ```bash
  python3 rebuild_universe.py
  python3 build_site.py
  ```

**Finding a CIK:** it's the manager's numeric SEC id. Open the manager on your
site or on SEC EDGAR — the number in the address bar is the CIK. Leading zeros
don't matter (`1067983` and `0001067983` are the same).

### C2) Fix a filer's *type* (or exclude a whole category)

The project guesses each filer's type from its name. When the guess is wrong — a
holding company that reports one big stake slips in, or a mutual-fund complex
sneaks through — correct it in **`config/firm_types.yaml`**:
```yaml
overrides:
  - cik: 316011
    type: Holding Company        # force this filer's type
    reason: endowment holding a single strategic stake

excluded_types:                   # which types are hidden from the site
  - Market Maker / Broker
  - Operating Company             # corporations holding strategic stakes
  - Holding Company
  - Pension / Sovereign           # sovereign funds, central banks, pensions
  - Bank / Insurance
```
(PE/VC and Foundation/Endowment are deliberately *not* listed, so they stay
shown.) A passive-ETF guard in `screen.yaml` (`max_etf_pct`, default 50%) hides
filers holding mostly index ETFs even when their type looks fine.
The valid `type` values are: `Investment Manager`, `Market Maker / Broker`,
`Mutual Fund / Advisor Complex`, `Holding Company`, `Pension / Sovereign`,
`Foundation / Endowment`, `Bank / Insurance`. A type only **hides** a filer if it
appears under `excluded_types`. Then re-screen so the tags are stored:
```bash
python3 rebuild_universe.py
python3 build_site.py
```
> A force-`include` in `curation.yaml` always wins — if you both exclude a type
> and force-include a specific CIK of that type, the CIK is shown.

### D) Trim the database to specific quarters

If old or unwanted quarters sneak in:
```bash
python3 prune_quarters.py --keep 2025-Q1 2025-Q2 2025-Q3 2025-Q4 2026-Q1
python3 prune_quarters.py --keep 2026-Q1 --dry-run     # preview only, changes nothing
```

---

## 5. Saving and publishing your changes (git)

Your edits only go live after you **commit** (save a snapshot) and **push** (send
it to GitHub). After any change above:

```bash
git add -A                                   # stage everything you changed
git commit -m "Describe what you changed"    # save a snapshot
git push                                     # send it to GitHub → site republishes
```

Why this matters: every change is a dated, labeled snapshot you can look back on
or undo. Your `config/` edits give you a **full history of every rule change and
every firm you hid or added, and why** — that's the "reason" line.

> Tip: you can do all of this without the command line. Editing the `config/*.yaml`
> files on GitHub's website *is* a commit, and the robot republishes for you.

---

## 6. Checking things are healthy

```bash
python3 ingest.py --stats     # how many managers / quarters are loaded
python3 ingest.py --check     # automatic data-quality checks
python3 -m unittest discover -s tests   # run the test suite (should say "OK")
```

A few known, harmless `--check` notes: some SEC filings list a holding with a
zero or blank value. Those are flagged but don't break anything.

### The audit report — "why is this manager (not) shown?"

```bash
python3 evaluate_screen.py
```
This reads the database (it changes nothing) and writes a report to
**`data/audit/screen_audit.md`** (plus a `.json` for tools). Open the markdown to
see, for the latest quarter:

- the **shown universe** — count, total AUM, each manager with its firm type and
  which test let it in;
- **suspected false positives** — anything that looks off (fewer than 3 or more
  than 50 companies, or an excluded firm type still showing);
- **benchmark violations** — the project ships two lists in
  `config/benchmark.yaml`: **must-pass** (famous concentrated value managers that
  should always appear, e.g. Pershing Square, ValueAct, Akre) and **must-exclude**
  (known non-managers that should never appear, e.g. Lilly Endowment, Vanguard
  Advisers, a market-maker). The report flags any must-pass that's hidden or
  must-exclude that's shown, **with the exact reason** — so you can fix the right
  knob (a threshold, a firm-type override, or a curation entry).

Think of `benchmark.yaml` as a safety net: if a future rule change accidentally
drops a great manager or lets a junk filer back in, the report (and the test
suite) tells you immediately.

---

## 7. A few real-world quirks (already handled for you)

- **Quarter labels follow the *holdings* date,** the way analysts talk
  ("2025-Q1 holdings"), even though the filing arrives ~45 days later.
- **Dollar units changed in 2023:** older filings reported values in thousands,
  newer ones in whole dollars. The app normalizes both — you don't have to.
- **Amendments supersede originals:** if a manager refiles (a `13F-HR/A`), the
  newer version is shown.
- **Be polite to the SEC:** downloads are intentionally slow (capped well under
  the SEC's rate limit). A full quarter scans thousands of filings.

---

## 8. Quick reference (cheat sheet)

| I want to... | Do this |
|---|---|
| See the data privately | `streamlit run app.py` |
| Add the newest quarter | `python3 ingest.py --backfill 1` → `python3 rebuild_universe.py` → `python3 build_site.py` |
| Change the screen rules | edit `config/screen.yaml` → `python3 rebuild_universe.py` → `python3 build_site.py` |
| Hide a manager | add CIK to `exclude` in `config/curation.yaml` → `python3 build_site.py` |
| Force-add a manager | add CIK to `include` in `config/curation.yaml` → `python3 rebuild_universe.py` → `python3 build_site.py` |
| Fix a filer's type | edit `config/firm_types.yaml` → `python3 rebuild_universe.py` → `python3 build_site.py` |
| See why X is/isn't shown | `python3 evaluate_screen.py` → open `data/audit/screen_audit.md` |
| Publish changes | `git add -A` → `git commit -m "..."` → `git push` |
| Preview the site locally | `python3 -m http.server 8620 --directory site` then open http://localhost:8620 |
| Check health | `python3 ingest.py --stats` / `--check` |

---

## 9. Where things live (one glance)

```
config/screen.yaml      ← the screening RULES (you edit this)
config/curation.yaml    ← your exclude/include OVERRIDES (you edit this)
config/firm_types.yaml  ← per-CIK type corrections + excluded types (you edit this)
config/benchmark.yaml   ← must-pass / must-exclude safety-net lists (you edit this)
data/13f.db             ← the database (kept in git so the robot can update it)
data/audit/             ← the "why is X shown?" report (made by evaluate_screen.py)
ingest.py               ← load a quarter from the SEC
rebuild_universe.py     ← re-screen + backfill each manager's full history
evaluate_screen.py      ← read-only audit report + benchmark check
build_site.py           ← (re)build the website into ./site
app.py                  ← the private dashboard (streamlit run app.py)
.github/workflows/      ← the robot that auto-updates and republishes
```

That's the whole operating manual. For anything deeper, `ARCHITECTURE.md` has the
full design notes.
