# Project instructions for Claude Code

This is the 13F Fund Tracker ("Value Flow") — a Python + SQLite + Streamlit /
static-site project tracking concentrated value managers from SEC EDGAR 13F
filings. Design details: ARCHITECTURE.md. Plain-English manual: USER_GUIDE.md.

## Working rules

- **Never commit or push unless explicitly asked.** The user reviews first.
  Pushing to main triggers the public site deploy.
- Screen criteria and curation are **config-as-data**: edit `config/*.yaml`
  (screen.yaml, firm_types.yaml, curation.yaml, benchmark.yaml), then re-run
  `python3 rebuild_universe.py`. Never weaken `config/benchmark.yaml` to make
  a check pass.
- `data/13f.db` is tracked in git on purpose; `data/raw/` (~12GB cache) is not.
- After data or config changes, the verification path is:
  `python3 -m unittest discover -s tests` → `python3 evaluate_screen.py` →
  `python3 build_site.py`.

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
