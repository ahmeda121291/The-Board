#!/usr/bin/env python3
"""Diagnose why a venue health-check fails. Prints the REAL errors that
preflight swallows. Read-only: lists balances/accounts, places no orders.

    python scripts/diagnose_venues.py
"""

from __future__ import annotations


def main() -> None:
    from boardroom.config import get_settings

    s = get_settings()
    print("=== config ===")
    print("kraken creds present   :", bool(s.kraken_api_key and s.kraken_api_secret))
    print("ibkr gateway url       :", s.ibkr_gateway_url)
    print("ibkr account id        :", (s.ibkr_account_id or "(missing)"))

    print("\n=== Kraken: private Balance call ===")
    try:
        from boardroom.brokers.kraken import KrakenBroker

        kb = KrakenBroker()
        # Scan the loaded key/secret for non-ASCII characters (copy-paste gremlins).
        for nm, val in (
            ("API key", s.kraken_api_key.get_secret_value() if s.kraken_api_key else ""),
            ("API secret", s.kraken_api_secret.get_secret_value() if s.kraken_api_secret else ""),
        ):
            bad = [(i, hex(ord(c))) for i, c in enumerate(val) if ord(c) > 127]
            print(f"{nm}: len={len(val)} ascii={val.isascii()}" + (f" NON-ASCII at {bad[:8]}" if bad else ""))
        bal = kb._private("Balance")
        print("OK. Balance keys:", list(bal.keys()))
        print("CAD (ZCAD):", bal.get("ZCAD", "0"))
    except Exception as e:  # noqa: BLE001
        print("ERROR:", repr(e)[:700])

    print("\n=== IBKR: Client Portal Gateway health ===")
    try:
        from boardroom.brokers.ibkr import IBKRBroker

        ib = IBKRBroker()
        healthy = ib.health_check()
        print("gateway authenticated :", healthy)
        if healthy:
            print("cash (CAD)            :", ib.get_cash_cad())
        else:
            print("-> start the gateway and log in at", s.ibkr_gateway_url)
    except Exception as e:  # noqa: BLE001
        print("ERROR:", repr(e)[:700])


if __name__ == "__main__":
    main()
