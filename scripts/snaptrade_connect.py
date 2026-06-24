#!/usr/bin/env python3
"""One-time SnapTrade connection helper — get USER_SECRET + ACCOUNT_ID.

Wealthsimple has no public dev API; SnapTrade brokers it. This script does the
three one-time steps so you can fill SNAPTRADE_USER_SECRET and
SNAPTRADE_ACCOUNT_ID in your .env. It uses ONLY your app keys
(SNAPTRADE_CLIENT_ID + SNAPTRADE_CONSUMER_KEY) which it reads from the
environment / .env.

Run it on a machine with network access to api.snaptrade.com (this sandboxed
environment blocks that host).

    pip install -e ".[venues]"

    # 1. Register a SnapTrade user and get its secret (run once). Pick any id.
    python scripts/snaptrade_connect.py register --user-id ahmed-boardroom

    # 2. Open the printed connection URL, log into Wealthsimple, finish linking.

    # 3. List the connected accounts and copy the account id you want to trade.
    python scripts/snaptrade_connect.py accounts \
        --user-id ahmed-boardroom --user-secret <secret-from-step-1>

Then put SNAPTRADE_USER_ID, SNAPTRADE_USER_SECRET, SNAPTRADE_ACCOUNT_ID in .env.
Treat the user secret like a password.
"""

from __future__ import annotations

import argparse
import os
import sys


def _client():
    try:
        from snaptrade_client import SnapTrade
    except ImportError:
        sys.exit("snaptrade-python-sdk not installed. Run: pip install -e '.[venues]'")

    client_id = os.environ.get("SNAPTRADE_CLIENT_ID")
    consumer_key = os.environ.get("SNAPTRADE_CONSUMER_KEY")
    if not client_id or not consumer_key:
        # Fall back to .env if present.
        try:
            from dotenv import load_dotenv

            load_dotenv()
            client_id = client_id or os.environ.get("SNAPTRADE_CLIENT_ID")
            consumer_key = consumer_key or os.environ.get("SNAPTRADE_CONSUMER_KEY")
        except ImportError:
            pass
    if not client_id or not consumer_key:
        sys.exit("Set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY (env or .env).")
    return SnapTrade(consumer_key=consumer_key, client_id=client_id)


def _body(resp):
    return resp.body if hasattr(resp, "body") else resp


def cmd_register(args: argparse.Namespace) -> None:
    client = _client()
    try:
        resp = client.authentication.register_snap_trade_user(body={"userId": args.user_id})
        data = _body(resp)
        secret = data.get("userSecret")
        print("\nRegistered SnapTrade user.")
        print(f"  SNAPTRADE_USER_ID={args.user_id}")
        print(f"  SNAPTRADE_USER_SECRET={secret}")
    except Exception as e:  # user may already exist
        print(f"register failed ({str(e)[:120]}).")
        print("If the user already exists, reuse its saved secret, or reset it via the SnapTrade dashboard.")
        secret = args.user_secret

    if not secret:
        print("\nNo user secret available; re-run with --user-secret once you have it to get the link.")
        return

    login = client.authentication.login_snap_trade_user(user_id=args.user_id, user_secret=secret)
    url = _body(login).get("redirectURI")
    print("\nOpen this URL in a browser and connect Wealthsimple:\n")
    print(f"  {url}\n")
    print("Then run:  python scripts/snaptrade_connect.py accounts "
          f"--user-id {args.user_id} --user-secret {secret}")


def cmd_accounts(args: argparse.Namespace) -> None:
    client = _client()
    resp = client.account_information.list_user_accounts(
        user_id=args.user_id, user_secret=args.user_secret
    )
    accounts = _body(resp)
    if not accounts:
        print("No accounts yet — finish the connection step in the browser first.")
        return
    print("\nConnected accounts:")
    for a in accounts:
        print(f"  SNAPTRADE_ACCOUNT_ID={a.get('id')}  "
              f"[{a.get('institution_name')} · {a.get('name')} · {a.get('number')}]")


def main() -> None:
    p = argparse.ArgumentParser(description="SnapTrade one-time connection helper.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("register", help="register a user + print the connect URL")
    r.add_argument("--user-id", required=True)
    r.add_argument("--user-secret", default=None, help="reuse if the user already exists")
    r.set_defaults(func=cmd_register)

    a = sub.add_parser("accounts", help="list connected accounts (after linking)")
    a.add_argument("--user-id", required=True)
    a.add_argument("--user-secret", required=True)
    a.set_defaults(func=cmd_accounts)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
