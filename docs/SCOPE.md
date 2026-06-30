# Boardroom — Living Scope

> **This is the canonical, continuously-updated scope.** It supersedes the original
> `Boardroom_Scope.docx` and is kept in sync with the code as the system evolves.
> When behavior changes, this file changes in the same commit.
>
> **Last updated:** 2026-06-30 · **Status:** LIVE (real capital) · **Funding:** ~$200+ CAD

---

## 1. What Boardroom is

An autonomous, multi-agent capital-allocation system. **Twice a day** it convenes a
"boardroom" of specialized agents, looks at real crypto and equity market data,
and decides where a small pool of capital should go — **usually nothing**. It is
deliberately low-frequency, floor-first, and skeptical of its own ideas.

It operates in **two modes, split by venue:**

- **Crypto (Kraken) — fully autonomous.** The Yield and Event divisions auto-trade
  live (within the caps, default HOLD). This is the only money the system moves on
  its own.
- **Stocks (IBKR) — advisory only.** The system never auto-trades equities. Instead it
  scans a wide universe, publishes a **recommended portfolio**, reads the user's
  **actual IBKR holdings**, and presents *current vs recommended* with a plain-English
  buy/sell explanation. The user executes those trades by hand.

It is designed to run unattended and be safe by construction: it can place crypto
trades but **cannot withdraw money** from any venue, and it **cannot trade stocks at all**.

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

| Division | Asset class | Venue | Funding | Role |
| --- | --- | --- | --- | --- |
| **Yield** | Crypto | Kraken | auto-trades | The floor — the safe baseline return every other idea must beat. |
| **Event** | Crypto | Kraken | auto-trades | Event/catalyst-driven crypto opportunities. The only division the CEO funds with real capital. |
| **Directional** | Stocks / ETFs | IBKR | **advisory** | Equity ideas — feed the recommended portfolio. Never auto-funded. |
| **Momentum** | Stocks + crypto | IBKR / Kraken | **advisory** | Volume-confirmed breakouts (catalyst continuation). Advisory. |
| **Effort** | — | — | disabled | Disabled. Reserved. |

A pitch carries computed numbers (code) plus a short narrative (LLM). Quant fields
are never LLM guesses.

**Advisory vs fundable.** Equities are **advisory**: Directional/Momentum pitch stocks,
but the CEO never funds them. Only crypto (Event) is auto-traded. The advisory equity
pitches feed the **recommendation engine** (§2a) instead.

**Scanned universe.** Because stocks are advisory, the equity universe is deliberately
**wide** (~70 liquid stocks/ETFs by default — broad-market & sector ETFs, megacaps,
high-momentum semis/AI/growth names incl. **SNDK** — so a runaway winner isn't missed).
Event scans the major crypto pairs (BTC, ETH, SOL, XRP, ADA, LINK, DOT, +more wide).
Every symbol runs the same grounded model + risk/cost gates.

### 2a. The recommendation engine (advisory equities)

`boardroom/recommend.py` turns the advisory equity pitches into a **recommended
portfolio**, fully deterministically:

1. keep equity pitches that beat the floor net of cost (risk-adjusted score > 0),
2. rank by the same risk-adjusted score the CEO uses for crypto,
3. weight proportional to score, cap each name at the per-trade cap (20%), and keep the
   book within the deployable cap (80%) — the remainder is cash,
4. read the user's **actual IBKR holdings** (`IBKRBroker.get_positions()`),
5. **diff** current vs recommended → ordered `buy / sell / trim / hold` actions with
   dollar deltas (a rebalance band suppresses trading noise).

`agents/advisor.py` writes the plain-English summary ("Buy Costco, sell SanDisk").
Every number is code-computed; the LLM only narrates. The output is persisted to the
`recommendations` table each checkpoint and rendered on the dashboard as **"Current
portfolio in IBKR" vs "Recommended portfolio"**.

---

## 3. The agents (who decides)

| Agent | What it does |
| --- | --- |
| **CEO** | Deterministically ranks the surviving **fundable (crypto)** pitches against the hurdle rate and each division's demonstrated track record. Default action is **HOLD** (stay in the floor). Auto-funds at most the single best crypto idea, or nothing. Equity pitches are advisory and bypass funding — they go to the recommendation engine. |
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

- **Two checkpoints per day** — `CHECKPOINT_TIMES`, default **`13:30,19:00` UTC**
  (≈ near the open and ~1h before the close, ET). Each checkpoint auto-trades crypto
  AND refreshes the advisory stock recommendation + IBKR holdings diff.
- Crypto (Kraken) trades **24/7** — the Yield/Event legs can act at any checkpoint.
- Stocks are **advisory** — nothing auto-executes on IBKR, so there's no equity-fill
  timing concern. The recommendation is computed off the latest daily bars at each
  checkpoint regardless of session.
- **Market-hours guard** still exists as defense in depth (it would hold any live
  equity order placed while the market is closed), but equities no longer auto-trade.

> **Why twice a day?** See §9.

**On-demand runs.** Besides the scheduled checkpoints you can trigger a run yourself,
two ways: a **"Run Boardroom Now" desktop shortcut** (fires a live checkpoint on the
PC immediately), or a **"Run now" button on the dashboard**. The dashboard button
only *requests* a run (inserts a row in `run_requests`) — it never trades, because
the keys live only on the PC. A local **poller** (`boardroom poll`, a background
scheduled task) claims the request and runs the checkpoint locally, preserving the
dashboard's read-only safety property. The daily scheduler stays on alongside this.

---

## 6. The three loops (the engine)

1. **Decision loop (per checkpoint):** gather data → divisions pitch → risk vetoes →
   CEO ranks & funds/holds the **crypto** legs → execute (live behind the flag) →
   build the **equities recommendation** (rank advisory pitches → read IBKR holdings →
   diff → narrate → persist) → log everything.
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
| Stocks | **No equity execution path at all.** The IBKR integration is read-only (holdings + cash); the system only *recommends* stock trades. |
| Keys | Trade-only, scoped per venue. Kraken and the equities account are **isolated** — a leak in one can't touch the other. |
| Live gate | A live (crypto) order requires **both** the global `LIVE_TRADING=true` flag **and** a per-call `--confirm-live`. Otherwise every run is a dry-run simulation. |

---

## 8. The dashboard

A Vercel-hosted dashboard reads the logged state from Supabase (read-only) and shows:
live/armed status, next-checkpoint countdown, equity curve, the CEO's latest verdict
and the full session, division calibration, attribution, the CFO review, and the
"Ask the Boardroom" chat. Password-gated.

It also shows two holdings views:

- **Your portfolio** — what's actually held across both venues, from a portfolio
  snapshot taken each checkpoint (`boardroom/portfolio.py`, persisted via migration
  0010): crypto coins + cash on Kraken (with each coin's intraday change), stock
  holdings + cash + unrealized P&L on IBKR, the crypto/stock split, and the day's top
  gainers/losers. `KrakenBroker.get_positions()` / `IBKRBroker.get_positions()` read
  the real books; every derived number is code-computed (unpriced holdings show as
  such rather than guessed).
- **Stocks — recommended portfolio** — the plain-English advisory note, the actionable
  buy/sell/trim list, and **"Current portfolio in IBKR" vs "Recommended portfolio"**
  side by side.

All read-only — the user places any stock orders in IBKR themselves.

---

## 9. Open design questions / rationale

**Is twice-a-day enough for 24/7 crypto?** For a ~$200 book, **yes — by design.**
- Trading more often multiplies **fee drag**, which is fatal on a small account
  (the fee-drag cap is 5% of equity). Twice daily is a deliberate, conservative cadence.
- The system **holds the floor most checkpoints** and rarely carries an open crypto
  position, so there is usually nothing to "manage" intraday.
- The second daily checkpoint mainly buys responsiveness on the **advisory stock
  recommendation** (which is free — no fees) and a faster look at the live portfolio,
  not more crypto churn.

This is revisited as the account grows. The natural next step (when equity and
open-position frequency justify the fees) is an **intraday risk-only check** for
crypto — i.e. allow the Event division to *exit* a cratering position between
checkpoints, without increasing entry frequency. Not warranted at current size.

---

## Changelog

- **2026-06-30** — **The crypto-auto / stocks-advisory remodel.** Split the system by
  venue. **Crypto (Kraken) stays fully autonomous** — Event/Yield auto-trade live as
  before. **Stocks (IBKR) are now advisory only**: `DirectionalDivision.advisory=True`
  (Momentum already advisory), so equities are never auto-funded. Added the
  **recommendation engine** (`boardroom/recommend.py`): it ranks the advisory equity
  pitches into a weighted target portfolio (score-proportional, per-trade-capped, within
  the deployable cap), reads the **real IBKR holdings** (`IBKRBroker.get_positions()`),
  and **diffs** current vs recommended → buy/sell/trim/hold actions; `agents/advisor.py`
  writes the plain-English "buy COST / sell SNDK" note (code computes every number).
  Persisted to a new `recommendations` table (migration 0009) and rendered on the
  dashboard as **"Current portfolio in IBKR" vs "Recommended portfolio"**. The equity
  universe went **wide by default** (~70 liquid names incl. SNDK + momentum/growth) so
  runaway winners aren't missed. Cadence moved to **twice daily** (`CHECKPOINT_TIMES`,
  default `13:30,19:00` UTC). 215 tests passing.

- **2026-06-29** — **Equity-scaled aggression schedule + real venue balances + a
  human dashboard.** The CEO's deviation bar (how readily it leaves the floor) is now a
  function of equity: low (0.005) while the account is small so it actually deploys and
  compounds, rising to the conservative 0.02 as equity grows past $5k — bolder small,
  calmer as it grows. Hard caps unchanged. The dashboard now shows REAL venue cash
  (pulled by the local runner via `boardroom balances` → `system_state`, migration 0008)
  instead of a hardcoded baseline, and was reworked to lead with plain language (filters,
  legends, a "show the numbers" toggle) rather than raw model internals.
- **2026-06-29** — **Directional venue switched to Interactive Brokers; SnapTrade /
  Wealthsimple fully removed.** A SnapTrade→Wealthsimple connection couldn't be made
  trade-capable (read-only / account lockout), so the equity leg now executes on IBKR
  via the Client Portal Gateway (session-based; no static API key). Deleted the
  SnapTrade broker, connect helper, config, dependency, and the `Venue.SNAPTRADE`
  enum; IBKR is the sole Directional venue. Also hardened the test suite to be
  hermetic (`tests/conftest.py`) — it strips live credentials / `LIVE_TRADING` / the
  Supabase keys and never reads `.env`, so running `pytest` on the live machine can
  no longer attempt real orders or touch the production database.
- **2026-06-28** — **Self-improvement transmission wired + diligence upgrades.** The
  adaptive engine was fully built but never ran live (no outcome ever resolved). Added
  a resolution loop: funded positions (paper or live) are marked to fresh prices each
  checkpoint, resolved on horizon/stop net of cost, and folded into calibration → leash
  → retirement through the existing guardrails. Added a guardrailed walk-forward model
  re-fit (persisted in `model_params`, gated by can-refit + out-of-sample survival +
  bounded step; rejected re-fits change nothing). New pure diligence features (ATR,
  Sortino, downside deviation, skew/kurtosis, MACD, Bollinger bandwidth, beta); the
  floor carry APR is now configurable (`FLOOR_CARRY_APR`) and refreshable from live
  Kraken Earn within a sanity band. New tables: `open_positions`, `model_params`.
  Structural self-modification remains `requires_human`; all new adaptation is
  parameter-level and behind the guardrails. (The Event news-gate prototyped on this
  branch was dropped in favor of the canonical Yahoo `news_intensity` feed below.)
- **2026-06-28** — Docs reconciled: README updated to SnapTrade → Wealthsimple as the
  Directional venue (IBKR retained as an alternate adapter), and the branch workflow
  switched to `main` for everything (RUNBOOK clone + CLAUDE.md working agreement).
- **2026-06-26** — **News / catalyst feed** (`data/news.py`, keyless Yahoo search).
  Computes a deterministic `news_intensity` (recency-weighted headline burst) that
  confirms whether real coverage backs a breakout, and attaches the headlines as
  read-only context — fetched only for breakout candidates, degrades to "no news"
  on failure. Grounding intact: the score is code, headlines are context, neither
  is an LLM number. Shown on the dashboard session ("📰 Catalyst news").
- **2026-06-26** — **Momentum / catalyst-continuation division** added (the LLY fix).
  Root cause of missing catalyst moves: every prior model (Directional, Event) is
  mean-reversion biased and *fades* strength, so a volume-driven breakout was scored
  as a SELL. The new Momentum strategy BUYS volume-confirmed upside breakouts
  (`breakout_strength` + `volume_surge` features), is asset-agnostic (stocks AND
  crypto, routed per symbol), and ships **advisory** — it pitches/logs but gets no
  real capital until validated on live data. LLY + more catalyst-prone megacaps added
  to the core daily universe.
- **2026-06-26** — Equity feed switched to **Yahoo Finance** (Stooq was serving a
  bot-block page). Dashboard **"Tracked universe"** card (the symbols scanned each
  run). **"Run wide scan"** button + `--wide` mode: a broader curated ~50-symbol set
  (40 liquid stocks/ETFs + 10 crypto) on demand, vs the daily core ~21. Deliberately
  curated/liquid, not a whole-market scan.
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
