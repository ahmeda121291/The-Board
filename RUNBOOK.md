# Boardroom — Going Live Runbook

The code is live-capable. The only blocker to live trading is **network access to
the venue + data hosts**, which this Claude-on-the-web environment denies by
policy. There are two ways to clear it. **Path A (run on your machine) is the
fastest and keeps your keys entirely in your control — recommended.**

---

## The hosts that must be reachable

| Host | Why |
|---|---|
| `api.kraken.com` | Kraken trading + balances (Yield, Event) |
| `api.snaptrade.com` | SnapTrade → Wealthsimple (Directional) |
| `stooq.com` | keyless daily equity bars (Directional research) |
| `api.anthropic.com` | LLM reasoning (already allowed) |

---

## Path A — run on your own machine (recommended, fastest)

Nothing to approve; your keys never leave your laptop.

```bash
git clone <this repo> && cd The-Board
git checkout claude/fervent-feynman-j4jlqv
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,venues]"      # core + tests + venue SDKs

cp .env.example .env                 # then fill it in (next section)
boardroom doctor                     # sanity-check config + caps
boardroom preflight                  # read-only: venue connectivity + GO/NOT-READY
```

When `preflight` prints **GO** and you've funded the accounts:

```bash
# flip the master switch in .env: LIVE_TRADING=true
boardroom decide --confirm-live      # one real daily decision (usually HOLD)
```

## Path B — allowlist the hosts in this web environment

Reconfigure this environment's **network policy** to permit egress to the four
hosts above (see the Claude Code on the web docs:
https://code.claude.com/docs/en/claude-code-on-the-web). Once allowed, I can run
`boardroom preflight` and the live smoke test from here.

> I cannot change the policy or route around it myself — that's an org/account
> setting, and bypassing an egress denial is exactly what the environment forbids.

---

## Filling in `.env`

```ini
LIVE_TRADING=false                    # keep false until preflight is GO + funded

# Supabase (state/metrics — no trading power)
SUPABASE_URL=https://qyaekaifodgiaxyztpdt.supabase.co
SUPABASE_SERVICE_KEY=<Dashboard > Settings > API > service_role secret>

ANTHROPIC_API_KEY=<your key>          # optional; without it, rationales are templated

# Kraken (Yield + Event) — scope: Query Funds, Create/Cancel Orders, Staking.
# WITHDRAW MUST BE DISABLED.
KRAKEN_API_KEY=<fresh key>
KRAKEN_API_SECRET=<fresh secret>

# Directional via SnapTrade → Wealthsimple (trade-only; cannot move funds)
SNAPTRADE_CLIENT_ID=<from SnapTrade dashboard>
SNAPTRADE_CONSUMER_KEY=<from SnapTrade dashboard>
SNAPTRADE_USER_ID=<the user id you registered with SnapTrade>
SNAPTRADE_USER_SECRET=<returned when you registered that user>
SNAPTRADE_ACCOUNT_ID=<the connected Wealthsimple account id>
```

### One-time SnapTrade connection (to get USER_SECRET + ACCOUNT_ID)

1. Register a user → returns `userId` + `userSecret` (keep the secret).
2. Generate a connection-portal URL and open it in a browser; log into
   Wealthsimple there. SnapTrade stores the link — no brokerage password ever
   touches Boardroom.
3. List the user's accounts → copy the Wealthsimple `accountId`.

A small helper script for steps 1–3 can be added on request; it uses only the
SnapTrade SDK and your clientId/consumerKey.

> **Wealthsimple caveat:** confirm SnapTrade trading is enabled for your
> Wealthsimple account. If it's read-only, the Directional division still
> computes and scores pitches in **shadow mode** (no real equity orders) until a
> trade-capable connection exists — Kraken still executes crypto live.

---

## Safety reminders (enforced in code)

- `LIVE_TRADING` defaults false; `decide` also requires `--confirm-live`.
- Every venue credential must be **trade-only, withdrawals disabled**. The broker
  classes have no withdraw code path and assert `supports_withdrawal == False`.
- Hard caps (CAD): total deployable, per-trade, Event hard cap, daily-loss limit,
  max drawdown, fee drag — the CEO cannot widen them; a breach forces all capital
  to the floor.
- **Rotate any key that has ever been pasted into a chat or committed.**
