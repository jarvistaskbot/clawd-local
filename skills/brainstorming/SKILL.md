---
name: brainstorming
description: Use before any creative or build work — new features, components, functionality, or behavior changes. Explores intent, requirements, and design before implementation.
---

# Brainstorming Ideas Into Designs

Turn a rough idea into a fully formed design through natural, collaborative dialogue —
one question at a time — then get explicit approval before any implementation.

This skill runs inside a Telegram chat. Each of your replies is one Telegram message.

<HARD-GATE>
Do NOT write code, scaffold, propose file diffs, or take any implementation action until
you have presented a design AND the user has explicitly approved it. This applies to EVERY
task regardless of perceived simplicity.
</HARD-GATE>

**Violating the letter of this gate is violating its spirit.** "It's basically approved",
"this part is trivial", and "I'll just sketch the code" are all violations.

## Anti-Pattern: "This Is Too Simple To Need A Design"

Every task goes through this process — a one-liner, a config change, all of them. "Simple"
tasks are where unexamined assumptions cause the most wasted work. The design can be short
(a few sentences), but you MUST present it and get approval.

## Process (in order)

1. **Explore context** — check relevant files, docs, recent commits, existing patterns.
2. **Assess scope first** — if the request spans multiple independent subsystems, say so and
   help decompose into sub-projects before refining details. Each sub-project gets its own
   design → plan cycle.
3. **Ask clarifying questions — ONE at a time.** Multiple choice preferred. Focus on purpose,
   constraints, and success criteria. Never send a wall of questions.
4. **Propose 2-3 approaches** with trade-offs. Lead with your recommendation and why.
5. **Present the design in sections**, each scaled to its complexity. Ask after each section
   whether it looks right. Cover: architecture, components, data flow, error handling, testing.
6. **On approval, write the design doc** to
   `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` in the working directory.
7. **Spec self-review** — scan for placeholders (TBD/TODO), internal contradictions, scope
   creep, and ambiguity. Fix inline.
8. **Ask the user to review the written spec** before going further.
9. **Terminal state:** offer to hand off to implementation planning. Do NOT start building
   yourself.

## One Question At A Time

- Only ONE question per message. If a topic needs more, break it into multiple turns.
- Prefer multiple-choice ("A / B / C") over open-ended when you can.
- Number your questions ("Q1 of ~4") so the user knows where they are.

## Design Principles

- **YAGNI ruthlessly** — remove unnecessary features from every design.
- **Explore alternatives** — always 2-3 approaches before settling.
- **Incremental validation** — approval after each section, not one giant dump at the end.
- **Isolation & clarity** — units with one clear purpose and well-defined interfaces.
- In existing codebases, follow established patterns; don't propose unrelated refactoring.

## Rationalization Table

| Excuse | Reality |
|--------|---------|
| "This is too simple to design" | Simple tasks hide the worst assumptions. Short design, still required. |
| "The user clearly wants me to just build it" | They want the outcome. A 3-line design costs seconds and prevents rework. |
| "I'll ask all my questions at once to save time" | Walls of questions get half-answered. One at a time converges faster. |
| "I already know the approach" | Then presenting it takes 20 seconds and confirms alignment. |
| "Approval was implied" | Implied ≠ explicit. Ask: "Approve this design?" and wait. |

## Red Flags — STOP

- You're about to write code and the user has not said "approved" / "yes, build it".
- You've asked three things in one message.
- You're proposing ONE approach without alternatives.
- You skipped straight to a solution without asking a single question.

All of these mean: stop, back up to the right step.
