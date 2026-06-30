# Boardroom

> An autonomous multi-agent **capital-allocation system** — a decision-making
> organization, not a trading bot. Specialist *divisions* hunt opportunities
> backed by **real computed math**, a single *CEO* agent decides where ~$200+ CAD
> goes (usually nowhere), and a *measurement* layer scores every decision and
> feeds results back so the system adapts. It runs **several times a day**.
>
> **Two modes by venue:** crypto (Kraken) is **fully autonomous — it auto-trades
> live**; stocks (IBKR) are **advisory only** — the system publishes a recommended
> portfolio and diffs it against your real holdings ("buy Costco, sell SanDisk"),
> but you place the stock orders yourself.
>
> Canada build · Kraken + Interactive Brokers · live-capable, gated behind a flag.

**The governing law (scope §5): the LLM reasons; CODE calculates.** No
quantitative field the system acts on is ever produced by an LLM's free-form
judgment. Every number traces to a deterministic, unit-tested function on real
market data. The language model only writes narrative and adjudicates genuinely
qualitative calls.

---

## Status — what's built

| Milestone | What | State |
|---|---|---|
| M0 | Repo, config, hard caps, schemas, broker/division interfaces | ✅ |
| M1 | Skeleton decision loop (divisions → CEO → execute-stub), LangGraph wiring | ✅ |
| M2 | Grounding: data layer, feature functions, prediction models, backtest gate | ✅ |
| M3 | Adversarial risk manager (code-driven vetoes the LLM can't sweet-talk) | ✅ |
| M4 | Measurement (ROI vs **floor** and **buy-and-hold**, Critic, cost gate) + Supabase | ✅ |
| M5 | Adaptive engine (calibration → trust + leashes, refit guardrails, retirement, shadow) | ✅ |
| M6 | Kraken + IBKR adapters behind the broker interface (live-gated) | ✅ code · ⏸ live smoke test needs the gateway running |
| M7–M10 | Event live · go-live floor-dominant · ratchet · Effort | later |

**221 tests pass** across the spine (features, CEO logic, calibration math,
measurement, caps, the recommendation engine, the full loop). Everything runs
**offline in dry-run** today: `LIVE_TRADING` defaults `false` and execution is
stubbed until you fund accounts and wire venues.

---

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # core + test deps
cp .env.example .env             # then paste your keys (see below)

boardroom doctor                 # check config + the safety rails
boardroom preflight              # read-only venue connectivity + live GO/NOT-READY
boardroom backtest --synthetic   # run the backtest gate on offline data
boardroom decide --synthetic     # run one daily decision loop, offline
boardroom decide                 # same, using real keyless public data feeds
```

**Going live:** see [`RUNBOOK.md`](RUNBOOK.md). **Crypto auto-trades on Kraken.**
**Stocks are advisory** — the system reads your **Interactive Brokers** holdings
(Client Portal Gateway, run locally) and publishes a recommended portfolio, but
never places equity orders. Live crypto trading needs egress to `api.kraken.com`;
the IBKR gateway on `localhost:5000` is used read-only (holdings + cash) for the
recommendation diff — easiest is to run on your own machine.

`boardroom decide` prints the day's pitches, the trust-weighted ranking, the
floor hurdle, and the CEO's verdict — one of **FUND / FUND_NONE / HOLD**. Most
days the right answer is HOLD (stay in the floor); that is by design, not a bug.

---

## Architecture

Three layers, three loops (scope §2, §10):

```
 Divisions (sensory organs)        CEO (the cortex)            Measurement (conscience)
 ─────────────────────────         ─────────────────          ────────────────────────
 Yield  → the floor/hurdle         price vs the floor          Performance: ROI vs floor
 Event  → asymmetric crypto        null default = HOLD           AND vs buy-and-hold
   (auto-trades on Kraken)         trust = demonstrated        Critic: calibration,
 Directional/Momentum → stocks       calibration, not vibes      process-vs-luck
   (ADVISORY — recommend only)     conviction sizing (crypto)  Recommendation engine:
 Effort → non-market (disabled)                                  rank → diff vs IBKR
        every pitch is COMPUTED ───────────►  ◄─────────── Adaptive engine feeds back
```

- **`boardroom/data`** — pull real fresh data (Kraken public OHLC, Stooq daily),
  freshness/sanity-check it, hash it. Stale/insane data → the division abstains.
- **`boardroom/features`** — pure, unit-tested signal functions (momentum, vol,
  mean-reversion z, RSI, liquidity, …). The numbers start here.
- **`boardroom/models`** — explicit, inspectable feature→(expected_return,
  win_probability) maps. Backtest-fittable. Versioned.
- **`boardroom/divisions`** — pitch-or-abstain machinery; computed fields only.
- **`boardroom/agents`** — the thin LLM layer: a narrator, the CEO's rationale,
  the adversarial risk manager, the Critic's post-mortems. **Prose only.**
- **`boardroom/ceo`** — deterministic hurdle, trust-weighting, conviction sizing,
  ranking, and the null-default arbitration (crypto funding only).
- **`boardroom/recommend.py`** — the advisory **equities recommendation engine**:
  ranks advisory stock pitches into a weighted target portfolio and diffs it against
  the real IBKR holdings → buy/sell/trim/hold actions (code computes; LLM narrates).
- **`boardroom/risk`** — the cost model (a *decision input*), and the hard caps +
  circuit breakers the CEO **cannot** override.
- **`boardroom/measurement`** — the two scorers, the two benchmarks.
- **`boardroom/adaptive`** — calibration posteriors, risk leashes, division
  retirement, model re-fit — all behind anti-overfitting guardrails.
- **`boardroom/graph`** — the LangGraph decision loop + the performance/learning loops.

---

## The safety rails (in code, outside any agent's control)

- **`LIVE_TRADING` defaults `false`.** The full loop runs in dry-run until you
  flip it *after* funding. The CLI additionally requires `--confirm-live`.
- **Hard caps the CEO can't widen** — expressed as **percent of portfolio value**
  so they scale as the account grows (a $40 cap at $200 becomes $400 at $2,000):
  total deployable (80%), per-trade max (20%), the Event hard cap (5%), daily-loss
  limit (6%), max drawdown (15%), fee-drag limit (5%). A breach forces **all
  capital back to the floor**. Full model: [`docs/OPERATIONS.md`](docs/OPERATIONS.md).
- **Withdrawals disabled everywhere.** Brokers expose `supports_withdrawal` only
  so we can assert it is `False` at startup.
- **Kraken and the equities venue are isolated** accounts/sessions — a leak in one
  can't touch the other.
- **Secrets via env only.** `.env` is gitignored; `.env.example` is the template.

---

## Credentials — and exactly how to scope them

Generated by **you**, pasted into `.env` only — never a prompt, never the repo.
Scope each to the **minimum** permission. A trading key with withdrawal
permission is the single most dangerous thing in this project; don't create one.

| Env var | Powers | Scope it to |
|---|---|---|
| `ANTHROPIC_API_KEY` | every agent's reasoning | n/a (usage-billed) |
| `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` | state + metrics | data only, **no** trading power |
| `KRAKEN_API_KEY` + `KRAKEN_API_SECRET` | Yield + Event | **trade + staking; DISABLE withdraw** |
| `IBKR_ACCOUNT_ID` (+ Client Portal Gateway session) | reading equity holdings + cash for the recommendation diff (advisory — **no equity orders**) | read-only is sufficient |
| `MARKET_DATA_API_KEY` | richer Directional signals | read-only (optional) |
| `CHECKPOINT_TIMES` | checkpoint schedule (UTC, default `13:30,15:30,17:30,19:00` — 4×/day) | n/a |

> The system runs **without** the Anthropic key (agents fall back to templated
> prose) and **without** Supabase (it uses an in-memory repository). Those are
> for development; production wants both.

---

## Supabase

State lives in a dedicated **`boardroom`** Postgres schema on the project at
`https://qyaekaifodgiaxyztpdt.supabase.co` (the `public` schema is untouched).
Tables: `division_state`, `pitches`, `decisions`, `outcomes`,
`performance_snapshots`, `weekly_reports`, `audit_log`, `recommendations`. Migrations are in
[`supabase/migrations`](supabase/migrations). RLS is **enabled with no policies**
— anon/public access is denied; the backend's service key bypasses RLS.

If the Python client can't see the schema (`PGRST106`), add `boardroom` to
**Dashboard → Settings → API → Exposed schemas** (it's already set via SQL, but
the dashboard toggle is the durable home for it).

---

## Wiring the venues (Milestone 6)

The broker interface (`boardroom/brokers/base.py`) is venue-agnostic.
`KrakenBroker` (crypto — auto-trades) and `IBKRBroker` (equities — used **read-only**
for holdings + cash; `get_positions()` feeds the recommendation diff) are
**implemented** (`boardroom/brokers/`). Each sits behind two hard safety
properties: `supports_withdrawal` is `False` with no withdraw/transfer code path,
and a live order is placed **only** when the per-call `live` flag **and** the
global `LIVE_TRADING` flag **and** credentials are all present — otherwise it
simulates (no network, no money). In the current model only crypto is funded, so
IBKR never receives an order regardless. `make_brokers(prefer_live=True)` selects real
adapters vs stubs; `build_default_org(prefer_live_brokers=True)` injects them.

To run the **live smoke test** (smallest possible real order), set in the
environment / `.env`:

1. **Kraken** — `KRAKEN_API_KEY` + `KRAKEN_API_SECRET`, scoped **trade + staking,
   withdrawals disabled**.
2. **Interactive Brokers** — run the **Client Portal Gateway** locally and log in at
   `https://localhost:5000` (session-based; no static API key), then set
   `IBKR_ACCOUNT_ID` (and `IBKR_GATEWAY_URL` if not the default). Enable trading;
   keep transfers/withdrawals off. See [`RUNBOOK.md`](RUNBOOK.md) for the gateway
   setup.

Then flip `LIVE_TRADING=true` and run `boardroom decide --confirm-live`. Until
then the same code runs fully in dry-run.

---

## Reading the weekly report

`boardroom report` produces a plain-language readout: ROI **vs the floor** and
**vs buy-and-hold**, per-division attribution, calibration movement, what the
adaptive engine re-weighted or benched, and the circuit-breaker status. It is
your dashboard and your trust-check on the machine.

---

## Tests

```bash
pytest -q          # 189 tests: features, CEO logic, calibration, measurement, caps, the loop
```

The spine — feature functions, CEO decision logic, and the calibration math — is
the most heavily tested by design (scope §13).

---

*Personal learning project. Goal: a disciplined, grounded, self-measuring,
adaptive decision system that operates with real stakes — not "beat the market."*
