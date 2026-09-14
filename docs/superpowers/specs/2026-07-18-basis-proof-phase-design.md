# Basis Trading Bot — Proof Phase Design

Date: 2026-07-18
Status: Approved by Arto (Telegram, 2026-07-18)
Repo: artomnats/arbitrage-trading (local: /Users/openclaw/arbitrage-trading, VPS: root@76.13.209.1)

## 1. Objective

Decide, with hard evidence, whether the Bybit basis trading system deserves $10,000
of capital. Current state: ~$336 capital, real historical P&L approximately -$42
(DB previously claimed +$29 until fill-level audit corrected it). Funding arbitrage
is empirically dead at VIP0; basis (~2-3% per cycle, ~10-15% annualized) is the only
live edge.

Decision chain:

    audit + fix -> freeze -> 10-cycle proof -> pass -> re-audit -> Arto approval
    -> $2,500 stage -> 4 clean cycles -> $10,000

Capital never moves onto unaudited code. The proof never runs on unaudited code.
All capital movements require Arto's explicit "Execute this".

## 2. Proof Gate (the contract)

The system earns the $10k scale decision when ALL of the following hold, evaluated
from the locked ledger:

1. Cycles: >= 10 completed basis cycles (entry -> delivery settlement or verified
   early exit) between clock-start and 2026-10-01.
2. Accuracy: evaluated over the first 10 completed cycles — >= 8 of those 10 land
   within +/-20% of the net profit predicted at entry; no single cycle in the
   window worse than -50% of prediction. (Cycles completing after the 10th still
   log to the ledger but do not change the gate verdict.)
3. Integrity: zero unhedged incidents. No naked leg older than 5 minutes, verified
   against live Bybit positions (not the bot's own DB).
4. Scale check: for every real trade, a shadow simulation at $10k-proportional
   sizing against the live orderbook must show the net edge remains positive after
   simulated slippage at that depth.

Rationale for 8/10 rather than 10/10: at ~$50-100 positions a single noisy fill can
swing +/-20% without any systemic fault. The -50% floor still catches accounting
lies and structural failures.

### Failure definition

- Fewer than 10 completed cycles by 2026-10-01 (an edge that never fires is not an
  edge), OR
- Accuracy condition missed, OR
- Any integrity violation, OR
- Shadow verdicts show the edge dies at $10k sizing.

### Failure policy (agreed: one diagnosis round, then hard kill)

1. First failure: root-cause analysis (fees? fills? prediction model? frequency?)
   -> fixes -> gate re-runs ONCE from zero (fresh 10 cycles).
2. Second failure: hard kill. Bot stopped, positions closed at natural exits,
   Arto withdraws remaining capital, repo archived with post-mortem, all effort
   redirected to CheckoutGuard. Memory updated so the strategy is not resurrected
   without seeing the verdict. No appeals, no goalpost moves.

## 3. Pre-Proof Audit Phase (~1.5-2 weeks, before clock start)

Ordering rationale: fixing critical bugs mid-proof touches trading logic, which
resets the cycle counter under the freeze rules. Audit first so the proof runs on
hardened code and the result is trustworthy the first time.

Fixed checklist — nothing else enters this phase:

1. Full code audit of the basis strategy path (subagent deep-audit, same style as
   the 2026-04-03 audit that found the _entry_lock bug + 8 major issues). Scope:
   - entry math and threshold logic
   - fill handling (order placement -> get_order_fill_details -> DB write)
   - hedge sizing / delta neutrality enforcement
   - exit logic (delivery settlement + early exit)
   - fee and cost model vs current Bybit fee schedule
   - DB-vs-exchange consistency (every stored number traceable to exchange data)
   Deliverable: audit report, every issue classified critical / major / minor.
2. Fix all criticals and majors; each fix reviewed and tested before merge.
   Minors logged; fixed only if trivial. No scope creep.
3. PR #13 (early-exit redesign, 15 tests) reviewed as part of the audit — merge or
   explicitly reject BEFORE the freeze. Early exits materially increase cycle
   frequency and therefore protect the 10-cycles-by-October requirement.
4. Basis market scan: one-off script over current Bybit delivery contracts
   measuring how often opportunities clear the entry threshold. If fewer than ~2
   qualifying entries/week, widen the universe BEFORE clock start.
5. Deploy (standard process), freeze begins, clock starts. Target: ~2026-08-01.

## 4. Instrumentation

### 4.1 Prediction ledger (MongoDB collection: proof_ledger)

One document per cycle, written at three moments:

1. At entry (immutable after write): symbol/contract, entry timestamp, predicted
   net profit (USD), full cost breakdown used by the prediction (spot fee, perp
   fee, expected slippage, borrow), expected fill prices for both legs, basis % at
   entry, planned exit (delivery date or early-exit condition).
2. After fills confirm: actual fill prices/quantities from get_order_fill_details()
   (exchange execution history — the trusted path built after the April audit).
3. At close: realized net profit computed from Bybit execution history (never from
   bot-DB prices), accuracy ratio realized/predicted, pass/fail flag for the
   +/-20% band.

Key property: prediction is written before the trade; realized values come only
from exchange data. The two cannot contaminate each other — this specifically
prevents the -$42-real vs +$29-claimed failure mode.

### 4.2 Shadow logger (MongoDB collection: shadow_ledger)

At each real entry and close: snapshot of top ~20 orderbook levels on both legs,
then a simulated fill walking the book at $10k-proportional size (same 30% sizing
rule; e.g. a $100 real position on $336 capital simulates ~$3,000 on $10k).
Records simulated average fill price per leg, slippage vs top-of-book, and whether
the net edge survives. Pure logging; zero influence on real trading decisions.

Known limitation (accepted): shadow fills are snapshot simulations; they cannot
capture market impact or queue position of a real $3k order. They are an
upper-bound sanity check on depth, not a guarantee. The $2.5k staging step exists
precisely to cover this gap with real money before $10k.

### 4.3 Reporting

- Weekly Telegram scorecard (Sundays): cycles N/10, accuracy per closed cycle,
  worst cycle, shadow verdict per cycle, days remaining to Oct 1.
- Silent otherwise (Arto preference). Immediate Telegram alert only on integrity
  violation (naked leg > 5 minutes).

### 4.4 Integrity watchdog

5-minute loop comparing live Bybit positions against expected hedge pairs. Naked
leg > 5 minutes -> immediate Telegram alert + incident record in proof_ledger.

## 5. Build Plan

Branch: proof-phase. PR to main. Arto reviews. Development on Mac mini at
/Users/openclaw/arbitrage-trading (never /tmp clones).

- services/proof_ledger.py — record_entry_forecast(), record_fills(),
  record_close(), snapshot_orderbook(), simulate_fill_at_scale()
- Hooks at basis open/close call sites (3-4 sites), each wrapped in try/except so
  ledger failure can never block or crash a real trade
- scripts/proof_scorecard.py — Sunday Telegram report; VPS cron following the
  period_profit.py pattern
- Integrity watchdog loop
- No changes to entry/exit decision logic beyond PR #13 (if merged pre-freeze)

Deploy process (unchanged, critical): push to GitHub -> Arto approves ->
`docker compose build --no-cache trading-bot && docker compose up -d` on VPS.
No deploy without Arto's go.

## 6. Freeze Rules (clock-start until gate verdict)

- No config changes, no threshold tuning, no new strategies, no capital changes.
- Allowed: bugfixes to ledger/reporting only (observation layer), and emergency
  fixes for anything that risks capital (e.g. hedge-break bug). Every intervention
  is logged in the ledger.
- Any change that touches trading logic mid-proof resets the cycle counter to
  zero.

## 7. Outcomes

### On PASS

1. Focused re-audit before any capital moves: diff review of all changes since the
   pre-proof audit + ledger anomaly scan (fee drift, slippage trends, near-miss
   hedge breaks). Capital moves only after a clean report AND Arto's explicit go.
2. Staged capital: $336 -> $2,500 for 4+ clean cycles at real mid-size fills
   (~$750/position), then -> $10,000. Roughly 4-6 additional weeks.
3. The ledger, scorecard, and gate metrics stay on permanently. Rolling accuracy
   below 8/10 at any capital level = automatic freeze of new entries + Telegram
   alert.
4. Honest economics at $10k: 10-15% annualized -> ~$1,000-1,500/year. Fee-tier and
   multi-exchange work considered only after three clean months at $10k.

### On FAIL (after the one retry)

1. Bot stopped; positions closed at natural exits (no fire-sale).
2. Arto withdraws remaining capital.
3. Repo archived with post-mortem; ledger data preserved as research.
4. CheckoutGuard becomes the sole profit project.
5. Memory updated with the verdict.

## 8. Timeline

| Milestone | Target |
|---|---|
| Pre-proof audit phase starts | 2026-07-18 |
| Audit report + fixes merged, PR #13 decided, market scan done | ~2026-07-30 |
| Freeze + deploy, proof clock starts | ~2026-08-01 |
| Gate verdict (or "insufficient cycles" failure) | 2026-10-01 hard |
| On pass: re-audit + $2,500 stage | Oct-Nov 2026 |
| On pass: $10,000 | ~Dec 2026 |

## 9. Out of Scope (explicitly)

- Funding arbitrage revival (empirically dead at VIP0)
- Multi-exchange expansion
- Fee-tier optimization
- Any strategy changes during the proof window
