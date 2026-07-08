---
name: writing-skills
description: Use when creating new skills, editing existing skills, or verifying skills work before deployment
---

# Writing Skills

## Overview

**Writing skills IS Test-Driven Development applied to process documentation.**

You write test cases (pressure scenarios with subagents), watch them fail (baseline
behavior), write the skill (documentation), watch tests pass (agents comply), and
refactor (close loopholes).

**Core principle:** If you didn't watch an agent fail without the skill, you don't know
if the skill teaches the right thing.

## What is a Skill?

A **skill** is a reference guide for proven techniques, patterns, or tools. Skills help
future agents find and apply effective approaches.

**Skills are:** Reusable techniques, patterns, tools, reference guides
**Skills are NOT:** Narratives about how you solved a problem once

## TDD Mapping for Skills

| TDD Concept | Skill Creation |
|-------------|----------------|
| Test case | Pressure scenario with subagent |
| Production code | Skill document (SKILL.md) |
| Test fails (RED) | Agent violates rule without skill (baseline) |
| Test passes (GREEN) | Agent complies with skill present |
| Refactor | Close loopholes while maintaining compliance |
| Write test first | Run baseline scenario BEFORE writing skill |
| Watch it fail | Document exact rationalizations agent uses |
| Minimal code | Write skill addressing those specific violations |
| Watch it pass | Verify agent now complies |
| Refactor cycle | Find new rationalizations → plug → re-verify |

## When to Create a Skill

**Create when:**
- Technique wasn't intuitively obvious
- You'd reference this again across projects
- Pattern applies broadly (not project-specific)

**Don't create for:**
- One-off solutions
- Standard practices well-documented elsewhere
- Project-specific conventions (put in your instructions file)
- Mechanical constraints (if enforceable with regex/validation, automate it)

## SKILL.md Structure

**Frontmatter (YAML):** two required fields, `name` and `description` (max 1024 chars total).
- `name`: letters, numbers, hyphens only.
- `description`: third-person, describes ONLY *when to use* (NOT what it does). Start with
  "Use when...". NEVER summarize the skill's workflow — agents that see a workflow summary
  in the description follow it instead of reading the body.

```markdown
---
name: skill-name-with-hyphens
description: Use when [specific triggering conditions and symptoms]
---

# Skill Name

## Overview
What is this? Core principle in 1-2 sentences.

## When to Use
Bullet list with SYMPTOMS and use cases. When NOT to use.

## Core Pattern
Before/after code comparison (for techniques/patterns).

## Quick Reference
Table or bullets for scanning.

## Common Mistakes
What goes wrong + fixes.
```

## Skill Discovery Optimization

1. **Rich description** — answers "should I read this skill right now?". Triggering
   conditions only, no workflow summary.
2. **Keyword coverage** — error messages, symptoms, synonyms, tool names an agent greps for.
3. **Descriptive naming** — active voice, verb-first (`creating-skills` not `skill-creation`).
4. **Token efficiency** — frequently-loaded skills < 200 words; others < 500. Move detail
   to `--help` and cross-references. Do NOT force-load other skills with `@` links.

## Match the Form to the Failure

Classify the baseline failure before writing guidance.

| Baseline failure | Right form | Wrong form |
|---|---|---|
| Skips/violates a rule under pressure | Prohibition + rationalization table + red flags | Soft guidance ("prefer...", "consider...") |
| Complies but output has wrong shape | Positive recipe: state what the output IS, its parts in order | Prohibition list ("don't restate", "never narrate") |
| Omits a required element | Structural: REQUIRED field/slot in the template | Prose reminders near the template |
| Behavior should depend on a condition | Conditional keyed to an observable predicate | Unconditional rule + exemption clauses |

Prohibitions backfire on shaping problems — a recipe leaves nothing to negotiate. No nuance
clauses ("don't X unless it matters" reopens the negotiation). Exemption clauses don't scope.

## Bulletproofing Against Rationalization

For discipline skills (rules an agent knows but skips under pressure):

- **Close every loophole explicitly** — don't just state the rule, forbid the specific
  workarounds ("Don't keep it as reference. Don't adapt it. Delete means delete.").
- **Address spirit-vs-letter** — "Violating the letter of the rules is violating the spirit."
- **Rationalization table** — every excuse from baseline testing goes in, with the reality.
- **Red flags list** — make self-checking easy ("Code before test → STOP, start over").

## The Iron Law

```
NO SKILL WITHOUT A FAILING TEST FIRST
```

Applies to NEW skills AND EDITS. Write skill before testing? Delete it. Start over.
No exceptions — not for "simple additions", not for "documentation updates".

## RED-GREEN-REFACTOR for Skills

- **RED:** Run pressure scenario WITHOUT the skill. Document exact behavior and
  rationalizations verbatim.
- **GREEN:** Write minimal skill addressing those specific rationalizations. Re-run — agent
  should comply.
- **REFACTOR:** New rationalization appears? Add explicit counter. Re-test until bulletproof.

**Micro-test wording first:** one fresh-context sample per variant, always include a
no-guidance control, 5+ reps, read every flagged match manually, treat variance as a metric.

## Anti-Patterns

- Narrative example ("In session 2025-10-03 we found...") — too specific, not reusable.
- Multi-language dilution (example-js, example-py, example-go) — one excellent example wins.
- Code in flowcharts — can't copy-paste.
- Generic labels (helper1, step3) — labels need semantic meaning.

## Skill Creation Checklist

**RED:** Create pressure scenarios → run WITHOUT skill → document baseline → find patterns.
**GREEN:** name (hyphens only) → YAML frontmatter → "Use when..." description, third person
→ keywords → core principle → address baseline failures → form matches failure type → one
excellent example → run WITH skill, verify compliance.
**REFACTOR:** identify new rationalizations → add counters → build rationalization table →
red flags list → re-test until bulletproof.

## The Bottom Line

Creating skills IS TDD for process documentation. Same Iron Law (no skill without failing
test first), same cycle (RED → GREEN → REFACTOR). If you follow TDD for code, follow it for
skills.
