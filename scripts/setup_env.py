#!/usr/bin/env python3
"""Guided .env setup — answer the prompts, it writes a correct .env for you.

Run:  python scripts/setup_env.py

For each setting it shows a short description and (if you already have a value)
lets you keep it by pressing Enter. Secrets you paste are written straight to
.env in the repo root — no Notepad, no risk of a ".env.txt" filename.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# (key, friendly prompt, default, is_secret)
FIELDS = [
    ("LIVE_TRADING", "Master live switch — keep 'false' until you're ready to trade for real", "false", False),
    ("SUPABASE_URL", "Supabase project URL", "https://qyaekaifodgiaxyztpdt.supabase.co", False),
    ("SUPABASE_SERVICE_KEY", "Supabase service_role key (Dashboard > Settings > API > Reveal). Long JWT starting eyJ...", "", True),
    ("ANTHROPIC_API_KEY", "Anthropic API key (sk-ant-...). Optional — blank = templated rationales", "", True),
    ("KRAKEN_API_KEY", "Kraken API key (trade + staking; WITHDRAW DISABLED)", "", True),
    ("KRAKEN_API_SECRET", "Kraken API secret (the private key, ends in ==)", "", True),
    ("IBKR_ACCOUNT_ID", "Interactive Brokers account id (U... live or DU... paper). Run the Client Portal Gateway + log in at https://localhost:5000", "", False),
    ("IBKR_GATEWAY_URL", "IBKR Client Portal Gateway URL", "https://localhost:5000", False),
    # --- Hard risk caps as PERCENT of portfolio value (scale as you grow) ----
    ("TOTAL_DEPLOYABLE_PCT", "Max fraction of portfolio the agents may deploy (0.80 = 80%)", "0.80", False),
    ("PER_TRADE_MAX_PCT", "Max fraction of portfolio for any single trade (0.20 = 20%)", "0.20", False),
    ("EVENT_HARD_CAP_PCT", "Ceiling on the Event (lottery) division (0.05 = 5%)", "0.05", False),
    ("DAILY_LOSS_LIMIT_PCT", "Daily realized-loss limit as % of equity; breach -> all to floor (0.06 = 6%)", "0.06", False),
    ("MAX_DRAWDOWN_PCT", "Peak-to-trough drawdown that trips the circuit breaker (0.15 = 15%)", "0.15", False),
    ("FEE_DRAG_LIMIT_PCT", "Cumulative cost-drag ceiling (0.05 = 5%)", "0.05", False),
    ("STARTING_PORTFOLIO_CAD", "Reference portfolio value for resolving caps until live equity is wired", "200", False),
    ("CHECKPOINT_UTC", "Daily checkpoint time the CEO convenes, HH:MM in UTC (19:00 = ~3pm ET, inside market hours)", "19:00", False),
]


def _load_existing() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def _mask(value: str) -> str:
    if not value:
        return "(blank)"
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}…{value[-2:]}  ({len(value)} chars)"


def main() -> None:
    print("\n=== Boardroom .env setup ===")
    print("Paste each value and press Enter. Press Enter alone to keep the shown")
    print("value or skip. Nothing is sent anywhere — it's written only to your")
    print(f"local file: {ENV_PATH}\n")

    existing = _load_existing()
    result: dict[str, str] = {}

    for key, desc, default, is_secret in FIELDS:
        current = existing.get(key, default)
        shown = _mask(current) if (is_secret and current) else (current or "(blank)")
        print(f"\n{key}")
        print(f"  {desc}")
        print(f"  current: {shown}")
        entered = input("  new value (Enter = keep): ").strip()
        result[key] = entered if entered else current

    # Write the file (only non-empty values, plus LIVE_TRADING/SUPABASE_URL always).
    lines = []
    for key, _desc, _default, _secret in FIELDS:
        v = result.get(key, "")
        if v or key in ("LIVE_TRADING", "SUPABASE_URL"):
            lines.append(f"{key}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Best-effort lock-down on POSIX; on Windows the repo .gitignore already
    # excludes .env so it never gets committed.
    try:
        os.chmod(ENV_PATH, 0o600)
    except Exception:
        pass

    set_keys = [k for k, _, _, _ in FIELDS if result.get(k)]
    print(f"\nWrote {ENV_PATH}")
    print("Keys with a value:", ", ".join(set_keys) or "(none)")
    print("\nNext:  boardroom doctor")


if __name__ == "__main__":
    main()
