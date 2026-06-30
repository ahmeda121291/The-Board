# CLAUDE.md — Boardroom

> Memory + quick reference for this project. Loaded automatically by Claude Code in
> this repo. For the full living spec see **`docs/SCOPE.md`** (kept in sync on every change).

## What this is

**Boardroom** is an autonomous, multi-agent capital-allocation system funded with
~$200+ CAD (Canadian resident). **Several times a day** (4× by default) it convenes a
"boardroom" of agents, looks at real crypto + equity data, and decides where capital
goes. Live (real money) as of 2026-06. Two modes, split by venue:

- **Crypto (Kraken) = fully autonomous, auto-trades live.** Yield = the floor; Event
  takes rare asymmetric bets. Default is still HOLD the floor — most checkpoints do
  nothing.
- **Stocks (IBKR) = ADVISORY ONLY, never auto-trades.** The system scans a wide equity
  universe and publishes a **recommended portfolio**, reads the **actual IBKR holdings**,
  and shows **"Current portfolio in IBKR" vs "Recommended portfolio"** with the AI
  explaining the diff in plain English ("buy Costco", "sell SanDisk"). The user places
  those orders by hand.

## The one rule that governs everything

**The LLM reasons; code calculates.** No quantitative field the system acts on
(expected return, win probability, size, max loss, cost) is ever an LLM free-form
guess — all come from deterministic, unit-tested functions on real data. The LLM
only writes narrative and adjudicates qualitative calls. Enforced in the schema layer.

## Divisions (pitch ideas) → Agents (decide)

- **Yield** (crypto/Kraken) = the floor every idea must beat · **Event** (crypto/Kraken,
  auto-trades) · **Directional** (stocks/ETFs via IBKR, **advisory**) · **Effort** (disabled).
- **Funding rule is by VENUE** (`run_once`): only **Kraken (crypto)** pitches are
  auto-funded; every **IBKR (equity)** pitch is advisory and feeds the recommendation
  engine. So a crypto **Momentum** breakout trades live, while the same division's stock
  pitches never do. Directional (IBKR) is advisory by construction.
- **Recommendation engine** (`boardroom/recommend.py`): ranks the advisory equity pitches
  into a weighted **target portfolio** (score-proportional, per-trade-capped, within the
  deployable cap), reads the real IBKR holdings (`IBKRBroker.get_positions()`), and diffs
  them → buy/sell/trim/hold actions. `agents/advisor.py` writes the plain-English
  "buy COST / sell SNDK" note. Code computes every number; the LLM only narrates. Persisted
  to `recommendations` (migration 0009); shown on the dashboard each checkpoint.
- **Crypto Trend** (`divisions/crypto_trend.py`): the **always-on crypto workhorse** —
  reuses the trend/mean-reversion `DirectionalModel` on the Kraken universe and proposes a
  long whenever there's positive edge (not just on a rare trigger), so the system regularly
  takes crypto positions. Auto-funded (venue rule); long-only; cost-gated and capped. This
  is what turns "HOLD most checkpoints" into "regularly in the market."
- **Momentum** (catalyst-continuation): BUYS volume-confirmed upside breakouts
  (`models/momentum.py`, loosened triggers: breakout ≥1.0 vol on ≥1.25× volume).
  Asset-agnostic — its **crypto** breakouts are auto-funded on Kraken (venue rule), while
  its **equity** breakouts are advisory and feed the recommendation engine.
- **News/catalyst feed** (`data/news.py`, keyless Yahoo search): computed `news_intensity`
  (recency-weighted headline burst) confirms a breakout; headlines attached as context via
  `Division.enrich()`. Grounding intact: score is code, headlines are context.
- **Scanned universe** (factory.py): equities scan **wide by default** (~70 liquid
  stocks/ETFs incl. SNDK + high-momentum names — so a runaway winner isn't missed) since
  stocks are advisory; crypto scans ~25 liquid **CAD-quoted** Kraken pairs (the account is
  CAD-funded, so it can only buy CAD pairs). Equities via **Yahoo** (`fetch_equity_daily`,
  Stooq fallback), crypto via Kraken. Long-only.
- **CEO** ranks the *fundable* (crypto) pitches deterministically vs hurdle + track record;
  default HOLD; auto-funds ≤1 best crypto idea. **Risk Manager** adversarially vetoes.
  **CFO/Strategist** studies the scoreboard, writes a review each checkpoint.

## Money & safety (non-negotiable)

- **Caps are percent-of-portfolio** (scale with equity): deployable 80%, per-trade 20%,
  Event 5%, daily-loss 6%, max-drawdown 15%, fee-drag 5%. Circuit breakers on loss/drawdown.
- **Aggression schedule** (`ceo/engine.py`): bolder while small, calmer as it grows. Two
  knobs ride an equity ramp ($500→$5000): (1) the CEO's **deviation bar** is LOW while
  small (0.001 ≤ $500) rising to conservative (0.02 ≥ $5000) — it acts on almost any
  positive-edge crypto idea while tiny; (2) the **crypto Event position cap** is BOLD while
  small (up to the 20% per-trade max, `EVENT_HARD_CAP_PCT_SMALL`) tapering to 5% as equity
  grows. Tunable via `CEO_DEVIATION_THRESHOLD*` / `EVENT_HARD_CAP_PCT_SMALL` /
  `AGGRESSIVE_BELOW_CAD` / `CONSERVATIVE_ABOVE_CAD`. The **daily-loss (6%) and drawdown
  (15%) circuit breakers are NEVER scaled** — they're the "don't lose it all in one day"
  backstop regardless of aggression.
- **Gains ratchet** sweeps a fraction of new highs into an **untouchable reserve**.
- **Withdrawals DISABLED on every venue** — no transfer code path exists. Keys are
  trade-only and per-venue isolated (Kraken ⟂ equities).
- **Live gate**: a real order needs BOTH `LIVE_TRADING=true` AND per-call `--confirm-live`.
  Otherwise every run is a dry-run simulation.

## Scheduling & market hours

- **Checkpoints run several times a day** (`CHECKPOINT_TIMES`, default
  `13:30,15:30,17:30,19:00` UTC ≈ 4× across the ET session — more shots for crypto while
  the account is small). Windows Task Scheduler runs `boardroom run --confirm-live --once`
  at each (installer registers one trigger per time); with `--once` the trigger time IS
  the execution time. Each checkpoint auto-trades crypto AND refreshes the advisory stock
  recommendation + IBKR holdings diff + portfolio snapshot.
- Crypto is 24/7 (auto-traded any checkpoint). Stocks are advisory so there's no
  equity-execution timing concern; the **market-hours guard** still exists for safety
  (would hold any live equity order while the market is closed — but equities don't
  auto-execute now).
- Off-days (weekends/holidays): checkpoints still convene; crypto trades, stock
  recommendations refresh off the latest data.
- **On-demand runs**: dashboard "Run now" button writes a `run_requests` row; the
  local `boardroom poll` poller (a startup scheduled task on the PC) claims it and
  runs the checkpoint locally (keys stay on PC; dashboard never trades). Also a
  "Run Boardroom Now" desktop shortcut (`run_now.ps1`) for instant local runs.

## Live-armed state

- Durable `live_armed` flag in Supabase `system_state` (set whenever a live-confirmed
  run convenes). Dashboard badge: **LIVE TRADING** (a real trade logged) /
  **LIVE · ARMED** (`live_armed` true, no trade yet) / **dry-run · safe**. It does NOT
  reset on redeploy.

## Where things live

- **Code**: `boardroom/` (config, schemas, divisions, ceo, risk, brokers, graph,
  agents, persistence, market.py, **recommend.py**, **portfolio.py**). **Tests**:
  `tests/` (230 passing; `python -m pytest`).
- **Portfolio view** (`boardroom/portfolio.py`): each checkpoint (and `boardroom
  balances`) snapshots real holdings on BOTH venues — `KrakenBroker.get_positions()`
  (coins priced in CAD + intraday change) and `IBKRBroker.get_positions()` (holdings +
  unrealized P&L) — into crypto/stock/merged books with weights + top movers. Persisted
  to `portfolio_snapshots` (migration 0010); dashboard "Your portfolio" section.
- **Dashboard**: `dashboard/` (Next.js 14 on Vercel, reads Supabase read-only; Docs
  page at `/docs`; "Ask the Boardroom" chat = read-only, needs `ANTHROPIC_API_KEY`).
- **Ops**: `RUNBOOK.md`, `docs/OPERATIONS.md`, `install_scheduler.ps1`, `run_boardroom.ps1`.
- **Spec**: `docs/SCOPE.md` (living). **Migrations**: `supabase/migrations/`.

## Stack & infra

- Python 3.11, LangGraph orchestration, Anthropic LLM (`claude-opus-4-8`),
  pydantic-settings. Supabase Postgres (schema `boardroom`, project
  `qyaekaifodgiaxyztpdt`). Dashboard on Vercel (`the-board-amber`), auto-promotes
  `main` → production. GitHub: `ahmeda121291/the-board`.
- **Live operation runs on the user's Windows machine** (this remote container blocks
  outbound financial/Supabase hosts). PC must be awake for the daily checkpoints.

## Working agreements

- Work on `main` for everything; pushes to `main` auto-deploy to production. Commit as
  `Claude <noreply@anthropic.com>`.
- **When behavior changes, update `docs/SCOPE.md` (+ changelog) in the same commit.**
- Never commit secrets; `.env` is gitignored. Never echo secret values.
- Cadence is 4×/day — more shots for crypto while small; the cost gate still blocks any
  trade that doesn't clear its fees, so frequency can't become fee-bleed churn. Future
  upgrade as the account grows: intraday **risk-only** crypto exit.
