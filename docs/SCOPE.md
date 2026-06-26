# Boardroom — Living Scope

> **This is the canonical, continuously-updated scope.** It supersedes the original
> `Boardroom_Scope.docx` and is kept in sync with the code as the system evolves.
> When behavior changes, this file changes in the same commit.
>
> **Last updated:** 2026-06-25 · **Status:** LIVE (real capital) · **Funding:** ~$200 CAD

---

## 1. What Boardroom is

An autonomous, multi-agent capital-allocation system. Once a day it convenes a
"boardroom" of specialized agents, looks at real crypto and equity market data,
and decides where a small pool of capital should go — **usually nothing**. It is
deliberately low-frequency, floor-first, and skeptical of its own ideas.

It is designed to run unattended and be safe by construction: it can place trades
but **cannot withdraw money** from any venue.

### The grounding law (the single most important rule)

**The LLM reasons; code calculates.** No quantitative field the system acts on —
expected return, win probability, position size, max loss, cost — is ever produced
by an LLM's free-form judgment. Those all come from deterministic, unit-tested
functions on real market data. The language model only writes narrative and
adjudicates qualitative calls. This is enforced in the schema layer, not by
convention.

---

## 2. The divisions (where ideas come from)

Each division is an independent strategy that *pitches* opportunities. They do not
trade directly — they propose, and the CEO disposes.

| Division | Asset class | Venue | Role |
| --- | --- | --- | --- |
| **Yield** | Crypto | Kraken | The floor — the safe baseline return every other idea must beat. |
| **Event** | Crypto | Kraken | Event/catalyst-driven crypto opportunities. |
| **Directional** | Stocks / ETFs | Wealthsimple (via SnapTrade) | Directional equity positions. |
| **Effort** | — | — | Disabled. Reserved. |

A pitch carries computed numbers (code) plus a short narrative (LLM). Quant fields
are never LLM guesses.

**Scanned universe.** Each checkpoint, Directional scans a basket of liquid ETFs and
mega-caps (SPY, QQQ, IWM, DIA, sector ETFs, AAPL/MSFT/NVDA/AMZN/GOOGL/META) and Event
scans the major crypto pairs (BTC, ETH, SOL, XRP, ADA, LINK, DOT). Every symbol runs
the same grounded model + risk/cost gates; the CEO ranks across all of them and funds
at most the single best. A wider universe means more chances something is a genuine,
non-stretched, positive-edge buy — so the system actually deploys, rather than holding
because its only candidate was overbought.

---

## 3. The agents (who decides)

| Agent | What it does |
| --- | --- |
| **CEO** | Deterministically ranks surviving pitches against the hurdle rate and each division's demonstrated track record. Default action is **HOLD** (stay in the floor). Funds at most the single best idea, or nothing. |
| **Risk Manager** | Adversarial. Tries to *veto* each pitch (e.g. "edge doesn't clear cost"). Vetoes drop the pitch before the CEO sees it. |
| **Critic** | Challenges reasoning quality. |
| **CFO / Chief Strategist** | Studies the whole scoreboard — calibration, attribution, cost drag, drawdown — and writes a strategic review with recommendations each checkpoint. Structural changes it proposes are tagged `requires_human` and never auto-applied. |

You can talk to the CEO and CFO directly from the dashboard ("Ask the Boardroom").
It is **read-only** — a chat box can never trigger a trade.

---

## 4. Money & risk caps — percentage-based

**All caps scale with the portfolio.** They are expressed as a percent of current
equity, so they grow as the account grows and shrink if it draws down — no fixed
dollar amounts to outgrow. Resolved against live equity (falls back to the
`STARTING_PORTFOLIO_CAD` baseline until live equity is wired).

| Cap | Default | Meaning |
| --- | --- | --- |
| Total deployable | 80% | Most of the book can be at work; the rest stays in the floor. |
| Per-trade max | 20% | No single position exceeds this share. |
| Event hard cap | 5% | Crypto Event is capped tight. |
| Daily loss limit | 6% | Circuit breaker for the day. |
| Max drawdown | 15% | Hard drawdown breaker. |
| Fee-drag limit | 5% | Cumulative cost ceiling. |

**Circuit breakers** halt new risk when the daily-loss or drawdown limits trip.

**Gains ratchet & reserve.** As realized equity makes new highs, a fraction of the
gain is swept into an **untouchable reserve** — locking in progress so the system
plays with house money over time.

---

## 5. When it runs — and the market-hours rule

- **One checkpoint per day** at **3:00pm local (≈19:00 UTC summer)**.
- Crypto (Kraken) trades **24/7** — the Yield/Event legs can act at any checkpoint.
- Stocks (Wealthsimple) only fill during the **regular session, 9:30am–4:00pm ET**.
  3pm local is **1 hour before the close** in both summer and winter, so the
  Directional leg fills while the market is open.
- **Market-hours guard:** if a live equity order is ever attempted while the market
  is closed, the system **holds that leg** and logs `equity_market_closed` instead
  of queuing a blind after-hours order at an unknown price. Crypto is unaffected.
- On weekends/holidays the checkpoint still convenes **crypto-only** (the equity
  leg is auto-held).

> **Why once a day?** See §9.

**On-demand runs.** Besides the daily 3pm checkpoint you can trigger a run yourself,
two ways: a **"Run Boardroom Now" desktop shortcut** (fires a live checkpoint on the
PC immediately), or a **"Run now" button on the dashboard**. The dashboard button
only *requests* a run (inserts a row in `run_requests`) — it never trades, because
the keys live only on the PC. A local **poller** (`boardroom poll`, a background
scheduled task) claims the request and runs the checkpoint locally, preserving the
dashboard's read-only safety property. The daily scheduler stays on alongside this.

---

## 6. The three loops (the engine)

1. **Decision loop (daily):** gather data → divisions pitch → risk vetoes → CEO
   ranks & funds/holds → execute (live behind the flag) → log everything.
2. **Measurement loop (per outcome):** every resolved trade updates each division's
   calibration (a Beta posterior — *demonstrated* accuracy, not stated confidence),
   attribution, and the scoreboard.
3. **Adaptive loop (ongoing):** trust/leash per division adjusts from calibration;
   the CFO studies the whole picture and recommends structural changes for human
   sign-off.

---

## 7. Venues & safety

| Property | Guarantee |
| --- | --- |
| Withdrawals | **Disabled everywhere.** No transfer/withdraw code path exists. Trade access cannot move your money. |
| Keys | Trade-only, scoped per venue. Kraken and the equities account are **isolated** — a leak in one can't touch the other. |
| Live gate | A live order requires **both** the global `LIVE_TRADING=true` flag **and** a per-call `--confirm-live`. Otherwise every run is a dry-run simulation. |

---

## 8. The dashboard

A Vercel-hosted dashboard reads the logged state from Supabase (read-only) and shows:
live/armed status, next-checkpoint countdown, equity curve, the CEO's latest verdict
and the full session, division calibration, attribution, the CFO review, and the
"Ask the Boardroom" chat. Password-gated.

---

## 9. Open design questions / rationale

**Is once-a-day enough for 24/7 crypto?** For a ~$200 book, **yes — by design.**
- Trading more often multiplies **fee drag**, which is fatal on a small account
  (the fee-drag cap is 5% of equity).
- The system **holds the floor most days** and rarely carries an open directional
  crypto position, so there is usually nothing to "manage" intraday.
- More frequent entries invite reactive churn — the opposite of the floor-first,
  skeptical philosophy.

This is revisited as the account grows. The natural next step (when equity and
open-position frequency justify the fees) is an **intraday risk-only check** for
crypto — i.e. allow the Event division to *exit* a cratering position between daily
checkpoints, without increasing entry frequency. Not warranted at current size.

---

## Changelog

- **2026-06-26** — **Widened the scanned universe** from 1 ticker per division to a
  basket (Directional: ~14 ETFs/mega-caps; Event: 7 crypto pairs). Each checkpoint
  scores every symbol and the CEO funds the best — far more likely to find an
  actionable buy than scanning a single (often overbought) instrument. Batch-file
  launchers (`run_*.cmd`) replaced the `.ps1` ones that wouldn't launch from Task
  Scheduler / Startup. On-demand "Run now" verified end-to-end.
- **2026-06-25** — Daily **keep-alive cron** (Vercel → `/api/keepalive` → trivial
  Supabase read) so the free-tier project never idles out and gets paused. A paused
  project drops its `<ref>.supabase.co` DNS, which breaks every local run; the
  keep-alive runs on Vercel independent of the PC. Poller hardened to survive
  transient DNS/connection errors instead of crashing.
- **2026-06-25** — On-demand runs: dashboard "Run now" button + `run_requests`
  queue + local `boardroom poll` poller, and a "Run Boardroom Now" desktop shortcut.
  Daily 3pm scheduler unchanged. Durable `live_armed` flag so the live/armed badge
  survives redeploys.
- **2026-06-25** — Market-hours guard added; daily checkpoint moved to 3pm local so
  the equity leg fills in-session. Tri-state live status badge. This living scope
  created and linked from the dashboard.
- **2026-06** — All caps converted from fixed dollars to **percent-of-portfolio**.
  CFO/Strategist agent, gains ratchet + reserve, equity chart, session history, and
  "Ask the Boardroom" chat added. SnapTrade→Wealthsimple chosen for Directional.
- **Initial** — M0–M6: contracts, decision loop, grounding layer, adversarial risk
  manager, measurement + Supabase, adaptive engine, venue adapters, dashboard.
