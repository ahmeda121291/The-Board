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
  · **Directional** (stocks/ETFs via Wealthsimple→SnapTrade) · **Effort** (disabled).
- **CEO** ranks pitches deterministically vs hurdle + track record; default HOLD; funds
  ≤1 best idea. **Risk Manager** adversarially vetoes. **Critic** challenges reasoning.
  **CFO/Strategist** studies the scoreboard, writes a review each checkpoint
  (structural recs tagged `requires_human`).

## Money & safety (non-negotiable)

- **Caps are percent-of-portfolio** (scale with equity): deployable 80%, per-trade 20%,
  Event 5%, daily-loss 6%, max-drawdown 15%, fee-drag 5%. Circuit breakers on loss/drawdown.
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

## Live-armed state

- Durable `live_armed` flag in Supabase `system_state` (set whenever a live-confirmed
  run convenes). Dashboard badge: **LIVE TRADING** (a real trade logged) /
  **LIVE · ARMED** (`live_armed` true, no trade yet) / **dry-run · safe**. It does NOT
  reset on redeploy.

## Where things live

- **Code**: `boardroom/` (config, schemas, divisions, ceo, risk, brokers, graph,
  agents, persistence, market.py). **Tests**: `tests/` (132 passing; `python -m pytest`).
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
