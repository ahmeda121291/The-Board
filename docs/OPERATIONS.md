# Boardroom — Operations & Risk Model

How the system scans, how the agents work, and the hard limits that bound it.
This is the human-readable companion to the code in `boardroom/` and the source
for the in-app **Docs** page.

---

## 1. The grounding law

**The LLM reasons; code calculates.** No quantitative field the system acts on
is ever produced by an LLM's free-form judgment. Every number — expected return,
win probability, size, max loss, cost — comes from a deterministic, unit-tested
function on real market data. The language model only writes narrative and
adjudicates genuinely qualitative calls. (`boardroom/models`, `boardroom/features`.)

---

## 2. Scanning & decision frequency

Frequency matches the **slowest-resolving feedback loop**, not the fastest data
refresh. Review often (cheap), act rarely (consequential).

| Division | Scan / decision cadence | Why |
|---|---|---|
| **Yield** (floor) | Continuous / passive | The default resting state, not a decision. |
| **Directional** (equities) | **Advisory**, twice daily | Scanned wide for the recommended portfolio; never auto-traded. |
| **Event** (crypto) | **Trigger-driven**, unscheduled | Auto-trades on Kraken. Pitches only when quantitative triggers fire — maybe zero for weeks. |
| **Effort** (disabled) | Weekly at most | Feedback too slow to touch more often. |

The **CEO convenes twice daily** as a checkpoint — auto-trading crypto and refreshing
the advisory stock recommendation. The expected output of most checkpoints is
**HOLD — stay in the floor.** Calendar-driven action is the enemy; the null default is
the single most important rule.

Three nested loops (`boardroom/graph`):
1. **Decision loop** (per checkpoint) — divisions pull fresh data → compute → pitch or
   abstain → cost gate → risk manager → CEO decides FUND / FUND_NONE / HOLD for crypto →
   execute (live only behind the flag) → build the advisory equities recommendation →
   log everything.
2. **Performance loop** (daily snapshot + weekly) — ROI vs both benchmarks,
   attribution, drawdown, cost drag; trips circuit breakers if limits are crossed.
3. **Learning loop** (per resolved decision + weekly) — the Critic scores each
   outcome; calibration updates trust + leashes; the model re-fits within
   guardrails; broken divisions are benched.

---

## 3. The agents

| Agent | Role | Reasoning vs math |
|---|---|---|
| **Divisions** (Yield, Directional, Event, Effort) | Hunt one orthogonal opportunity type; pitch in a standard schema or abstain. | Numbers computed; narrative LLM-authored. |
| **CEO** | Ranks pitches vs the floor, weights each division by demonstrated calibration, sizes by conviction, decides where capital goes — or that it goes nowhere. | Ranking, hurdle, trust-weighting, sizing are **deterministic**; LLM writes the rationale only. |
| **Risk Manager** | Adversarially challenges every surviving pitch (cost, max loss, liquidity, stop integrity, caps). | Hard vetoes are **code** the LLM can't talk past; LLM adds qualitative concerns. |
| **Critic** | Scores every resolved decision: predicted vs realized, calibration, process-vs-luck. | Calibration/Brier deterministic; LLM writes the post-mortem. |

**Track-record-weighted trust:** the CEO keeps a live Beta posterior on each
division. It distrusts *stated* confidence and trusts *demonstrated* calibration —
a division that says 70% but hits 50% gets discounted. (`boardroom/adaptive`.)

---

## 4. Hard caps — percent of portfolio (they scale as you grow)

All caps are **fractions of the current total portfolio value**, not fixed dollar
amounts, so every ceiling grows with the account (a $40 cap at $200 becomes $400
at $2,000 — same 20%). They are enforced in code, **outside any agent's control**,
and resolved to CAD against live equity at decision time. (`boardroom/risk`,
`boardroom/config.py`.)

| Cap | Default | Meaning |
|---|---|---|
| `TOTAL_DEPLOYABLE_PCT` | **80%** | Max fraction the agents may deploy out of the floor (≥20% always rests). |
| `PER_TRADE_MAX_PCT` | **20%** | Max for any single trade. |
| `EVENT_HARD_CAP_PCT` | **5%** | Absolute ceiling on the Event (lottery) division — the CEO can never override it. |
| `DAILY_LOSS_LIMIT_PCT` | **6%** | Daily realized loss limit; breach forces ALL capital to the floor. |
| `MAX_DRAWDOWN_PCT` | **15%** | Peak-to-trough; breach trips the circuit breaker. |
| `FEE_DRAG_LIMIT_PCT` | **5%** | Cumulative cost-drag ceiling; breach de-risks to the floor. |

Resolved at a **$200** portfolio that's: deployable $160, per-trade $40, Event $10,
daily-loss $12. At **$1,000** it's automatically $800 / $200 / $50 / $60. Override
any percentage via the matching env var.

**Circuit breakers** (any one trips → force all capital to the floor): daily loss
≥ limit, drawdown ≥ max, or cost drag ≥ limit.

**Sizing:** once a pitch clears the cost gate and beats the floor, the CEO sizes
by `edge × trust-adjusted-confidence` (fractional-Kelly, deliberately timid),
then clamps to the per-trade cap, the deployable headroom, and — for Event — the
hard cap. Equal sizing is forbidden; the variance of position size is the CEO
expressing judgment.

---

## 5. Safety rails (in code, outside any agent)

- `LIVE_TRADING` defaults **false**; the CLI also requires `--confirm-live`.
- Venue credentials are **trade-only, withdrawals disabled** — the broker classes
  have no withdraw code path and assert `supports_withdrawal == False`.
- Kraken and the equities venue are **isolated** accounts — a leak in one can't
  touch the other.
- Stale / missing / insane data → the division **abstains**. No trade on garbage.
- A backtest gate: a division can't deploy real capital until its rule shows
  historical edge net of cost (which also seeds its calibration prior).

---

## 6. Adaptation, within guardrails

What adapts automatically: calibration posteriors, feature/model weights
(periodic re-fit on recent resolved outcomes), and per-division risk leashes.
Guarded by: minimum sample before a re-fit, bounded weight moves, walk-forward
validation, and regime humility. Persistently miscalibrated or net-negative
divisions get their leash set to **zero** (benched) until re-validated. New
components run in **shadow mode** — scored but unfunded — until they earn in.
