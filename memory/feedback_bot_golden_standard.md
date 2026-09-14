---
name: feedback_bot_golden_standard
description: clawd-local bot is mission-critical — every change must be tested before push, no speculative commits
metadata:
  type: feedback
---

clawd-local is the single point of contact between Arto and all services. Treat every change to it as production-critical infrastructure, not a dev experiment.

**Why:** Arto stated this explicitly on 2026-08-31 after a series of stuck messages and forced restarts disrupted his workflow. The bot is the only channel to TLS, arbitrage, stock monitoring, and all other systems.

**How to apply:**
- Before committing any change to `main.py`, `agent.py`, `memory.py`, or `config.py`: run a local syntax check (`python3 -m py_compile`) and verify the bot starts cleanly (`launchctl kickstart -k gui/501/com.clawd.local` + confirm log shows "Bot started. Polling").
- Never push and assume it works — verify the bot actually responds to a test message after every restart.
- Draft → propose → get explicit approval → implement → test → push. No shortcutting the approval step for bot changes.
- Stale `--resume` session IDs cause slow responses; clear them after any major context change.
- Document what each commit changes in the commit message — not just "fix" but what specifically.
