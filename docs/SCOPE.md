# Boardroom — Living Scope

> **This is the canonical, continuously-updated scope.** It supersedes the original
> `Boardroom_Scope.docx` and is kept in sync with the code as the system evolves.
> When behavior changes, this file changes in the same commit.
>
> **Last updated:** 2026-07-01 · **Status:** LIVE (real capital) · **Funding:** ~$200+ CAD

---

## 1. What Boardroom is

An autonomous, multi-agent capital-allocation system. **Several times a day** (4× by
default) it convenes a "boardroom" of specialized agents, looks at real crypto and
equity market data, and decides where a small pool of capital should go — **usually
nothing**. It is floor-first and skeptical of its own ideas, but tuned to act readily
on crypto while the account is small (see §4, the aggression schedule).

**Boardroom is a crypto agent (since 2026-07).** The equity leg is **sunset**:
no stock scans, no recommendations, no IBKR dependency — all effort goes into
deeper crypto analysis. The advisory stock code remains dormant behind
`ENABLE_EQUITIES=true` (flip it to resurrect the recommended-portfolio /
IBKR-diff feature), but by default:

- **Crypto (Kraken) — fully autonomous.** The divisions auto-trade live within
  the caps (default HOLD). Analysis runs on deep **USD-pair data** (~37 coins);
  execution settles in the **account's funding currency**
  (`ACCOUNT_BASE_CURRENCY`) — and a coin with no market in that quote is
  **excluded before funding** (checked against Kraken's live pair list) so it
  never wastes a slot; if that lookup fails, the order still errors cleanly
  and the next idea gets the capital.
- **Funding currency & FX (2026-07-03).** CAD-funded, only ~5 of the 37 coins
  have a Kraken CAD market (BTC, ETH, SOL, XRP, PEPE); **USD-funded, the whole
  universe is buyable.** To switch: convert CAD→USD inside Kraken, set
  `ACCOUNT_BASE_CURRENCY=USD`. The system's **risk unit stays CAD** — caps,
  equity, P&L — with conversion at the broker boundary: order sizing divides
  the CAD notional by the live USDCAD rate (**no rate = no trade**, never
  1:1), cash sums **every fiat balance code** Kraken reports (ZCAD/ZUSD, plain
  CAD/USD, `*.F` Rewards-enrolled, `*.HOLD` deposits on hold) valued in CAD,
  and holdings are priced on the quote market then converted. Sizing at 1:1
  would silently over-buy ~37%.
- Up to **`MAX_FUNDINGS_PER_CHECKPOINT` (default 2) different coins** can be
  funded per checkpoint, and a **per-asset aggregate cap**
  (`ASSET_MAX_EXPOSURE_PCT`, default 20% of the book) stops any single trending
  coin from eating every slot — without ever banning re-buying a coin the
  system still likes.

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
| **Event** | Crypto | Kraken | auto-trades | Rare dislocation/catalyst crypto bets. |
| **Crypto Trend** | Crypto | Kraken | auto-trades | **Always-on** trend/mean-reversion long — proposes whenever there's positive edge, so the system is regularly in the market (not just on rare triggers). |
| **Momentum** | Crypto | Kraken | auto-trades | Volume-confirmed breakouts on the crypto universe. |
| **Directional** | Stocks / ETFs | IBKR | **SUNSET** | Dormant behind `ENABLE_EQUITIES` — advisory recommended-portfolio only, never auto-funded. |
| **Effort** | — | — | disabled | Disabled. Reserved. |

A pitch carries computed numbers (code) plus a short narrative (LLM). Quant fields
are never LLM guesses.

**Scanned universe (crypto-first, whole-exchange).** Analysis runs on
**USD-quoted Kraken pairs** — that's where the deep, liquid OHLC history lives.
Since 2026-07-09 the wide scan is **dynamic**: every USD pair Kraken actually
lists with ≥ `CRYPTO_MIN_USD_VOLUME_24H` ($250k) of 24h volume, capped at the
`CRYPTO_UNIVERSE_MAX` (150) deepest books, refreshed from the live exchange at
every checkpoint — stablecoins, fiat crosses, dark pools, and tokenized
equities excluded. A surging coin can't hide outside a hand-curated list
anymore (and DOGE is finally in, under Kraken's own `XDGUSD` name). The old
curated ~37 remains the fallback if the exchange lookup fails. **Execution settles in the account's funding currency** (`exec_pair_for`,
`ACCOUNT_BASE_CURRENCY`). A coin with no market in that quote is filtered out
**before the CEO ranks it** — the executability gate checks Kraken's real pair
list for the quote (public AssetPairs, cached per process), audits a
`no_exec_market_skip`, and shows the reason in the session — so an unfillable
coin (UNIUSD did this three times from the CAD account) never eats one of the
day's funding slots. If the pair-list lookup fails, the gate fails open and
execution still errors cleanly. Every symbol runs the same grounded model
+ risk/cost gates.

**Diversification is structural, not a ban.** Two rules replace winner-take-all:
(1) up to `MAX_FUNDINGS_PER_CHECKPOINT` (default 2) ideas fund per checkpoint,
each clearing the bar and every cap independently, always **different assets**;
(2) the **per-asset aggregate cap** (`ASSET_MAX_EXPOSURE_PCT`, default 20%)
lets the CEO keep adding to a coin it still likes until that coin holds the max
share of the book — then its pitches step aside (`asset_cap_skip` audit, shown
with the reason in the session) and capital flows to the next-best coin.

### 2a. The recommendation engine (advisory equities — SUNSET)

> **Sunset 2026-07.** Everything below is dormant unless `ENABLE_EQUITIES=true`:
> no equity scans run, no recommendations are generated, and the dashboard hides
> the stocks section once the last recommendation ages out. The code is kept,
> not deleted, so the stock leg can return when the account justifies it.

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

**Aggression schedule (bold while small, calmer as it grows).** Two levers ride an
equity ramp (`$1000`→`$5000`): the CEO's **deviation bar** (how readily it leaves the
floor) is **exactly ZERO under $1000** — any idea with genuine positive net edge that
clears cost, the yield floor, and the Risk Manager gets funded (go-big 2026-08-04:
post-shrinkage scores live at the 0.001–0.005 scale, so even a 0.001 bar meant the
floor won every checkpoint) — rising to the conservative 0.02 as equity grows; and
the **crypto Event position cap** is bold while small (up to the 20% per-trade max,
`EVENT_HARD_CAP_PCT_SMALL`) tapering to the conservative 5% as equity grows. This is
deliberate — small play-money account, willing to take real risk for growth, auto-de-risking
into the thousands. **The daily-loss (6%) and max-drawdown (15%) breakers are never scaled**
— they remain the catastrophe backstop at every account size.

**Circuit breakers** halt new risk when the daily-loss or drawdown limits trip.

**Gains ratchet & reserve.** As realized equity makes new highs, a fraction of the
gain is swept into an **untouchable reserve** — locking in progress so the system
plays with house money over time.

**Growth ladder (milestones — signals only).** Every checkpoint, total equity
(investable + reserve, so the ratchet can never demote the system) is mapped
through a pure, deterministic ladder (`adaptive/growth.py`) to a named tier.
The $500/$5,000 rungs deliberately match the aggression schedule's ramp, so the
ladder *narrates* the same progression the sizing already rides — it changes
**no trading behavior**. What it adds is the `requires_human` unlock layer:

| Tier | Total equity ≥ | Eligible to build/enable (human call) |
| --- | --- | --- |
| 0 · seed | $0 | — |
| 1 · sprout | $500 | — |
| 2 · sapling | $1,000 | — |
| 3 · grove | $2,500 | intraday **tick-level** exits (today exits evaluate on daily closes at checkpoints) |
| 4 · canopy | $5,000 | + intraday **surge entries** (today entries happen only at checkpoints) |

Each checkpoint audits a `growth_tier` event and the session carries the tier
(current rung, next unlock and the equity it needs), so the audit trail and
dashboard show when the account has *earned* a capability. Nothing auto-enables:
crossing a threshold makes the feature worth its fee drag; turning it on stays a
human decision requiring code/scheduler changes.

---

## 5. When it runs — and the market-hours rule

- **Several checkpoints per day** — `CHECKPOINT_TIMES`, default
  **`01:30,04:30,07:30,10:30,13:30,16:30,19:30,22:30` UTC** (8×/day, every 3h — crypto
  is 24/7; more shots for crypto while the account is small). Each checkpoint
  auto-trades crypto AND refreshes the advisory stock recommendation + IBKR
  holdings diff + portfolio snapshot.
- **The exit watcher runs BETWEEN checkpoints** (`EXIT_WATCH_ENABLED`, default on;
  every `EXIT_WATCH_MINUTES`, default 15). It prices ONLY the held book on
  **intraday bars** (`EXIT_BAR_MINUTES`, default 60 — the forming candle's close is
  the live price) and executes any stop / take-profit / trailing exit immediately,
  at any hour. Sells only — no LLM, no pitches, no new entries. Why it exists: on
  2026-08-06 the book rode LIT +75% overnight to ~$969 and round-tripped to a
  −14% stop-out while four checkpoints watched — exits evaluated on daily closes,
  so the whole move lived inside one candle nothing could see. Trailing state
  (fill-time entry price, peak-off-highs, armed flag) is persisted per position
  (`open_positions.entry_price/peak_return/trail_armed`, migration 0004) so a
  ride survives restarts and rolling bar windows. When the watcher frees capital
  it convenes a **re-entry checkpoint** immediately (`EXIT_REENTRY_ENABLED`,
  default on) — sell the top, re-bet the cash on the current best idea instead of
  idling until the next scheduled slot.
- Crypto (Kraken) trades **24/7** — the Yield/Event legs can act at any checkpoint.
- Stocks are **advisory** — nothing auto-executes on IBKR, so there's no equity-fill
  timing concern. The recommendation is computed off the latest daily bars at each
  checkpoint regardless of session.
- **Market-hours guard** still exists as defense in depth (it would hold any live
  equity order placed while the market is closed), but equities no longer auto-trade.

> **Why a few times a day and not constant?** See §9.

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
3. **Adaptive loop (ongoing):** trust/leash per division adjusts from calibration
   judged on a ROLLING window (`CALIBRATION_WINDOW`, 30) of the most recent
   outcomes — old results age out in both directions. A non-retired division's
   leash floors at `LEASH_MIN` (0.15), never zero: it always keeps trading at
   minimum size so it can earn trust back (zero was an absorbing state that
   silently shut the system off). Retirement — the real kill switch — needs
   BOTH windowed miscalibration (mean < `RETIRE_MEAN_BELOW`, 0.35) AND a
   net-negative record over ≥ `RETIRE_MIN_SAMPLE` (30) resolutions; it is
   audited, and only the human `boardroom revive` brings a division back
   (fresh flat prior, working leash). The CFO studies the whole picture and
   recommends structural changes for human sign-off.

---

## 7. Venues & safety

| Property | Guarantee |
| --- | --- |
| Withdrawals | **Disabled everywhere.** No transfer/withdraw code path exists. Trade access cannot move your money. |
| Stocks | **No equity execution path at all.** The IBKR integration is read-only (holdings + cash); the system only *recommends* stock trades. |
| Keys | Trade-only, scoped per venue. Kraken and the equities account are **isolated** — a leak in one can't touch the other. |
| Live gate | A live (crypto) order requires **both** the global `LIVE_TRADING=true` flag **and** a per-call `--confirm-live`. Otherwise every run is a dry-run simulation. |
| Orphan reconciliation | Each checkpoint compares Kraken's real holdings against tracked open positions; a coin held with no tracked position is an **orphan** (crash residue / an outside buy) the auto-sell loop can't manage. It's surfaced as a dashboard alert, and **`boardroom adopt`** reconciles it. |

**`boardroom adopt`.** Lists untracked orphans and can flatten one back to cash:
`boardroom adopt` (list) · `boardroom adopt --asset AAVE --sell --confirm-live`
(sell the whole balance). The sell settles in the account's quote currency and
sells the exact held quantity; it stays on-exchange — a trade, never a
withdrawal — behind the same two-key live gate as any other live order.

---

## 8. The dashboard

A Vercel-hosted dashboard reads the logged state from Supabase (read-only),
password-gated, organized as a **health strip + three glanceable sections**
(**crypto-only since 2026-07** — the stocks/IBKR UI was removed with the
equities sunset; resurrect it from git history if the stock leg returns):

1. **Executed** — confirmed fills only (`fills` table, written the moment the
   broker returns: side, qty, price, notional, fee, live/paper, exit reason).
   Paper trades sit behind a toggle. A reconciliation alert appears when the
   venue holds coins with no tracked position behind them.
2. **Positions** — every open position with cost basis, current value,
   unrealized P&L, and the exit plan fixed at entry (stop / take-profit /
   horizon date), plus the full venue holdings snapshot.
3. **Reasoning log** — one expandable card per checkpoint: every idea with the
   reason it was funded / vetoed / passed over, the CEO's rationale, and the
   CFO's standing view. **Crashed runs appear inline in red** (`runs` table).

The health strip on top shows mode (LIVE/armed/dry-run), live equity, the
next-checkpoint countdown, last-run status (including crashes), breaker status
(**"clear" only when actually evaluated**), and scheduler/poller liveness with
a stuck-"Run now" warning. Performance (equity curve, attribution, outcomes),
teams, universe, the event log (plain language), and "Ask the Boardroom" are
one click below. `/docs` renders `docs/SCOPE.md`, `docs/OPERATIONS.md`, and
`RUNBOOK.md` **directly from the repo at build time** — every merge to main
redeploys and re-syncs them, so the dashboard docs can never drift.

It also shows **Your portfolio** — the Kraken book, from a portfolio snapshot
taken each checkpoint (`boardroom/portfolio.py`, persisted via migration 0010):
coins + cash with each coin's intraday change and the day's top gainers/losers.
`KrakenBroker.get_positions()` reads the real book; every derived number is
code-computed (unpriced holdings show as such rather than guessed). The health
strip's equity figure likewise counts Kraken only. All read-only.

---

## 9. Open design questions / rationale

**Why a few checkpoints a day and not constant trading?** The owner's mandate is
growth-while-small with real risk tolerance, so the cadence is **8×/day** (2026-08-05, up from 4×) —
more shots for crypto while the account is tiny. But it is deliberately *not* a
high-frequency churner, because:
- Every round-trip pays **~0.5% in Kraken fees**; trading constantly turns fees into the
  dominant cost on a small book (the fee-drag cap is 5% of equity). The cost gate refuses
  any trade whose edge doesn't clear its own fees, so "constant 1%/day churn" is structurally
  blocked — it would lose to fees.
- The system still **holds the floor most checkpoints** unless a genuine positive-edge
  setup appears; the aggression schedule just lowers the bar to act while small.

This is revisited as the account grows. The natural next step (when equity justifies it)
is an **intraday risk-only check** for crypto — let the Event leg *exit* a cratering
position between checkpoints — and cadence can rise further if the edge proves out net of
fees. Pure frequency for its own sake is intentionally avoided.

---

## Changelog

- **2026-08-06** — **Intraday exit engine — the $969 that never sold.** Post-mortem:
  three LITUSD lots (~$372, TP 9–12.5%, stops 6–10%) rode +75% overnight to a
  ~$969 book top and round-tripped to a −14.28% stop-out at 14:48 the next day,
  tripping the drawdown breaker — while checkpoints at 01:30/04:30/07:30/10:30
  watched equity print $869→$981→$894 in their own growth-tier audits. Three
  structural causes, all fixed: **(1) daily-candle blindness** — resolution walked
  1440-minute closes, so the entire pump-and-dump lived inside one candle; exits
  now walk **intraday bars** (`EXIT_BAR_MINUTES`, 60) fetched per held symbol, and
  the **exit watcher** re-checks the book every `EXIT_WATCH_MINUTES` (15) between
  checkpoints — sells only, no LLM. **(2) amnesiac trail** — armed/peak state was
  recomputed from each fetch's closes, so the intraday peak never registered;
  the trail now **arms and rides off bar HIGHS** and persists
  `entry_price`/`peak_return`/`trail_armed` per position (migration 0004), with the
  entry price captured at **fill time** instead of recovered from a stale daily
  close (all three LIT lots had "resolved" at an identical −14.28% because they
  shared one daily entry bar). **(3) the tick-exit gate** — intraday exits were a
  `requires_human` capability parked at the $2,500 tier; an exit that banks pumps
  earns its fee at any size, so it is BUILT and always-on at every tier. Plus,
  opportunist by design: a watcher exit triggers an immediate **re-entry
  checkpoint** (`EXIT_REENTRY_ENABLED`) so freed cash is re-bet at once, and
  phantom rows whose balance was already swept by a clamped sibling sell
  (TRU/EUL, erroring at every checkpoint since 08-05) now book their outcome and
  void (`exit_no_balance`) instead of retrying forever. Nothing got more
  conservative: same stops, same uncapped trail upside, same caps — the system
  just finally *sees* the moves it was already promising to act on. 376 tests.
- **2026-08-05 (f)** — **Volatility tilt — spot's honest substitute for leverage.**
  Leverage is off the table structurally: Kraken's OSC restricted-dealer terms
  prohibit margin/leverage for Canadian clients (the same regime behind the
  BLESS `CA:ON` rejection), and the owner was told plainly rather than sold a
  workaround. What spot CAN do: prefer the wildest liquid movers. A positive
  CEO score is now multiplied by **(1 + `VOL_TILT_STRENGTH` × min(vol/`VOL_TILT_REF`, 2))**
  (defaults 0.5 / 5% daily vol → a 12%-vol meme coin gets 2.0×, a 2%-vol major
  1.2×), using the pitch's own computed volatility feature — pure code, no LLM.
  Leverage-like daily swings from the asset itself, with zero liquidation risk;
  the cost gate still kills anything that can't pay its way, and gated pitches
  are never rescued by wildness. Strength 0 disables. 362 tests.
- **2026-08-05 (e)** — **LOTTO MANDATE — the owner's explicit throwaway-money
  directive** ("as BIG as possible; if it ends at zero it's fine"): deployable
  98%, per-trade/per-asset caps 100% (the whole book can ride the single best
  idea), order floor 40% of book, stop cap widened to 10% (volatile runners
  aren't shaken out; the trail arms at 12.5%), full Kelly + 0.7 shrinkage floor
  unchanged, ratchet off. The daily-loss (50%) and drawdown (80%) breakers are
  reframed as MALFUNCTION tripwires — they exist to halt a runaway bug, not to
  protect capital the owner has explicitly put at risk. Recorded honestly in the
  same commit: this is a maximum-variance configuration; the modal outcome is a
  drawn-down book punctuated by occasional multi-x runs — exactly what was
  ordered, on the record. 358 tests.
- **2026-08-05 (d)** — **Owner risk dials — max aggression, chosen explicitly.** Asked
  the owner the four risk-of-ruin questions directly; the answers (on the record):
  per-trade cap **40%** (was 20; per-asset aggregate cap follows to 40% so a full
  position is reachable), daily-loss breaker **12%** (was 6 — at ~$100+ positions the
  old line tripped on a single overnight gap and froze the day), **FULL Kelly**
  (`KELLY_FRACTION` 1.0, new dial; hard caps still clamp every size) with the
  shrinkage floor softened to **0.7** (the model keeps ≥70% of its voice — the record
  still drags fantasy down, it no longer silences conviction), and the **gains
  ratchet OFF** (`RATCHET_CAPTURE_PCT` 0, new dial — every profit dollar stays
  invested and compounds; the already-banked reserve is never released). Drawdown
  breaker stays 15% from peak — the last hard line. Neither breaker ever rides the
  aggression ramp. 358 tests.
- **2026-08-05 (c)** — **Trade autopsy → targeted aggression.** One-time read of all
  57 resolved trades: horizon exits made **+$27** (avg +2.6%) and the two real
  take-profits **+$10.9**, while stop-losses lost **−$67.8** at an average −20.4% —
  triple the 6% cap, because stops only evaluate at checkpoints and daily closes gap
  through them. Repeat winners (KAITO 7/7 +$43, ZAMA 4/4 +$16) and repeat losers
  (TRU 0/4 −$23, COTI 4/10 −$28) — but nothing remembered the ASSET, only the
  division. And every crash ever (3) was a transient network failure. Changes:
  (1) **checkpoints 8×/day** (every 3h, `CHECKPOINT_TIMES` default) — denser stop
  evaluation shrinks gap risk AND doubles scan frequency; (2) **per-asset track-record
  tilt** — each asset's realized net (≥2 resolutions) becomes a bounded score
  multiplier (±0.6, code-computed each checkpoint), so proven coins outrank proven
  losers — demoted, never banned; (3) **network retries** on Kraken public GETs and
  idempotent private reads (3 attempts, backoff; AddOrder NEVER retries — a lost
  response after a fill must not double-order); (4) knobs: `MIN_ORDER_PCT` 15%,
  `MAX_FUNDINGS_PER_CHECKPOINT` 3, trail arms at 1.25R (+7.5%, profit floor ≈ +1.5%
  once armed), `ROTATION_EDGE_MULTIPLE` 2.0 (rotations were 1-for-6, −$19.7 — demand
  more edge before churning). Breakers/caps untouched. Operator: update
  `CHECKPOINT_TIMES` in `.env` (or delete the line to take the new default) and
  re-run `install_scheduler.ps1` so Task Scheduler registers the 8 triggers. 358 tests.
- **2026-08-05 (b)** — **Percent-of-book conviction floor.** ("We're ready.") Every
  funded order had pinned at the $25 exchange minimum — post-shrinkage Kelly sizes
  are dollars, so `MIN_ORDER_CAD` was doing all the sizing and positions could
  never be a meaningful slice of the book. The floor is now
  **max(`MIN_ORDER_CAD`, `MIN_ORDER_PCT` × portfolio)** (`MIN_ORDER_PCT` default
  10%): ~$68 positions on today's $676 book, ~$4 at risk per trade with the
  6%-capped stop, scaling automatically as equity grows. Clamped to the per-trade
  cap (20%) and deployable headroom as before; breakers untouched; `MIN_ORDER_PCT=0`
  restores the old fixed floor. 353 tests.
- **2026-08-05** — **Execution robustness: sells clamp to reality, refused assets
  remembered.** First fully-live night surfaced two blockers. (1) **Sell clamp**:
  a tracked position can exceed the actually-sellable spot balance (in-kind fee
  dust; Earn-allocated coins) — TRU/EUL exits bounced for days on
  `EOrder:Insufficient funds` over ~1e-6 coins, leaving ~$40 stuck. SELL orders
  with a tracked qty now clamp to Kraken's own available spot balance
  (`_available_base_qty`; Earn `.F`/`.S` variants excluded; unreadable balance →
  trade tracked qty as before; zero balance → clean error). (2) **Restricted
  assets**: Kraken listed BLESSUSD but refused the funded buy
  ("EAccount:Invalid permissions: BLESS trading restricted for CA:ON"), burning a
  funding slot. Permission refusals are now remembered in
  `system_state.restricted_assets` (migration 0016, applied + BLESS seeded) and
  gated out of funding alongside the executability gate. 351 tests.
- **2026-08-04 (d)** — **Zero deviation bar while small — the floor stops winning by
  default.** First post-unpark live run proved the last chokepoint: pitches passed
  every gate (cost, floor, Risk Manager), ranked at score 0.001 — and lost to a
  0.0017 deviation bar. Post-shrinkage scores live at the 0.001–0.005 scale, so the
  "low" 0.001 bar still meant HOLD forever. `CEO_DEVIATION_THRESHOLD_LOW` now
  defaults to **0.0** and `AGGRESSIVE_BELOW_CAD` to **$1000**: under $1000 equity,
  ANY surviving positive-net-edge idea funds (min-order floor makes it a real $25
  trade). Growth ladder re-rung to match (sprout/sapling merged at $1000). Breakers,
  caps, cost gate, and the two-key live gate unchanged. 345 tests.
- **2026-08-04 (c)** — **Go-big mandate: no silent self-parking, and winners run.**
  Owner directive after finding the system fully parked. (1) **Leash floor +
  rolling calibration**: the per-division leash had walked to 0 for BOTH live
  divisions (crypto_trend 17/42 wins, momentum ~1/10) — an absorbing state (no
  trades → no evidence → no recovery). A non-retired division's leash now
  floors at `LEASH_MIN` (0.15) and hydration clamps stored zeros up, so the
  currently-starved divisions revive on the next checkpoint; calibration is
  judged on the most recent `CALIBRATION_WINDOW` (30) outcomes so old losses
  age out. (2) **Retirement fixed and rearmed**: `n_resolved`/`net_vs_floor_cad`
  were never updated (stuck at 0), so the documented kill switch could never
  fire; they're now recomputed from the real outcome history each update, and
  retirement needs BOTH windowed mean < `RETIRE_MEAN_BELOW` (0.35) AND
  net-negative money over ≥ `RETIRE_MIN_SAMPLE` (30) — a division that's
  merely cold keeps trading at the floor; one that's demonstrably broken
  retires with an audit trail. New **`boardroom revive`** lists division
  states and is the only way back (fresh flat prior, default leash 0.5).
  (3) **Trailing exits** (`EXIT_TRAIL_ENABLED`, default true): hitting the
  take-profit no longer sells — it ARMS a trailing stop at the position's own
  capped stop distance; the ride is uncapped, survives the horizon clock, and
  exits on the first close that gives back the trail from its peak (the +9%
  hard TP had been capping every winner; the old asymmetric-band failure can't
  return because the give-back is bounded by the 6%-capped stop). 344 tests.
- **2026-08-04 (b)** — **Daily-loss breaker was counting ALL-TIME losses.**
  `SupabaseRepository.recent_outcomes` never hydrated `resolved_at` from the
  row, so every outcome took the schema default ("now") and the daily-loss
  breaker's `resolved_at.date() == today` filter matched the ENTIRE history:
  once lifetime losses passed 6% of equity the system force-held every
  checkpoint, forever (live: frozen 2026-08-01→04 on "daily loss 63.97" that
  was actually the all-time total; the true daily figure was under the limit).
  Row→model mapping extracted to `_outcome_from_row` (also restores `symbol`),
  unit-tested against the exact failure mode. The in-memory repo used by tests
  preserves objects, which is why no test ever caught it. 332 tests.
- **2026-08-04** — **Fiat balance codes: deposits are never invisible.** A new
  Kraken deposit can land under a variant asset code — `CAD.HOLD`/`USD.HOLD`
  (funding hold) or `CAD.F`/`USD.F` (Rewards-enrolled) — which the old cash
  reader (exact `ZCAD` + `ZUSD` lookups) silently ignored, so the dashboard's
  equity never moved after a top-up. `get_cash_cad` now classifies **every**
  balance code via `_fiat_currency()` and sums per currency (CAD at face, USD
  at live FX with the documented 1:1-understatement fallback, other fiat only
  at a live rate). Same classifier now guards `get_positions`, so fiat
  variants can't masquerade as coin holdings — and coins like ZRX are no
  longer dropped by the old Z-prefix heuristic. 328 tests.
- **2026-07-27 (b)** — **Strategy autopsy fixes** (a month live: realized −$5.70
  over 29 trades vs +7.9% average predicted). (1) **Exit asymmetry**: the
  take-profit was the predicted band top (~+20–28%, hit once in 29 trades) while
  stops ran 10–14% deep — small wins, big losses by construction. Now the stop is
  capped (`EXIT_STOP_CAP_PCT`, 6%) and the take-profit is a fixed R-multiple of it
  (`EXIT_TP_R_MULTIPLE`, 1.5× → 9%); the predicted band stays as the Critic's
  scoring window only. New `open_positions.take_profit` column (migration 0015);
  legacy rows (0) keep band-top behavior. (2) **Prediction shrinkage**: each
  pitch's expected return is blended toward the division's REALIZED mean before
  any gate/rank/size acts on it (weight `max(prior_n/(prior_n+n), min_weight)`,
  `PREDICTION_SHRINK_PRIOR_N`=5 / `PREDICTION_SHRINK_MIN_WEIGHT`=0.3; raw model
  number kept in features for audit). Fantasy forecasts stop clearing the cost
  gate; a cold streak can't silence the model entirely.
- **2026-07-27** — **Two stuck-state fixes** (found while the drawdown breaker was
  tripped). (1) **Resolution price fallback**: a HELD coin that churns out of the
  dynamic universe (volume/rank) lost its price series, so its stops/take-profit/
  horizon went unmanaged — six coins (AXS, BLUR, DRV, PYTH, SYRUP, TRU) sat like
  that from 2026-07-26. The resolution loop now fetches a held symbol's OHLC
  directly from Kraken's public endpoint when no division covers it (live mode
  only; misses cached per checkpoint). (2) **Breaker path keeps housekeeping**: a
  tripped breaker halts new risk but no longer skips the read-only portfolio
  snapshot + orphan reconciliation — previously both froze for as long as a
  breaker stayed tripped, going stale exactly when scrutiny mattered most.
- **2026-07-22** — **`boardroom adopt` — act on orphaned holdings.** The checkpoint
  already flagged untracked Kraken holdings (a coin held with no tracked position
  the auto-sell loop can't manage); now there's a command to act on them.
  `boardroom adopt` lists the orphans; `boardroom adopt --asset <SYM> --sell
  --confirm-live` flattens one back to cash — settling in the account quote,
  selling the exact held quantity (`Order.base_qty`), on-exchange only (never a
  withdrawal), behind the two-key live gate. `Orchestrator.flatten_holding` does
  the work; no new tables.
- **2026-07-10** — **Capital rotation (owner mandate: growth over sitting).**
  Each checkpoint, if a strong idea is left over after normal funding, it can
  take the money of the WEAKEST current holding: when the candidate's net edge
  beats the holding's remaining edge (today's pitch for that asset, else zero)
  by more than `ROTATION_EDGE_MULTIPLE` (1.5×) the round-trip switching cost,
  the holding is sold at market (forced resolution, booked as a real outcome
  with exit reason `rotation` — the learning loop scores it) and the candidate
  is funded through the full CEO gauntlet. At most ONE rotation per
  checkpoint; disable with `ENABLE_ROTATION=false`. Protection floor
  unchanged: caps, breakers, cost gates all still bind. 293 tests.
- **2026-07-09 (c)** — **Whole-exchange scan.** The wide crypto universe is now
  dynamic: every liquid USD-quoted Kraken pair (live 24h volume ≥ $250k,
  capped at the 150 deepest books, stablecoins/fiat/dark-pools/tokenized
  equities excluded), refreshed each checkpoint — replaces the hand-curated
  ~37 so a surging coin can't be invisible. DOGE becomes scannable and
  tradable under Kraken's `XDGUSD` name. Tunables:
  `CRYPTO_UNIVERSE_MAX` / `CRYPTO_MIN_USD_VOLUME_24H`; curated list is the
  fallback. Cadence and entry discipline unchanged: daily-close evaluation,
  Momentum buys volume-confirmed breakouts, no intraday surge-sniping (that
  stays the canopy-tier unlock at $5k). 289 tests.
- **2026-07-09 (b)** — **Live-equity sizing: deposits picked up automatically.**
  Sizing/caps now resolve against the REAL Kraken book each checkpoint (fiat
  cash in CAD terms + coin holdings at market, minus the reserve) instead of
  `STARTING_PORTFOLIO_CAD + realized P&L` — so topping up the account needs no
  config edit; the next checkpoint sees the money. The gains ratchet stays on
  the realized-P&L basis (a deposit is never swept as a "gain"), and a new
  live-equity high-water mark (`equity_hwm_cad`, migration 0014) feeds the
  drawdown breaker so it scales with deposits. Unreadable venue → clean
  fallback to the baseline, never a guess. 285 tests.
- **2026-07-09** — **Fee-drag breaker measures against equity (unfreeze fix).**
  The fee-drag breaker divided cumulative costs by cumulative *winning* P&L —
  with four resolved trades ($0.29 fees, one $1.15 win) that read as "25.3%
  drag" and froze all trading. It now measures costs against **equity** (the
  documented "5% of equity" cap): 0.15% today, clear. Breakers re-evaluate
  every run, so the fix self-clears the halt. Health-strip **Equity** now
  shows the full Kraken book (cash + coins) from the latest portfolio
  snapshot instead of cash only, which dipped misleadingly on every buy.
- **2026-07-08 (b)** — **Per-coin scoreboard.** Resolved outcomes now carry the
  traded pair (`symbol`, migration 0013), so the dashboard's Performance table
  shows WHICH coin each realized trade was (plus the critic's postmortem on
  hover). The learning loop itself was already complete — process-vs-luck tag,
  LLM postmortem, Beta-posterior calibration, leash, retirement, all folded in
  per resolved trade and reloaded by the CEO each checkpoint — it simply had
  zero completed trades to learn from until the stuck-SOL fix landed.
- **2026-07-08** — **Exit-resolution symbol fallback (the stuck-SOL fix).**
  Positions store their EXECUTION pair (SOLCAD in the CAD era) but the exit
  loop's price cache is keyed by ANALYSIS symbols (SOLUSD) — the lookup missed,
  so four past-horizon SOL positions sat open in silence for three days. The
  cache lookup now falls back through the base asset across quotes, an
  unpriceable position audits `resolution_no_data` instead of being skipped
  silently, and order sizing converts by the **exec pair's own quote** (a
  legacy CAD-pair sell on the USD-funded account sizes in CAD, not USD).
  279 tests.
- **2026-07-03 (b)** — **USD-funded mode.** Live check showed only 5/37 coins
  have a Kraken CAD market (BTC, ETH, SOL, XRP, PEPE) — the rest could never
  fill from a CAD account. `ACCOUNT_BASE_CURRENCY=USD` now executes on USD
  pairs (whole universe buyable) with an explicit FX layer at the broker
  boundary: CAD notional ÷ live USDCAD rate for sizing (no rate = no trade),
  ZUSD cash valued into CAD, holdings priced on the quote market → CAD. Gate
  generalized (`tradable_pairs_for(quote)`, `no_exec_market_skip` audit).
  Requires the operator to convert CAD→USD in Kraken first. 276 tests.
- **2026-07-03** — **Executability gate + truthful funded cards.** (1) Coins
  with no CAD market on Kraken are excluded **before funding** — verified
  against Kraken's live AssetPairs list (`tradable_cad_pairs`, cached per
  process, fails open to a clean execution error) — so an unfillable coin
  never eats a funding slot (UNIUSD burned three). Skips are audited
  (`no_cad_market_skip`) and explained in the session. (2) The dashboard's
  reasoning cards now cross-check funded decisions against the `fills` table:
  a FUNDED decision with no confirmed fill shows **"⚠ NOT FILLED — no money
  moved"** with the execution error, instead of "✅ Bought". 271 tests.
- **2026-07-02 (b)** — **Dashboard goes crypto-only.** The stocks/IBKR UI is
  removed to match the equities sunset: no Recommendations section, no IBKR
  book in "Your portfolio", and the health-strip equity counts Kraken cash
  only (was Kraken + IBKR). The backend advisory code stays dormant behind
  `ENABLE_EQUITIES`; the UI is resurrectable from git history.
- **2026-07-02** — **Growth ladder (signals only).** Every checkpoint maps total
  equity (investable + reserve) through a deterministic tier ladder
  (`adaptive/growth.py`); the tier is audited (`growth_tier` event) and carried
  in the session with the next unlock and the equity it needs. Rungs align with
  the aggression schedule ($500/$5,000); higher rungs flag intraday tick-level
  exits ($2.5k) and intraday surge entries ($5k) as eligible — `requires_human`
  signals, never auto-enabled. No trading behavior changed. 267 tests.
- **2026-07-01 (d)** — **Crypto-first.** Equities SUNSET by default
  (`ENABLE_EQUITIES=false`): no stock scans, no recommendations, no IBKR
  dependency — code dormant, not deleted. Crypto analysis widened to ~37 coins
  on deep **USD-pair data** with **CAD execution** via `exec_pair_for` (a coin
  without a CAD market errors cleanly and is skipped). New **per-asset
  aggregate exposure cap** (`ASSET_MAX_EXPOSURE_PCT`, 20%): re-buying a winner
  stays allowed until the asset holds the max share of the book, then the
  next-best coin gets the capital (no hard no-rebuy rule). The CEO may now fund
  up to `MAX_FUNDINGS_PER_CHECKPOINT` (2) **different** assets per checkpoint —
  diversification instead of winner-take-all (the SOL monoculture fix). 260 tests.
- **2026-07-01 (c)** — **Position-save FK bug fixed (the actual root cause).**
  `open_positions` has a foreign key to `decisions`; since 2026-06-30 the
  decision was saved *after* execution, so **every** new position insert
  violated the FK — unhandled, it crashed the 2026-07-01 20:06 run; handled
  (post-rework), it still left the 21:27 buy untracked. `run_once` now saves
  the decision **before** executing (FK parent exists) and re-saves it after
  (live flag stays truthful); the in-memory repo upserts decisions by id to
  match Supabase semantics. Both affected positions adopted manually. 252 tests.

- **2026-07-01 (b)** — **Execution truth + dashboard rework.** New `fills` table:
  every broker fill (buy and sell, live and paper) is persisted the instant the
  broker returns — before any other write — with qty/price/fee/txid, so a mid-run
  crash can never again lose the record of money moving (a 2026-07-01 wide-scan
  run crashed after a live SOLCAD buy and lost its decision + position; both were
  reconstructed manually and the position adopted). New `runs` table: every
  checkpoint records started/ok/**crashed** with the error, the breaker
  evaluation, and a **venue reconciliation** (Kraken holdings vs tracked
  positions → orphans surface as alerts). Circuit breakers are now evaluated
  **inside every run** and halt new entries deterministically. NaN/Infinity are
  sanitized before every Supabase write. The poller writes a liveness heartbeat.
  Dashboard rebuilt around Executed / Positions / Reasoning / Recommendations
  with an honest health strip; `/docs` now renders the repo's markdown at build
  time (the deploy pipeline is the docs-update loop). 251 tests.

- **2026-07-01** — **Two-key live gate enforced in the execution layer.** Both the
  buy path (`Orchestrator.execute`) and the live sell path (`_close_position_live`)
  previously fired on `LIVE_TRADING` alone — a `boardroom run`/`poll` invoked
  *without* `--confirm-live` (but with `LIVE_TRADING=true` in `.env`) would have
  placed real orders while the console printed "dry-run". The per-run confirm flag
  is now threaded into the orchestrator (`Orchestrator.confirm_live` →
  `effective_live`); either key alone is a dry-run, exactly as documented.
  `boardroom decide --confirm-live` also now wires real brokers (it silently used
  stubs before). 5 regression tests.
- **2026-06-30 (g)** — **Real auto-sell (it can now exit, not just buy).** First live BUY
  filled (SOLCAD $25) — but the resolution loop only booked paper P&L and deleted the
  tracking row; it never sold, so coins accumulated and "realized" P&L was fictional. Now a
  resolution **places a real Kraken SELL** to close on stop-loss / take-profit (the predicted
  band top) / horizon, selling the exact filled qty (`OpenPosition.qty`, migration 0011). The
  position is finalized only when the sell actually executes — a rejected sell keeps it open to
  retry and books no outcome. Also fixed `decisions.live` persistence (saved after execution)
  so the dashboard's LIVE badge is truthful. Exits evaluate on daily closes. 237 tests.

- **2026-06-30 (f)** — **Minimum-order floor (so small trades fill).** With a CAD universe in
  place, the next live FUND tried `SOLCAD` at $6.19 and Kraken rejected it: *volume minimum
  not met*. Weak-conviction sizes on a small account land below the exchange's per-coin
  minimum. Added `MIN_ORDER_CAD` (default 25): a funded order below it is bumped up to the
  floor — but never above the per-trade cap or deployable headroom, so the risk envelope is
  untouched. Dry-run now funds at the floor instead of a rejected dust order. 232 tests.

- **2026-06-30 (e)** — **Crypto universe → CAD pairs (so it can actually buy).** The first
  live FUND tried `AAVEUSD`→`AAVECAD`, which has no Kraken CAD market, so it skipped (cleanly,
  thanks to (d)). Root cause: the universe was USD-quoted alts a CAD account can't buy. Pinned
  the crypto universe to **CAD-quoted majors** (core 7 + ~18 wide) so data, signals, and
  execution all align and every funded coin is tradeable; unknown CAD pairs just abstain at
  data-fetch. Also made the Kraken ticker lookup raise a clear "no market for pair" message
  instead of a cryptic `KeyError: 'result'`.

- **2026-06-30 (d)** — **Live-execution fixes (first real order).** The first live crypto
  FUND surfaced two issues: (1) the account is CAD-funded but signals run on USD-quoted
  pairs, so the order hit `EOrder:Insufficient funds` — now orders are translated to the
  account's quote currency (`XBTUSD`→`XBTCAD`, via `exec_pair_for`) and priced in CAD;
  (2) a broker rejection crashed the whole checkpoint — `execute()` now catches it, logs an
  `execute_error`, and finishes the run (balances/recommendations/portfolio still refresh).
  Coins with no CAD market are skipped, not fatal. 237 tests passing.

- **2026-06-30 (c)** — **Made it actually trade crypto.** Diagnosis: it was HOLDing every
  checkpoint because the crypto strategies only pitch on rare setups (Event = dislocation,
  Momentum = confirmed breakout), so most checkpoints produced zero crypto pitches. Added an
  **always-on Crypto Trend division** (`crypto_trend.py`, new `CRYPTO_TREND` division) that
  reuses the trend/mean-reversion model on the Kraken universe and proposes a long whenever
  there's positive edge — auto-funded under the venue rule, long-only, still cost-gated and
  capped. Also **loosened the Momentum breakout trigger** (z 1.5→1.0, volume 1.5→1.25×). Now
  the loop regularly funds a crypto position instead of sitting in cash. 237 tests passing.

- **2026-06-30 (b)** — **Turned up for growth while small.** Per the owner's call (small
  play-money account, take real risk early, de-risk as it grows): the aggression schedule
  now scales TWO knobs on the equity ramp — the deviation bar (low 0.001 while small) AND a
  new bold-while-small **crypto Event position cap** (`EVENT_HARD_CAP_PCT_SMALL`, up to the
  20% per-trade max, tapering to 5%). Funding is now decided **by venue** (Kraken = funded,
  IBKR = advisory), so a crypto **Momentum** breakout trades live while stock pitches stay
  advisory. Crypto universe widened 13→31 pairs; checkpoints went 2×→**4×/day**. The
  daily-loss (6%) and drawdown (15%) breakers are explicitly NOT scaled. Dashboard tables are
  now collapsible. 237 tests passing.

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
  default `13:30,19:00` UTC). 237 tests passing.

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
