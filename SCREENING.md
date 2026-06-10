# How managers are selected — the complete methodology

This is the canonical reference for **how a 13F filer ends up on (or off) the
Value Flow list**. The system has several layers that evolved for different
reasons; each is simple, but together they deserve a careful walkthrough.

> Quick links: thresholds live in [config/screen.yaml](config/screen.yaml) ·
> membership in [config/roster.yaml](config/roster.yaml) · firm types in
> [config/firm_types.yaml](config/firm_types.yaml) · manual overrides in
> [config/curation.yaml](config/curation.yaml) · the answer key in
> [config/benchmark.yaml](config/benchmark.yaml). Plain-English how-tos:
> [USER_GUIDE.md](USER_GUIDE.md). Code-level design: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. The goal, in one sentence

Surface **fundamentally-driven, concentrated value managers** — the
Pershing Squares, TCIs and Akres — and exclude everything else that files a
13F: index/mutual-fund complexes, market-making desks, corporations holding
strategic stakes, sovereigns, banks, and passive ETF baskets.

Two principles shape the whole design:

1. **The screen is an *admission test*, not a per-quarter filter.** A great
   manager having a soft quarter (AUM dips to $1.9B, or 31 holdings instead
   of 30) should not vanish from the list. Qualifying once gets you in;
   only a human decision gets you out.
2. **Facts, rules, and judgment are kept in separate layers**, each recorded
   in its own git-tracked file, and they combine in exactly **one** rule for
   "shown" — so the site, the dashboard, the audit, and the statistics can
   never disagree about who's in.

---

## 2. The decision pipeline

Every quarter, every 13F filing flows through this chain:

```
            SEC EDGAR filing (13F-HR / 13F-HR/A)
                          │
                          ▼
   ┌─ LAYER 1 · MECHANICAL SCREEN (src/screener.py) ──────────────┐
   │  Verdict recorded per filer per quarter with a reject reason │
   │  in the quarter_screen ledger — never hand-edited.           │
   └──────────────────────────────────────────────────────────────┘
                          │ qualifies?
                          ▼
   ┌─ LAYER 2 · FIRM TYPE (src/classify.py + firm_types.yaml) ────┐
   │  A FACT about the filer, from its name + per-CIK overrides.  │
   │  Five types are barred from membership and display.          │
   └──────────────────────────────────────────────────────────────┘
                          │ acceptable type?
                          ▼
   ┌─ LAYER 3 · MEMBERSHIP ROSTER (config/roster.yaml) ───────────┐
   │  STICKY: qualifiers auto-join; nobody auto-leaves. Members   │
   │  failing a later screen are flagged "lapsed" for review.     │
   │  Removal = a human edit, with a reason, tracked in git.      │
   └──────────────────────────────────────────────────────────────┘
                          │ active member?
                          ▼
   ┌─ LAYER 4 · CURATION (config/curation.yaml) ──────────────────┐
   │  Editorial overrides: exclude hides anyone; include WINS     │
   │  over every exclusion (the emergency switch, used sparingly).│
   └──────────────────────────────────────────────────────────────┘
                          │
                          ▼
                     SHOWN on the site
```

The four layers compress into one SQL predicate
(`src/curation.py::screen_predicate`), used by every query in the project:

```
shown  =  cik IN curation-include
          OR (    cik IN active-roster-members
              AND cik NOT IN curation-exclude
              AND filer_type NOT IN excluded-types )
```

(If `config/roster.yaml` is absent — fresh checkout, offline tests — the
membership term falls back to the per-quarter mechanical verdict.)

### Layer 1 — the mechanical screen (admission test)

A filing **qualifies** when ALL of these hold
(thresholds from [config/screen.yaml](config/screen.yaml)):

| Test | Current value | Why it exists |
|---|---|---|
| Disclosed 13F assets | **> $2 billion** | big enough to matter |
| Distinct companies (floor) | **≥ 3** | drops 1–2-stock vehicles: corporations, PE funds, endowments reporting a single strategic stake |
| ETF / index-fund share of assets | **< 50%** | a mostly-ETF book is parked cash, not stock-picking — catches passive advisors, central banks, and trading desks that name-rules miss |
| Concentration, **either**: ≤ **30** companies | | the classic concentrated book |
| **or**: top-10 ≥ **80%** of assets **and** ≤ **50** companies | | catches a modest tail of small positions — the ≤ 50 cap keeps out 1,000-name fund complexes that are merely top-heavy |
| Not filed confidentially | | a filing with omitted holdings can't be assessed |

Companies are counted by **issuer** (first 6 CUSIP digits), so share classes
and listed options collapse into one position. Every filer scanned — pass or
fail — gets a row in the `quarter_screen` ledger with a fixed-vocabulary
**reject reason**: `aum_below_floor`, `below_min_holdings`, `mostly_etfs`,
`not_concentrated`, `too_many_holdings_for_weight`, `confidential`, or `""`
(qualified). This ledger is the permanent audit trail; it is never hand-edited.

### Layer 2 — firm type (a fact, not an opinion)

Every filer is tagged with what kind of institution it is, using a name
heuristic plus hand corrections in
[config/firm_types.yaml](config/firm_types.yaml) (the heuristic mis-reads
names in both directions — Toyota looks like a manager, Sequoia China looks
like an operating company).

**Barred types** (never join the roster, never shown):
`Market Maker / Broker` · `Operating Company` · `Holding Company` ·
`Pension / Sovereign` · `Bank / Insurance`.

**Kept deliberately:** `Investment Manager`, `Foundation / Endowment`
(some run genuinely concentrated books — Gates Foundation Trust), and
PE/VC firms (Carlyle, Sequoia) — concentrated post-IPO books count as
real conviction.

### Layer 3 — the membership roster (sticky, human-governed)

[config/roster.yaml](config/roster.yaml) lists every member with the quarter
it joined and how (`screen` = auto-qualified, `grandfathered` = the 40
near-miss managers admitted when the roster was created, `manual`).

- **Joining is automatic**: each quarterly rebuild adds filers that qualified
  in the new quarter and aren't a barred type or curation-excluded.
- **Nobody leaves automatically.** A member that fails the current quarter's
  screen is **lapsed**: still shown everywhere, but flagged — on the public
  *This quarter* page and in the audit report — with its lapse reason.
- **Removal is a human edit** (`status: removed` + `reason`), permanent in git.
  A removed member is never auto-re-added, even if it re-qualifies — so a
  removal is a real decision, not a tweak.

This is why the universe count (155 as of 2026-Q1: 115 currently qualifying
+ 40 lapsed) can exceed the number of filers passing the screen today.

### Layer 4 — curation (the emergency switches)

[config/curation.yaml](config/curation.yaml): `exclude` hides anyone
regardless of membership; `include` force-shows anyone and **wins over every
exclusion** — by design, so one explicit human call can always override the
machinery. Both are used sparingly; prefer fixing the right layer
(threshold → firm type → roster → curation, in that order).

---

## 3. Worked examples (real cases from 2026-Q1)

| Filer | What the layers say | Outcome |
|---|---|---|
| Berkshire Hathaway | qualifies (26 names, $263B) · Investment Manager · member | **Shown** |
| Appaloosa | fails (31 names — one over) · Investment Manager · grandfathered member | **Shown, flagged lapsed** |
| HBK Investments | fails (220 names) · Investment Manager · grandfathered member | **Shown, flagged lapsed** — review candidate for removal |
| Lilly Endowment | fails (1 name) · Holding Company (override) | **Hidden** (also on the must-exclude benchmark) |
| Matson Money | 6 names *but 83% ETFs* → `mostly_etfs` | **Hidden** — the ETF guard catches what name-rules miss |
| CTC LLC | $217B, top-10 86% — *looks* concentrated, but 69% ETFs | **Hidden** (a market-making desk) |
| Toyota Motor | name reads like a manager · Operating Company (override) | **Hidden** |
| SC US (Sequoia China) | name reads like an operating company · Investment Manager (override) | **Shown** |
| Vanguard Advisers | 208 names → fails the ≤ 50 weighted cap | **Hidden** (must-exclude benchmark) |

---

## 4. The quarterly lifecycle

**Automatic** (GitHub Actions, on the 16th/23rd/28th of Feb · May · Aug · Nov):

1. Ingest the new quarter — every filing parsed, screened, firm-typed, and
   recorded in the ledger.
2. New qualifiers **auto-join the roster** (the roster file is committed back).
3. Holdings history is backfilled for every member (including lapsed ones),
   and stored screen flags are re-synced from the ledger.
4. The site rebuilds and publishes.

**Human ritual** (a few minutes per quarter):

1. Open the **This quarter** page → *Membership changes*: sanity-check the new
   members; read the **lapsed** list and its reasons.
2. Keep a lapsed member → do nothing. Remove one → edit
   `config/roster.yaml` (`status: removed` + reason), rebuild.
3. Optionally run the audit (`python3 evaluate_screen.py`) or ask the
   *screen-auditor* agent "is the manager list clean?" for an independent
   judgment pass.

---

## 5. Guardrails — what keeps this honest over time

| Guardrail | What it protects against |
|---|---|
| [config/benchmark.yaml](config/benchmark.yaml): 14 **must-pass** + 24 **must-exclude** labeled answers | a future rule change silently dropping Pershing Square or letting Lilly Endowment back in |
| `evaluate_screen.py` (read-only audit → `data/audit/`) | reports benchmark violations, suspected false positives, and the lapsed-member review queue with reasons |
| `tests/test_benchmark.py` + 80 unit tests | every mechanical rule, the roster semantics (sticky shown / no auto-leave / removed stays removed), and the predicate shape are regression-tested |
| The `quarter_screen` ledger | "why isn't X shown?" is always answerable from data, for any quarter, forever |
| Everything in YAML + git | every threshold change and membership decision has an author, a date, and a diff |

Acceptance criteria (the audit's definition of "clean"): 100% of must-pass
shown · 0% of must-exclude shown · suspected false positives < 5% of shown ·
no must-pass hidden by a mechanical rule · independent agent sign-off.

---

## 6. How to change things

| You want to… | Edit… | Then run… |
|---|---|---|
| Loosen/tighten a numeric rule | `config/screen.yaml` | `python3 rebuild_universe.py` → `python3 evaluate_screen.py` |
| Fix a wrong firm type | `config/firm_types.yaml` (overrides) | same |
| Remove a member (with reason) | `config/roster.yaml` | `python3 build_site.py` |
| Force-show / force-hide one filer | `config/curation.yaml` | `python3 build_site.py` |
| Lock in a new known-good/bad example | `config/benchmark.yaml` (add only — never delete to make a check pass) | `python3 evaluate_screen.py` |

Fix-preference order when something looks wrong: **threshold → firm-type
override → roster decision → curation**. Broad fixes beat per-name fixes.

---

## 7. Honest limitations

- **13F data is partial and late**: long U.S.-listed positions only (no
  shorts, cash, or most non-U.S. listings), disclosed up to 45 days after
  quarter-end.
- **The name heuristic is approximate.** Per-CIK overrides correct known
  misses; brand-new junk filers can slip in until the quarterly audit/review
  catches them. The benchmark prevents *known* offenders from returning.
- **Money-flow estimates** on the This-quarter page derive from share-count
  changes × implied price; stock splits between quarters can distort a
  position's apparent change.
- **Lapsed members are shown without a badge** in the Managers directory
  (their own pages do mark sub-criteria quarters with ○). A directory badge
  is on the backlog.
- The quarterly automation currently publishes **without** running the audit
  as a deploy gate (parked as backlog item P0 in [ROADMAP.md](ROADMAP.md)).
