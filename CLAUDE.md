# CLAUDE.md — Boardroom

> Memory + quick reference for this project. Loaded automatically by Claude Code in
> this repo. For the full living spec see **`docs/SCOPE.md`** (kept in sync on every change).

## What this is

**Boardroom** is an autonomous, multi-agent capital-allocation system funded with
~$200+ CAD (Canadian resident). **Several times a day** (4× by default) it convenes a
"boardroom" of agents, looks at real crypto + equity data, and decides where capital
goes. Live (real money) as of 2026-06. **Crypto-first since 2026-07:**

- **Crypto (Kraken) = fully autonomous, auto-trades live, buy AND sell.** Analysis on
  deep USD-pair data (~37 coins); execution settles in `ACCOUNT_BASE_CURRENCY`
  (`exec_pair_for`; a coin with no market in that quote is excluded BEFORE funding
  via the executability gate — `tradable_pairs_for`, live Kraken pair list, fails
  open to a clean execution error). **CAD-funded = only ~5 coins buyable (BTC, ETH,
  SOL, XRP, PEPE); USD-funded = whole universe.** Risk unit is ALWAYS CAD: USD
  sizing converts via live USDCAD rate at the broker boundary (`quote_to_cad_rate`,
  no rate = no trade), cash/holdings valued back to CAD. Up to
  `MAX_FUNDINGS_PER_CHECKPOINT` (2) DIFFERENT assets fund per checkpoint, and the
  per-asset aggregate cap (`ASSET_MAX_EXPOSURE_PCT`, 20%) diverts capital to the
  next-best coin once a winner holds its max share — re-buying below the cap stays
  allowed (no hard no-rebuy rule).
- **Equities = SUNSET** (`ENABLE_EQUITIES=false` default): no stock scans, no
  recommendations, no IBKR dependency. The advisory recommended-portfolio code is
  dormant, not deleted — flip the flag to resurrect it.

## The one rule that governs everything

**The LLM reasons; code calculates.** No quantitative field the system acts on
(expected return, win probability, size, max loss, cost) is ever an LLM free-form
guess — all come from deterministic, unit-tested functions on real data. The LLM
only writes narrative and adjudicates qualitative calls. Enforced in the schema layer.

## Divisions (pitch ideas) → Agents (decide)

- **Yield** (crypto/Kraken) = the floor every idea must beat · **Event** (crypto/Kraken,
  auto-trades) · **Directional** (stocks/ETFs, **SUNSET** behind `ENABLE_EQUITIES`) ·
  **Effort** (disabled).
- **Funding rule is by VENUE** (`run_once`): only **Kraken (crypto)** pitches are
  auto-funded; every **IBKR (equity)** pitch is advisory and feeds the recommendation
  engine. So a crypto **Momentum** breakout trades live, while the same division's stock
  pitches never do. Directional (IBKR) is advisory by construction.
- **Recommendation engine** (`boardroom/recommend.py`): ranks the advisory equity pitches
  into a weighted **target portfolio** (score-proportional, per-trade-capped, within the
  deployable cap), reads the real IBKR holdings (`IBKRBroker.get_positions()`), and diffs
  them → buy/sell/trim/hold actions. `agents/advisor.py` writes the plain-English
  "buy COST / sell SNDK" note. Code computes every number; the LLM only narrates. Persisted
  to `recommendations` (migration 0009). Dashboard UI for it was REMOVED with the
  crypto-only dashboard (2026-07-02) — resurrect from git history alongside the flag.
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
- **Scanned universe** (factory.py + `data/sources.kraken_usd_universe`): the wide
  scan is DYNAMIC — every liquid USD-quoted Kraken pair (24h volume ≥
  `CRYPTO_MIN_USD_VOLUME_24H`, capped at `CRYPTO_UNIVERSE_MAX` deepest books;
  stables/fiat/dark-pools/tokenized-equities excluded), refreshed per checkpoint;
  curated ~37 is the fallback. DOGE trades as Kraken's `XDGUSD`. Execution via
  `exec_pair_for` — no market in the account quote → gate-skip before funding.
  Equity universe only loads when `ENABLE_EQUITIES=true`. Long-only.
- **CEO** ranks the *fundable* (crypto) pitches deterministically vs hurdle + track record;
  default HOLD; funds up to `MAX_FUNDINGS_PER_CHECKPOINT` (2) best DIFFERENT-asset ideas,
  respecting the per-asset aggregate cap. **Risk Manager** adversarially vetoes.
  **CFO/Strategist** studies the scoreboard, writes a review each checkpoint.

## Money & safety (non-negotiable)

- **LOTTO MANDATE (owner, 2026-08-05 "BIG BIG BIG — zero is fine")**: caps opened to
  the structural max — deployable 98%, per-trade/per-asset 100%, order floor 40% of
  book, stops capped 10%, FULL Kelly, shrinkage floor 0.7, ratchet OFF. The whole
  book can ride one idea. Breakers are MALFUNCTION TRIPWIRES only now (daily 50%,
  drawdown 80%) — they halt a runaway bug, not a bad bet the owner accepted. The
  lotto shape: cut losers at ~10% fast, ride winners on uncapped trails, re-roll up
  to 3 ideas × 8 checkpoints/day. **Vol tilt** (`VOL_TILT_STRENGTH` 0.5 /
  `VOL_TILT_REF` 5%): at comparable edge the ranking prefers the wildest liquid
  movers (12%-vol coin scores 2.0×, 2%-vol major 1.2×) — leverage-like swings
  from the asset itself; actual margin/leverage is PROHIBITED for this account
  (OSC restricted-dealer terms, same regime as the BLESS CA:ON rejection). Circuit breakers
  on loss/drawdown. **Sizing resolves against the LIVE Kraken book** (cash + coins −
  reserve, `live_investable_cad`) so deposits flow in automatically at the next
  checkpoint — `STARTING_PORTFOLIO_CAD` is only the offline fallback + ratchet/P&L
  baseline. Ratchet stays realized-basis (deposits never swept); drawdown uses the
  live `equity_hwm_cad` (migration 0014).
- **Aggression schedule** (`ceo/engine.py`): bolder while small, calmer as it grows. Two
  knobs ride an equity ramp ($1000→$5000): (1) the CEO's **deviation bar** is ZERO while
  small (0.0 ≤ $1000, go-big 2026-08-04 — post-shrinkage scores are 0.001-scale, so any
  positive bar meant the floor always won) rising to conservative (0.02 ≥ $5000) — it
  funds ANY surviving positive-net-edge crypto idea while tiny; (2) the **crypto Event position cap** is BOLD while
  small (up to the 20% per-trade max, `EVENT_HARD_CAP_PCT_SMALL`) tapering to 5% as equity
  grows. Tunable via `CEO_DEVIATION_THRESHOLD*` / `EVENT_HARD_CAP_PCT_SMALL` /
  `AGGRESSIVE_BELOW_CAD` / `CONSERVATIVE_ABOVE_CAD`. The **daily-loss (50%) and drawdown
  (80%) malfunction tripwires are NEVER scaled** — they're the "don't lose it all in one day"
  backstop regardless of aggression.
- **Leash floor + revive** (2026-08-04 go-big mandate): a non-retired division's leash
  floors at `LEASH_MIN` (0.15) — never zero (zero was an absorbing state that silently
  parked the whole system). Calibration runs on a rolling `CALIBRATION_WINDOW` (30) of
  recent outcomes; retirement (real kill switch, audited) needs BOTH windowed mean <
  `RETIRE_MEAN_BELOW` (0.35) AND net-negative money over ≥ `RETIRE_MIN_SAMPLE` (30);
  `n_resolved`/`net_vs_floor_cad` now recomputed from real history each update (were
  stuck at 0 — retirement could never fire). **`boardroom revive`** lists division
  states / revives one (fresh flat prior, leash 0.5) — the only way back.
- **Growth ladder** (`adaptive/growth.py`): every checkpoint maps total equity
  (investable + reserve) to a named tier — **signals only**, no behavior change.
  Rungs align with the aggression ramp ($1k/$5k). Intraday tick-level exits are
  BUILT and always-on at every tier (2026-08-06 — the $969 LIT peak went unsold
  while they were gated at $2.5k); canopy ($5k) still flags intraday surge
  ENTRIES as eligible — `requires_human`, never auto-enabled.
- **Conviction floor** (2026-08-05 "we're ready"): a funded order is bumped to
  **max(`MIN_ORDER_CAD` 25, `MIN_ORDER_PCT` 10% × book)** — positions are a real
  slice of equity (~$68 on a $676 book) and scale as it grows, clamped to the
  per-trade cap so the envelope holds. `MIN_ORDER_PCT=0` reverts to $25 floors.
- **Minimum-order floor** (`MIN_ORDER_CAD`, default 25): a small-conviction crypto order is
  bumped up to the exchange minimum so it actually fills — clamped to the per-trade cap, so
  it never breaches the risk envelope. Crypto trades execute in **CAD pairs** (account is
  CAD-funded; `exec_pair_for` maps USD→CAD).
- **Capital rotation** (`_rotate_capital`, owner mandate 2026-07-10): a strong
  leftover idea can take the WEAKEST holding's money when its net edge beats the
  holding's remaining edge by > `ROTATION_EDGE_MULTIPLE` (1.5×) the switching
  cost. Sell = forced resolution (real outcome, exit reason `rotation`, learning
  loop scores it); buy = full CEO gauntlet. Max ONE rotation/checkpoint;
  `ENABLE_ROTATION=false` kills it. Growth-over-sitting, but never churn.
- **Auto-sell / exits** (`graph/resolution_loop.py`): each checkpoint the resolution loop
  checks open crypto positions and **places a real Kraken SELL** to close on a **stop-loss**
  (close ≤ −stop, stop CAPPED at `EXIT_STOP_CAP_PCT` 6%), a **trailing exit** (2026-08-04,
  `EXIT_TRAIL_ENABLED` default true: reaching the take-profit `EXIT_TP_R_MULTIPLE` 1.5× stop
  ≈ +9% no longer sells — it ARMS a trailing stop at the position's capped stop distance;
  upside uncapped, rides past the horizon, exits on the first close that gives back the
  trail from its peak; disabled = old hard TP; migration 0015 — the predicted band is the
  Critic's scoring window only now, legacy rows fall back to band-top), or **horizon
  elapse** (unarmed positions only). **Prediction shrinkage** (2026-07-27): every pitch's
  expected return is blended toward the division's realized mean
  (`_shrink_expected_return`, weight `max(prior_n/(prior_n+n), min_weight)`,
  knobs `PREDICTION_SHRINK_PRIOR_N`/`PREDICTION_SHRINK_MIN_WEIGHT`) BEFORE the cost
  gate/ranking/sizing — the month-one failure was +7.9% predicted vs −0.8% realized.
  It sells the exact filled qty (`OpenPosition.qty`, migration 0011). A position is only
  finalized (P&L booked, tracking row deleted) when the sell actually executes — a rejected
  sell leaves it open to retry, so the record never claims a sale that didn't happen
  (exception: `exit_no_balance` — the balance was already swept by a clamped sibling
  sell, so the row books its outcome and voids instead of erroring forever).
  **Exits evaluate on INTRADAY bars** (`EXIT_BAR_MINUTES` 60; 2026-08-06 — daily candles
  hid the LIT +75% round-trip from four checkpoints): the trail arms and rides off bar
  HIGHS, measures from the fill-time `entry_price`, and persists
  `entry_price`/`peak_return`/`trail_armed` per position (migration 0004) so a ride
  survives restarts and rolling windows. Between checkpoints the **exit watcher**
  (`graph/exit_watch.py`, hosted in `boardroom poll` + the continuous `boardroom run`
  loop; `EXIT_WATCH_MINUTES` 15) re-checks the held book and sells the moment a trigger
  prints — then convenes an immediate re-entry checkpoint (`EXIT_REENTRY_ENABLED`) so
  the freed cash is re-bet at once. The exit
  price lookup falls back through the base asset (SOLCAD position ↔ SOLUSD series),
  then — live mode only — fetches the HELD symbol's OHLC directly from Kraken's
  public endpoint (`resolution_fallback_fetch`) when the coin churned out of the
  scanned universe (six coins sat unmanaged that way on 2026-07-26); an
  unpriceable position audits `resolution_no_data`, never a silent skip. A
  tripped breaker halts new risk but still runs the read-only housekeeping
  (portfolio snapshot + orphan reconciliation) — they no longer freeze while
  breakers are tripped.
- **Execution truth** (`fills` table, migration 0012): every broker fill (buy AND
  sell, live AND paper) persists the instant the broker returns — BEFORE any other
  write — with qty/price/fee/txid. A mid-run crash can never lose the record of
  money moving again (one did on 2026-07-01: live SOLCAD buy, decision+position
  lost, reconstructed manually).
- **Run health** (`runs` table): every checkpoint records started→ok/**crashed**
  (+error), the breaker evaluation, and a **venue reconciliation** (Kraken
  holdings vs tracked positions; orphans → `reconciliation_untracked` audit +
  dashboard alert). Act on an orphan with **`boardroom adopt`**: list them, or
  `boardroom adopt --asset <SYM> --sell --confirm-live` to flatten one back to
  cash (`Orchestrator.flatten_holding` — exact held qty via `Order.base_qty`,
  account-quote pair, on-exchange only, two-key live gate). **Circuit breakers are evaluated inside every run** and force
  a deterministic HOLD when tripped. NaN/Inf sanitized before every Supabase
  write (`_json_safe`). Poller writes `system_state.poller_seen_at` heartbeat.
- **Gains ratchet** (`RATCHET_CAPTURE_PCT`, owner-set 0 = OFF): when enabled, sweeps a
  fraction of new highs into an **untouchable reserve**; the existing reserve never releases.
- **Withdrawals DISABLED on every venue** — no transfer code path exists. Keys are
  trade-only and per-venue isolated (Kraken ⟂ equities).
- **Live gate**: a real order needs BOTH `LIVE_TRADING=true` AND per-call `--confirm-live`.
  Otherwise every run is a dry-run simulation. Enforced in the execution layer
  (`Orchestrator.effective_live`) for buys and sells alike.

## Scheduling & market hours

- **Checkpoints run several times a day** (`CHECKPOINT_TIMES`, default
  `01:30,04:30,07:30,10:30,13:30,16:30,19:30,22:30` UTC = 8×/day, every 3h around the
  clock (2026-08-05 autopsy: stops only evaluate at checkpoints, and daily-close gaps
  blew −20% through the 6% cap — denser checkpoints tighten real stops AND add shots) while
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
  `tests/` (251 passing; `python -m pytest`).
- **Portfolio view** (`boardroom/portfolio.py`): each checkpoint (and `boardroom
  balances`) snapshots real holdings — `KrakenBroker.get_positions()` (coins priced
  in CAD + intraday change; IBKR book still captured in the payload but no longer
  rendered) — persisted to `portfolio_snapshots` (migration 0010); dashboard
  "Your portfolio" section shows the Kraken book only.
- **Dashboard**: `dashboard/` (Next.js 14 on Vercel, reads Supabase read-only).
  **Crypto-only (2026-07-02)** — no stocks/IBKR UI; health-strip equity counts
  Kraken cash only. Layout: **health strip** (mode, equity, countdown, last-run
  status incl. crashes, breaker status, scheduler/poller liveness) + three
  sections: **1 Executed** (fills, paper behind a toggle, orphan alert) ·
  **2 Positions** (cost basis, value, unrealized, exit plan) · **3 Reasoning log**
  (per-checkpoint cards, crashed runs inline).
  "Ask the Boardroom" chat = read-only, needs `ANTHROPIC_API_KEY`.
- **Docs loop**: `/docs` renders `docs/SCOPE.md` + `OPERATIONS.md` + `RUNBOOK.md`
  from the repo — `dashboard/scripts/sync-docs.mjs` copies them into
  `dashboard/content/` on every build (npm pre-hooks), so every merge to main
  auto-updates the dashboard docs. Keep updating SCOPE.md in the same commit as
  behavior changes; the deploy pipeline handles the rest.
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
- Cadence is 8×/day (every 3h) for ENTRIES — more shots for crypto while small; the cost
  gate still blocks any trade that doesn't clear its fees, so frequency can't become
  fee-bleed churn. EXITS are intraday and always-on (the exit watcher, every 15 min —
  the "risk-only crypto exit" upgrade shipped 2026-08-06, plus an immediate re-entry
  checkpoint whenever it frees capital).
