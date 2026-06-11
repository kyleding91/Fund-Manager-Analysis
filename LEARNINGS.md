# Claude Code — Learnings & Best Practices

My running notebook for getting better at Claude Code while building this
project. Three sections:

- **Best practices** — distilled, stable advice (curated from the log below).
- **Learning log** — raw entries, newest first. To add one, just tell Claude
  *"log that"* (or "add this to learnings") in any session.
- **Open questions** — things to figure out; Claude should try to answer these
  when relevant and move them up once answered.

The `learning-curator` subagent (.claude/agents/learning-curator.md) tidies
this file periodically — say "tidy the learnings file" when the log gets long.

---

## Best practices (distilled)

### Giving instructions
- **State the goal and the constraints, not the steps.** The screen-refinement
  task worked because the ask was "exclude these kinds of funds, but don't
  lose any true value manager" — Claude designed the how (benchmark lists,
  audit loop) around that.
- **Lock decisions early when asked.** When Claude offers options
  (multiple-choice questions), picking one is a *decision on record* — later
  work honors it (e.g. "keep PE firms" survived three rounds of tuning).
- **Encode decisions as tests/config, not chat.** Chat is forgotten; tests and
  YAML are forever. Our must-pass/must-exclude benchmark means no future
  change can silently break what we decided.

### Subagents
- **A subagent is a fresh worker, not an observer.** It sees only the prompt
  it's given — never the chat history. Use the main conversation for anything
  that needs context; use subagents for self-contained jobs.
- **Best use: independent verification.** A separate "skeptic" agent reviewing
  the main agent's output catches what mechanical checks miss (ours found
  ETF-basket funds and mis-tagged managers the screen criteria passed).
- **Write the `description` line carefully** — it's what makes Claude delegate
  to the agent automatically. Bake guardrails into the agent file itself
  ("read-only", "never edit the benchmark", "never push").

### Project setup
- **CLAUDE.md is the only file read every session.** Standing instructions
  ("never commit unless asked", "offer to log learnings") belong there, not in
  chat. Chat instructions die with the session.
- **Put policy in config files, not code.** Screen thresholds, firm-type
  overrides and curation lists live in `config/*.yaml` — editable on GitHub's
  web editor, versioned, and Claude can tune them without touching Python.

### Working style
- **Review-then-commit beats auto-commit.** Claude does the work; nothing is
  saved to git history until you say "commit". You always get a review point.
- **Long jobs vs. laptop lids.** Closing the lid sleeps the Mac and
  kills/pauses background work. Either run `caffeinate -s` (plugged in), or —
  better — ask whether the job can be made faster/resumable. (Our 10-minute
  re-screen became a seconds-long database recompute when interruptions made
  the slow way impractical.)
- **"Status?" is always safe to ask.** Claude re-checks the actual state
  (processes, files, git) rather than answering from memory.

---

## Learning log (newest first)

### 2026-06-10 — Claude can propose, but not approve, changes to its own instructions
**Context:** Claude found a factually wrong line in CLAUDE.md ("pushing
triggers the deploy") and edited the file — but when it tried to *commit* the
edit, the permission system blocked it as unrequested self-modification.
**Learning:** Changes to Claude's standing instruction file need a human
action to become permanent. Claude drafts; you ratify (saying "commit it" —
or, as happened here, clicking the app's commit button does the same thing).
That's the guardrail working, not a malfunction.

### 2026-06-10 — "Push" doesn't mean "publish" — and permissions know the difference
**Context:** Asked Claude to "push to GitHub" expecting the site to update.
Pushing succeeded but the site didn't change: publishing only happens via the
deploy workflow (scheduled quarterly, or run manually). When Claude tried to
trigger that workflow on its own, the permission system stopped it — a
production deploy needs the explicit words ("deploy the site").
**Learning:** Name the action you actually want — "push" authorizes pushing,
not deploying. Bonus: when the `gh` tool was missing, Claude still triggered
the deploy through the GitHub API using the stored git credentials — missing
tools rarely mean blocked, but consequential actions still wait for your word.

### 2026-06-10 — A parked risk became the live bug (and caches come in layers)
**Context:** We had parked backlog item P0 with the note "returning users can
see stale pages after a deploy." First real deploy: exactly that happened —
the homepage was new while the Managers page showed the months-old site
(service-worker cache + the CDN's ~10-minute HTTP cache, never invalidated).
**Learning:** When you and Claude *predict* a failure and park the fix, write
down what event makes it urgent — "first deploy" here. Fix was to stamp a
unique cache version into every build so deploys self-invalidate.

### 2026-06-10 — Ask for the data behind a decision before locking it
**Context:** Claude asked "who should be on the initial roster: 115 or 225?"
Instead of choosing, I asked to see WHY ~100 managers had dropped. The
generated review file revealed the "225" mixed in stray 2017–2020 data, and
the real decision was about ~40 names in two clean groups.
**Learning:** When Claude offers options on a bulk decision, ask it to produce
the underlying review artifact first. The options often change once the data
is on the table.

### 2026-06-10 — When a metric confuses, show the disclosed fact, not just the estimate
**Context:** The money-moves page led with "estimated net bought ($)" — which
felt confusing. Raw share-count ranking would have been worse (not comparable
across stocks). The fix: lead each row with the share-count change (the fact
straight from the filing, e.g. "+40.3M sh (+78%)"), keep the $ estimate as
context, and keep ranking by $.
**Learning:** Separate the *display* metric from the *ranking* metric. Lead
with the verifiable number; let the derived number support it.

### 2026-06-10 — Pattern: turn a filter into an admission test + a human-governed registry
**Context:** The screen kept evicting good managers over boundary noise ($1.9B
vs $2B). Rather than loosening thresholds, we made membership sticky: the
screen *admits*, a git-tracked roster file *remembers*, lapses are flagged for
review, and only a human removes (with a reason, never auto-re-added).
**Learning:** When a rule-based filter churns, don't tune the rule forever —
split "qualifies right now" from "belongs on the list," and put the second
under human control in a config file. Defaults should favor keeping; removal
should cost a sentence of justification.

### 2026-06-10 — /agents isn't available in the desktop app environment
**Context:** Tried the `/agents` interactive UI after reading it should exist.
**Learning:** In this desktop environment some slash commands aren't available.
Fallback that always works: ask Claude to create `.claude/agents/<name>.md`
files directly. File-created agents load on the next session restart.

### 2026-06-10 — Subagents can't see the conversation
**Context:** Wanted a subagent to "keep tracking" my learnings automatically.
**Learning:** Subagents receive only the prompt they're spawned with. Capture
must happen in the main chat ("log that"); a subagent fits the periodic
distill/curate step instead.

### 2026-06-09 — Verification agents as a quality gate
**Context:** Refining the fund screen; mechanical criteria all passed but the
universe still contained junk.
**Learning:** Spawning an independent agent told to *judge* the result (not
rebuild it) found ~25 false positives the rules missed. Pattern: build →
mechanical checks → adversarial agent review → human decision.

### 2026-06-09 — Benchmark files turn judgment into regression tests
**Context:** Worried that tuning screen rules would silently drop good managers.
**Learning:** A hand-labeled answer key (must-pass / must-exclude lists in
`config/benchmark.yaml`) plus a test that asserts it means every future rule
change is automatically checked against past judgment.

### 2026-06-09 — Sleep kills background work
**Context:** Closed the laptop lid during a 10-minute data rebuild; it died twice.
**Learning:** Lid close = sleep = paused/killed jobs. `caffeinate` helps, but
the durable fix was restructuring the job to be fast (recompute from stored
data instead of re-scanning files).

### 2026-06-08 — Plan mode for big changes
**Context:** The screen refinement touched 28 files.
**Learning:** For large changes, having Claude write a plan first (sections,
decisions flagged for approval) made the multi-hour execution predictable, and
the plan doubled as documentation of *why*.

---

## Open questions

- [ ] Can this project define custom **skills / slash commands** (e.g. a
      `/learn` shortcut for logging) that work in the desktop app, given
      `/agents` wasn't available?
- [ ] When is Claude's built-in **memory** (persists across sessions) the right
      place for knowledge vs. project files like this one? Current working
      rule: memory = Claude's private context; git-tracked .md = shared,
      reviewable knowledge.
