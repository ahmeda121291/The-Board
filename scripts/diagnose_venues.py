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
    print("snaptrade client id    :", (s.snaptrade_client_id or "(missing)"))
    print("snaptrade consumer key :", "set" if s.snaptrade_consumer_key else "(missing)")
    print("snaptrade user id      :", (s.snaptrade_user_id or "(missing)"))
    print("snaptrade user secret  :", "set" if s.snaptrade_user_secret else "(missing)")
    print("snaptrade account id   :", (s.snaptrade_account_id or "(missing)"))

    print("\n=== Kraken: private Balance call ===")
    try:
        from boardroom.brokers.kraken import KrakenBroker

        kb = KrakenBroker()
        bal = kb._private("Balance")
        print("OK. Balance keys:", list(bal.keys()))
        print("CAD (ZCAD):", bal.get("ZCAD", "0"))
    except Exception as e:  # noqa: BLE001
        print("ERROR:", repr(e)[:700])

    print("\n=== SnapTrade: list_user_accounts ===")
    try:
        from boardroom.brokers.snaptrade import SnapTradeBroker

        sb = SnapTradeBroker()
        resp = sb._sdk().account_information.list_user_accounts(**sb._user_args())
        accounts = resp.body if hasattr(resp, "body") else resp
        ids = [str(a.get("id")) for a in accounts]
        print("OK. accounts returned:", len(ids))
        print("target account id     :", s.snaptrade_account_id)
        print("target present in list:", s.snaptrade_account_id in ids)
        if s.snaptrade_account_id not in ids:
            print("first few ids:", ids[:5])
    except Exception as e:  # noqa: BLE001
        print("ERROR:", repr(e)[:900])


if __name__ == "__main__":
    main()
