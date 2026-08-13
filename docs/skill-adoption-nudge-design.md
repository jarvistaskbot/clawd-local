# Skill Adoption Nudge — Design Doc

**Status:** Draft for review
**Author:** Arto Mnatsakanyan (design assisted)
**Scope:** Track Claude Code skill usage across developer sessions; on check-in, detect whether the applicable skill was used and, if not, nudge the developer in-session toward the highest-rated matching skill.

---

## 1. Goal

Increase adoption of high-value Claude Code skills (`.claude/skills/<name>/SKILL.md`) by:

1. Observing which skills each developer actually used in a coding session.
2. On check-in (commit/PR), determining which skill(s) *should* have applied to the change.
3. When an applicable, higher-rated skill was **not** used, surfacing an in-session nudge recommending it.

Ratings are a blend of **developer ratings** and **usage-success** (outcomes of check-ins where the skill was used).

## 2. Non-goals

- Not a gate: nudges are advisory and never block a commit/PR.
- Not a surveillance tool: it tracks *skill usage signals*, not keystroke-level developer monitoring.
- Not auto-invoking skills on the developer's behalf (v1 recommends; the dev decides).

## 3. Definitions

- **Skill** — a `.claude/skills/<name>/SKILL.md` file with YAML frontmatter (`name`, `description`, trigger keywords) and a body of instructions.
- **Session** — one Claude Code working session, captured as a transcript (`*.jsonl`) by the tracking extension.
- **Check-in** — a git commit or PR that closes a unit of work.
- **Skill used** — the `Skill` tool was invoked with that skill's name during the session that produced the check-in.
- **Applicable skill** — a skill whose trigger/description matches the nature of the change.

## 4. Architecture

```
 dev's Claude Code session ──(extension tracks transcript .jsonl)──┐
                                                                   │
 git check-in (commit / PR) ───────────────────────────────────────┤
                                                                   ▼
                                     ┌────────────────────────────────────┐
                                     │  Skill Adoption Service              │
                                     │                                      │
   [A] Skill Registry  ────────────▶ │  1. skills_used(session)             │
   (catalog + ratings)               │  2. skills_applicable(change)        │
                                     │  3. gap = applicable − used          │
   [B] Usage/Outcome store ────────▶ │  4. rank gap by combined_rating      │
                                     │  5. if top gap ≥ threshold → nudge   │
                                     └───────────────┬──────────────────────┘
                                                     ▼
                                     in-session nudge to the developer
                                     ("Use <skill> — rated 4.6, 22% fewer
                                      review cycles. Load it?")
```

Two hard parts (everything else is plumbing): **[1] detecting a skill was used** and **[2] deciding which skill should apply**.

## 5. Components

### 5.1 Skill Registry

A catalog built from every `.claude/skills/*/SKILL.md` discovered across tracked repos, plus rating metadata.

Registry record (derived from frontmatter + computed):

| Field | Source | Notes |
|---|---|---|
| `skill_id` | slug of `name` | stable key |
| `name`, `description` | frontmatter | used for matching + display |
| `triggers[]` | frontmatter (or parsed from description) | keyword/patterns for matching |
| `paths[]`, `languages[]` | optional frontmatter | scope the skill to file types |
| `dev_rating` | computed | mean of explicit developer ratings |
| `dev_rating_n` | computed | number of ratings (confidence) |
| `success_score` | computed | outcome-based (see 5.4) |
| `success_n` | computed | sample size for cold-start handling |
| `combined_rating` | computed | see 5.4 formula |
| `active` | curated | allow deprecating a skill |

Suggested optional frontmatter extension (backwards compatible — ignored by Claude Code):

```yaml
---
name: code-review
description: Review a diff for correctness and simplification.
triggers: [review, diff, pr, correctness, refactor]
paths: ["**/*.py", "**/*.ts"]
category: quality
---
```

### 5.2 Skill-usage detection (part [1])

**Primary signal — transcript parse.** Each skill invocation emits a `Skill` tool call in the session `.jsonl`. The extension parses the transcript into events:

```
skill_usage_event { session_id, skill_id, ts, repo, author }
```

**Binding session → check-in — commit trailer.** At check-in, the extension writes a trailer into the commit message so the link is auditable in git history and survives outside the tracking DB:

```
Claude-Skills-Used: code-review, writing-skills
Claude-Session: 29593855-db3c-42ca-b6bd-90190744979e
```

Fallbacks if a trailer is absent: correlate by `(repo, author, time-window)` between the session's last activity and the commit timestamp.

### 5.3 Task → skill matching (part [2])

Given a change (diff, changed paths, languages, commit message / PR title), produce the set of **applicable** skills:

- **Tier 1 (cheap, deterministic):** match `triggers`, `paths`, `languages` against the change. Path/language filters prune fast; keyword hits on the message/diff propose candidates.
- **Tier 2 (fuzzy, optional):** embed the change summary and each skill `description`; take cosine-similar skills above a similarity floor. Use a small LLM classifier only for ambiguous cases to control cost.

Output: `applicable_skills[]` with a match confidence per skill.

### 5.4 Rating model

```
combined = w_dev · norm(dev_rating) + w_success · norm(success_score)
```

- **`dev_rating`** — explicit developer rating (1–5), collected as a lightweight thumbs/stars prompt after a skill runs. `norm()` maps to 0–1.
- **`success_score`** — outcome of check-ins where the skill **was** used, over a rolling window. Candidate signals (pick 1–2):
  - merged with **≤1 review iteration** (low rework)
  - **CI green on first run**
  - **no revert within 7 days**
  - low **review-comment count** per changed LOC
  - **Recommended default:** `merged with ≤1 review iteration AND no 7-day revert` → binary success per check-in; `success_score = successes / total` (Wilson lower bound to be conservative on small samples).
- **Cold start:** if `success_n < N_min` (e.g. 20), set `w_success = 0` and rank on `dev_rating` alone; phase `w_success` in as samples accrue.
- **Default weights:** start **`w_dev = 0.5`, `w_success = 0.5`**, but effectively dev-weighted early via the cold-start rule. Revisit once each skill clears `N_min`.

Ranking uses `combined_rating`; ties broken by higher `success_n` (more evidence), then higher `dev_rating_n`.

### 5.5 Recommendation + nudge delivery

On check-in:

1. `used = skills_used(session)`
2. `applicable = skills_applicable(change)`
3. `gap = { s in applicable, active, s not in used }`
4. `candidate = argmax_{s in gap} combined_rating(s)`
5. if `combined_rating(candidate) ≥ NUDGE_THRESHOLD` and passes guardrails → deliver nudge in the active session.

Nudge copy (example):

> For changes like this, developers using **`code-review`** (rated 4.6, ~22% fewer review cycles) tend to land faster. Want me to load it? [Use it] [Not now] [Don't suggest for these changes]

**Guardrails (or developers will resent it):**
- Max **1 nudge per session per skill category**.
- Suppress a skill a developer explicitly **dismissed** ("Don't suggest…") — per developer, per category.
- Never block the check-in; the nudge is out-of-band and advisory.
- Global rate limit (e.g. ≤ N nudges/day/developer) to avoid fatigue.

## 6. Data model (illustrative)

```sql
skills(
  skill_id TEXT PRIMARY KEY, name TEXT, description TEXT,
  triggers JSON, paths JSON, languages JSON, category TEXT,
  active BOOLEAN, source_repo TEXT, updated_at TIMESTAMP
);

skill_ratings(              -- explicit developer ratings
  id INTEGER PK, skill_id TEXT, developer TEXT, stars INTEGER,
  session_id TEXT, created_at TIMESTAMP
);

skill_usage_events(         -- parsed from transcripts
  id INTEGER PK, session_id TEXT, skill_id TEXT, repo TEXT,
  developer TEXT, ts TIMESTAMP
);

checkin_events(             -- one per commit/PR
  checkin_id TEXT PK, repo TEXT, developer TEXT, session_id TEXT,
  changed_paths JSON, languages JSON, message TEXT, ts TIMESTAMP
);

checkin_skill_link(         -- applicable vs used, per check-in
  checkin_id TEXT, skill_id TEXT,
  applicable BOOLEAN, used BOOLEAN, match_confidence REAL
);

checkin_outcomes(           -- for success_score
  checkin_id TEXT PK, review_iterations INTEGER, ci_first_pass BOOLEAN,
  reverted_within_7d BOOLEAN, review_comments INTEGER, resolved_at TIMESTAMP
);

recommendations(            -- what we nudged + response
  id INTEGER PK, session_id TEXT, checkin_id TEXT, skill_id TEXT,
  combined_rating REAL, shown_at TIMESTAMP,
  response TEXT  -- used | dismissed | ignored
);
```

`combined_rating` / `success_score` are computed views/materializations over the above, refreshed on a schedule or on outcome resolution.

## 7. Check-in hook (pseudocode)

```python
def on_checkin(checkin):
    session = link_session(checkin)                 # trailer, else (repo,author,window)
    used = skills_used(session)                     # from skill_usage_events
    applicable = match_applicable(checkin)          # tier1 filters -> tier2 fuzzy
    record_links(checkin, applicable, used)         # checkin_skill_link
    gap = [s for s in applicable if s.active and s.id not in used]
    if not gap:
        return
    candidate = max(gap, key=lambda s: combined_rating(s))
    if combined_rating(candidate) >= NUDGE_THRESHOLD and guardrails_ok(session, candidate):
        deliver_nudge(session, candidate)
        log_recommendation(session, checkin, candidate)
```

## 8. Success-signal computation (pseudocode)

```python
def resolve_outcome(checkin):
    o = fetch_outcome(checkin)          # review iters, CI, revert@7d, comments
    success = (o.review_iterations <= 1) and (not o.reverted_within_7d)
    store_outcome(checkin, o, success)
    for s in skills_used_in(checkin):
        recompute_success_score(s)      # Wilson lower bound over rolling window
```

## 9. Privacy / consent

- Track **skill-usage signals and check-in outcomes**, not raw code or keystrokes, in the analytics store.
- Aggregate ratings; avoid exposing per-developer usage to peers.
- Make tracking opt-in / disclosed per team policy; provide a per-developer opt-out that still lets them use skills (just no telemetry).

## 10. Rollout (phased)

- **MVP (dev-rating only, no outcomes yet):**
  1. Skill Registry from `SKILL.md` frontmatter + manual/seed dev ratings.
  2. Skill-usage extractor (transcript parse + commit trailer).
  3. Check-in hook logging applicable-but-unused skills.
  4. Tier-1 keyword/path matcher.
  5. In-session nudge with guardrails.
- **Phase 2:** wire `checkin_outcomes`, compute `success_score`, blend into `combined_rating`, phase in `w_success`.
- **Phase 3:** Tier-2 embedding/LLM matcher for fuzzy cases; per-category dismissal learning.

## 11. Metrics for the feature itself

- Nudge → **accept rate** (`used / shown`) per skill and overall.
- Skill **adoption lift**: usage rate on matching check-ins, pre vs post.
- **Outcome delta**: review-iterations / revert-rate for check-ins that used a nudged skill vs comparable that didn't.
- **Fatigue guard**: dismissal rate, opt-out rate (watch for creep).

## 12. Open decisions to confirm

1. **Success signal:** default is `≤1 review iteration AND no 7-day revert`. Add CI-first-pass? Use review-comment density instead?
2. **Weights:** start `w_dev = w_success = 0.5` with cold-start dev-weighting — agreed, or lean dev-heavy longer?
3. **`NUDGE_THRESHOLD`** and `N_min` (min success samples before `w_success` engages).
4. **Nudge timing:** at the moment of check-in, or deferred to the next relevant point in the session?
5. **Extension host** (VS Code / JetBrains / other) — determines the nudge UI surface.

## 13. Risks

- **Bad matching → noisy nudges → fatigue.** Mitigation: conservative threshold, path/language pre-filters, guardrails, dismissal memory.
- **Gaming ratings.** Mitigation: outcome-based `success_score` is hard to fake; Wilson bound resists small-sample inflation.
- **Cold start.** Mitigation: dev-rating-only ranking until `N_min` outcomes accrue.
- **Session→check-in mislink.** Mitigation: prefer the commit trailer; time-window correlation only as fallback.
```
