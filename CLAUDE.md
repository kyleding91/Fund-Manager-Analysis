# Project instructions for Claude Code

This is the 13F Fund Tracker ("Value Flow") — a Python + SQLite + Streamlit /
static-site project tracking concentrated value managers from SEC EDGAR 13F
filings. Design details: ARCHITECTURE.md. Plain-English manual: USER_GUIDE.md.
**Selection methodology (canonical): SCREENING.md** — read it before touching
any screen/roster/curation logic, and keep it updated when that logic changes.

## Working rules

- **Never commit or push unless explicitly asked.** The user reviews first.
  Note: pushing alone does NOT redeploy the public site — publishing happens
  via the "Update 13F site" workflow (scheduled quarterly, or run manually
  from the GitHub Actions tab). Treat triggering that workflow as a production
  deploy: only on the user's explicit request.
- Screen criteria and curation are **config-as-data**: edit `config/*.yaml`
  (screen.yaml, firm_types.yaml, curation.yaml, benchmark.yaml), then re-run
  `python3 rebuild_universe.py`. Never weaken `config/benchmark.yaml` to make
  a check pass.
- The universe is a **sticky roster** (`config/roster.yaml`): qualifiers join
  automatically; **never remove a member yourself** — lapsed members are kept
  and flagged for the user's review; only the user marks `status: removed`
  (with a reason). Never auto-re-add a removed member.
- `data/13f.db` is tracked in git on purpose; `data/raw/` (~12GB cache) is not.
- After data or config changes, the verification path is:
  `python3 -m unittest discover -s tests` → `python3 evaluate_screen.py` →
  `python3 build_site.py`.
- **The site is bilingual — Chinese (default, site root) + English (/en/).**
  Every visitor-facing string lives in `src/i18n.py` as an en/zh pair; templates
  must use `t('key')` and NEVER hardcode display text. When adding or changing
  site copy, update BOTH languages in the same edit (a missing key fails the
  build — that's intentional). Company/manager names, quarter labels, and
  financial terms (13F, AUM, ETF, CUSIP) stay in English in both versions.

## Learning capture (important)

The user is **learning Claude Code itself** while building this project and
keeps a notebook at **LEARNINGS.md** (best practices + dated log + open
questions).

- When the user says **"log that"** (or similar), append a dated entry to the
  *Learning log* section, newest first, matching the existing format
  (Context / Learning).
- Also **offer** to log proactively when something notable happens: a
  misconception gets corrected, a Claude Code feature is discovered or found
  unavailable, or a workflow pattern clearly works well. Offer briefly; don't
  interrupt the main task.
- Periodic tidy-up is delegated to the `learning-curator` subagent
  (.claude/agents/learning-curator.md) — suggest running it when the log has
  grown by ~10 entries.
