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
| `localhost:5000` | IBKR Client Portal Gateway (Directional) — runs locally |
| `query1.finance.yahoo.com` | keyless daily equity bars (Directional research) |
| `api.anthropic.com` | LLM reasoning (already allowed) |

---

## Path A — run on your own machine (recommended, fastest)

Nothing to approve; your keys never leave your laptop.

```bash
git clone <this repo> && cd The-Board
git checkout main
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

# Directional via Interactive Brokers (Client Portal Gateway, session-based).
IBKR_GATEWAY_URL=https://localhost:5000
IBKR_ACCOUNT_ID=<your IBKR account id, e.g. U1234567 (or DU... for paper)>
```

### One-time IBKR setup (Client Portal Gateway)

IBKR's Client Portal API is **session-based — there is no static API key**. You
run a small gateway locally and log into it; it holds your authenticated session.
Requires an **IBKR Pro** account and **Java 8u192+**.

```powershell
# 1. Download + unzip the gateway:
#    https://download2.interactivebrokers.com/portal/clientportal.gw.zip
Expand-Archive "$HOME\Downloads\clientportal.gw.zip" -DestinationPath "C:\IBKR"

# 2. Start it (leave this window running — the session lives here):
cd C:\IBKR
bin\run.bat root\conf.yaml

# 3. In a browser, open https://localhost:5000, accept the local cert warning,
#    and log in with your IBKR username + password + 2FA ("Client login succeeds").
```

Then set `IBKR_ACCOUNT_ID` in `.env` (account id from
[portal.interactivebrokers.com](https://www.interactivebrokers.com/en/trading/client-portal.php)).
Enable trading on the account; keep transfers/withdrawals OFF.

> **The gateway must be running and authenticated when Boardroom runs.** The
> session **expires daily / on inactivity**, so re-log-in before each checkpoint
> (people automate this with [IBeam](https://github.com/voyz/ibeam); manual
> re-login is fine to start). If the gateway is down or logged out, the Directional
> leg simply abstains that checkpoint — Kraken (crypto) is unaffected and executes
> live regardless.

---

## Running unattended (Windows Task Scheduler)

Instead of leaving `boardroom run` open in a terminal, let Windows be the daily
trigger — survives reboots, wakes the PC, no window to babysit.

```powershell
# from the repo root, once. 15:00 local = always 1h before the 4pm equities
# close, so the stock leg fires while the market is open and can fill.
powershell -ExecutionPolicy Bypass -File .\install_scheduler.ps1 -Time 15:00
```

> **Why 15:00 local?** The run uses `--once`, so the Task Scheduler trigger time
> *is* the execution time. Equities (Interactive Brokers) only fill during
> the 9:30am–4:00pm ET regular session; 15:00 local is 1h before the close in both
> summer and winter. Crypto (Kraken) is 24/7. As a backstop, a market-hours guard
> auto-holds any live equity order placed while the market is closed (it logs an
> `equity_market_closed` event rather than queuing a blind after-hours order).

That registers a **Boardroom Daily** task that runs `run_boardroom.ps1` →
`boardroom run --confirm-live --once` (one live checkpoint) each day, logging to
`logs\scheduler.log`. It only runs while you're logged in to Windows; for fully
headless operation, open Task Scheduler → Boardroom Daily → Properties → General
→ "Run whether user is logged on or not" (stores your Windows password).

Remove it with:
```powershell
Unregister-ScheduledTask -TaskName "Boardroom Daily" -Confirm:$false
```

## Running on demand (besides the daily 3pm checkpoint)

Two ways to fire a checkpoint yourself, in addition to the scheduler.

**1. Desktop shortcut (instant, local).** Creates a "Run Boardroom Now" icon on your
Desktop; double-click it any time to fire one live checkpoint.
```powershell
powershell -ExecutionPolicy Bypass -File .\install_run_shortcut.ps1
```

**2. Dashboard "Run now" button (remote).** The button on the dashboard *requests* a
run — it never trades (the keys live only here). A background **poller** on this PC
claims the request and runs the checkpoint locally. Register it once; it starts at
logon and keeps running:
```powershell
powershell -ExecutionPolicy Bypass -File .\install_poller.ps1
Start-ScheduledTask -TaskName "Boardroom Poller"   # start now without logging off
```
The poller logs to `logs\poller.log`. Remove with
`Unregister-ScheduledTask -TaskName "Boardroom Poller" -Confirm:$false`.

> Both reuse the same `LIVE_TRADING=true` + `--confirm-live` gate and the
> market-hours guard. The daily **Boardroom Daily** task is independent and stays on.

## Safety reminders (enforced in code)
- `LIVE_TRADING` defaults false; `decide` also requires `--confirm-live`.
- Every venue credential must be **trade-only, withdrawals disabled**. The broker
  classes have no withdraw code path and assert `supports_withdrawal == False`.
- Hard caps (CAD): total deployable, per-trade, Event hard cap, daily-loss limit,
  max drawdown, fee drag — the CEO cannot widen them; a breach forces all capital
  to the floor.
- **Rotate any key that has ever been pasted into a chat or committed.**
