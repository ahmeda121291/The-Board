# CLAUDE.md — Boardroom

> Memory + quick reference for this project. Loaded automatically by Claude Code in
> this repo. For the full living spec see **`docs/SCOPE.md`** (kept in sync on every change).

## What this is

**Boardroom** is an autonomous, multi-agent capital-allocation system funded with
~$200 CAD (Canadian resident). Once a day it convenes a "boardroom" of agents, looks
at real crypto + equity data, and decides where capital goes — **usually nothing
(HOLD the floor)**. It is live (real money) as of 2026-06.

## The one rule that governs everything

**The LLM reasons; code calculates.** No quantitative field the system acts on
(expected return, win probability, size, max loss, cost) is ever an LLM free-form
guess — all come from deterministic, unit-tested functions on real data. The LLM
only writes narrative and adjudicates qualitative calls. Enforced in the schema layer.

## Divisions (pitch ideas) → Agents (decide)

- **Yield** (crypto/Kraken) = the floor every idea must beat · **Event** (crypto/Kraken)
  · **Directional** (stocks/ETFs via Interactive Brokers) · **Effort** (disabled).
- **Momentum** (catalyst-continuation) = the counterweight to the mean-reversion bias
  in Directional/Event: BUYS volume-confirmed upside breakouts (`models/momentum.py`,
  `breakout_strength`+`volume_surge`). Asset-agnostic (stocks+crypto, `venue_for`
  routes per symbol). Ships **advisory** (`advisory=True` → pitches/logs but never
  funded) until validated. Advisory pitches are excluded from CEO funding in the loop.
- **News/catalyst feed** (`data/news.py`, keyless Yahoo search): computed
  `news_intensity` (recency-weighted headline burst) confirms a breakout; headlines
  attached as context via `Division.enrich()` (fetched only for breakout candidates).
  Grounding intact: score is code, headlines are context. Shown on dashboard session.
- **Scanned universe** (factory.py): core = 14 liquid ETFs/mega-caps + 7 crypto pairs;
  **wide** = ~40 stocks/ETFs + 10 crypto (the "Run wide scan" button / `--wide`).
  Equities via **Yahoo** (`fetch_equity_daily`, Stooq fallback), crypto via Kraken.
  Each division pitches one idea per qualifying symbol (`propose_all`); the CEO ranks
  across all and funds the single best. Long-only (IBKR cash/Kraken-spot can't short).
- **CEO** ranks pitches deterministically vs hurdle + track record; default HOLD; funds
  ≤1 best idea. **Risk Manager** adversarially vetoes. **Critic** challenges reasoning.
  **CFO/Strategist** studies the scoreboard, writes a review each checkpoint
  (structural recs tagged `requires_human`).

## Money & safety (non-negotiable)

- **Caps are percent-of-portfolio** (scale with equity): deployable 80%, per-trade 20%,
  Event 5%, daily-loss 6%, max-drawdown 15%, fee-drag 5%. Circuit breakers on loss/drawdown.
- **Aggression schedule** (`ceo/engine.py`): the CEO's deviation bar is LOW while the
  account is small (0.005 ≤ $500) and rises to conservative (0.02 ≥ $5000) as equity grows
  — bolder small, calmer as it compounds. Tunable via `CEO_DEVIATION_THRESHOLD*` /
  `AGGRESSIVE_BELOW_CAD` / `CONSERVATIVE_ABOVE_CAD`. Hard caps above are unaffected.
- **Gains ratchet** sweeps a fraction of new highs into an **untouchable reserve**.
- **Withdrawals DISABLED on every venue** — no transfer code path exists. Keys are
  trade-only and per-venue isolated (Kraken ⟂ equities).
- **Live gate**: a real order needs BOTH `LIVE_TRADING=true` AND per-call `--confirm-live`.
  Otherwise every run is a dry-run simulation.

## Scheduling & market hours

- **One checkpoint/day at 3pm local** (Windows Task Scheduler runs `boardroom run
  --confirm-live --once`; with `--once` the trigger time IS the execution time).
- Crypto is 24/7. Stocks only fill 9:30–16:00 ET; 3pm local = 1h before close
  (summer & winter). **Market-hours guard** auto-holds any live equity order placed
  while the market is closed (logs `equity_market_closed`); crypto unaffected.
- Off-days (weekends/holidays): checkpoint still convenes **crypto-only**.
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
  agents, persistence, market.py). **Tests**: `tests/` (189 passing; `python -m pytest`).
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
  outbound financial/Supabase hosts). PC must be awake before 3pm local for the run.

## Working agreements

- Work on `main` for everything; pushes to `main` auto-deploy to production. Commit as
  `Claude <noreply@anthropic.com>`.
- **When behavior changes, update `docs/SCOPE.md` (+ changelog) in the same commit.**
- Never commit secrets; `.env` is gitignored. Never echo secret values.
- Once-daily cadence is deliberate (fee drag on a small book). Future upgrade when the
  account grows: intraday **risk-only** crypto exit (not more entries).
