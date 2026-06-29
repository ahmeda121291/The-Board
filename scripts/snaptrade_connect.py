#!/usr/bin/env python3
"""One-time SnapTrade connection helper — get USER_SECRET + ACCOUNT_ID.

Wealthsimple has no public dev API; SnapTrade brokers it. This script does the
one-time steps so you can fill SNAPTRADE_USER_SECRET and SNAPTRADE_ACCOUNT_ID in
your .env. It uses ONLY your app keys (SNAPTRADE_CLIENT_ID +
SNAPTRADE_CONSUMER_KEY), read from the environment / .env.

Commands:
    list-users     show SnapTrade users already registered under your keys
    register       register a user + print the Wealthsimple connect URL
    accounts       list connected accounts (run after linking in the browser)
    delete-user    remove a user (use to reset a stuck/duplicate registration)

Typical flow:
    python scripts/snaptrade_connect.py list-users
    python scripts/snaptrade_connect.py register --user-id ahmed-boardroom
    # open the printed URL, log into Wealthsimple, finish linking, then:
    python scripts/snaptrade_connect.py accounts --user-id ahmed-boardroom --user-secret <secret>

Run on a machine with network access to api.snaptrade.com.
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


def _err(e: Exception) -> str:
    """Full SnapTrade error detail incl. the response body (not truncated)."""
    parts = [f"{type(e).__name__}: {e}"]
    body = getattr(e, "body", None)
    if body:
        parts.append(f"body: {body}")
    return "\n".join(parts)


def cmd_list_users(args: argparse.Namespace) -> None:
    client = _client()
    try:
        resp = client.authentication.list_snap_trade_users()
        users = _body(resp)
        print("\nRegistered SnapTrade users under your keys:")
        if not users:
            print("  (none)")
        for u in users:
            print(f"  {u}")
        print("\nAuth works (your CLIENT_ID + CONSUMER_KEY are valid).")
    except Exception as e:
        print("\nlist-users failed — this usually means your CLIENT_ID or CONSUMER_KEY is wrong.")
        print(_err(e))


def cmd_register(args: argparse.Namespace) -> None:
    client = _client()
    secret = args.user_secret
    try:
        resp = client.authentication.register_snap_trade_user(body={"userId": args.user_id})
        data = _body(resp)
        secret = data.get("userSecret")
        print("\nRegistered SnapTrade user.")
        print(f"  SNAPTRADE_USER_ID={args.user_id}")
        print(f"  SNAPTRADE_USER_SECRET={secret}")
    except Exception as e:
        print(f"\nregister failed for user '{args.user_id}':")
        print(_err(e))
        print("\nIf this says the user already exists: either")
        print("  - reuse the saved secret with --user-secret, OR")
        print(f"  - reset it:  python scripts/snaptrade_connect.py delete-user --user-id {args.user_id}")
        print("    then run register again to get a fresh secret.")
        if not secret:
            return

    # connection_type="trade" is REQUIRED for the Directional leg to place orders.
    # SnapTrade connections default to READ-ONLY; without this the link is created
    # data-only and live equity orders are rejected (403 "Trading permissions have
    # not been enabled"). Pass --read-only to deliberately create a data-only link.
    connection_type = "read" if getattr(args, "read_only", False) else "trade"
    login = client.authentication.login_snap_trade_user(
        user_id=args.user_id, user_secret=secret, connection_type=connection_type
    )
    url = _body(login).get("redirectURI")
    print(f"\nOpen this URL in a browser and connect Wealthsimple ({connection_type} access):\n")
    print(f"  {url}\n")
    if connection_type == "trade":
        print("On the Wealthsimple consent screen, APPROVE trading — a read-only link "
              "leaves the equity leg in shadow mode (no real orders).\n")
    print("Then run:  python scripts/snaptrade_connect.py accounts "
          f"--user-id {args.user_id} --user-secret {secret}")


def cmd_accounts(args: argparse.Namespace) -> None:
    import json

    client = _client()
    try:
        resp = client.account_information.list_user_accounts(
            user_id=args.user_id, user_secret=args.user_secret
        )
    except Exception as e:
        print("\nCouldn't list accounts:")
        print(_err(e))
        return
    accounts = _body(resp)
    if not accounts:
        print("No accounts yet — finish the connection step in the browser first.")
        return

    print(f"\n{len(accounts)} account(s). Look for the one whose number contains 'HQ4'")
    print("and/or that holds your balance:\n")
    for a in accounts:
        bal = a.get("balance") or {}
        total = bal.get("total") if isinstance(bal, dict) else bal
        meta = a.get("meta") or {}
        # The brokerage's real account number often lives in meta.
        meta_num = meta.get("number") or meta.get("account_number") or meta.get("accountNumber")
        print(f"- id={a.get('id')}")
        print(f"    type/name : {a.get('name')}")
        print(f"    snap number: {a.get('number')}")
        print(f"    brokerage #: {meta_num or '(see meta below)'}")
        print(f"    balance    : {json.dumps(total) if total is not None else 'n/a'}")
        print(f"    status     : {a.get('sync_status') or a.get('status')}")
        if not meta_num and meta:
            print(f"    meta       : {json.dumps(meta)[:300]}")
        print()


def cmd_delete_user(args: argparse.Namespace) -> None:
    client = _client()
    try:
        client.authentication.delete_snap_trade_user(user_id=args.user_id)
        print(f"Deleted user '{args.user_id}'. You can now register it fresh.")
    except Exception as e:
        print("delete failed:")
        print(_err(e))


def main() -> None:
    p = argparse.ArgumentParser(description="SnapTrade one-time connection helper.")
    sub = p.add_subparsers(dest="cmd", required=True)

    lu = sub.add_parser("list-users", help="list registered users (auth check)")
    lu.set_defaults(func=cmd_list_users)

    r = sub.add_parser("register", help="register a user + print the connect URL")
    r.add_argument("--user-id", required=True)
    r.add_argument("--user-secret", default=None, help="reuse if the user already exists")
    r.add_argument(
        "--read-only",
        action="store_true",
        help="create a data-only link (default requests TRADE permission so the "
             "Directional leg can place live equity orders)",
    )
    r.set_defaults(func=cmd_register)

    a = sub.add_parser("accounts", help="list connected accounts (after linking)")
    a.add_argument("--user-id", required=True)
    a.add_argument("--user-secret", required=True)
    a.set_defaults(func=cmd_accounts)

    d = sub.add_parser("delete-user", help="remove a user to reset a stuck registration")
    d.add_argument("--user-id", required=True)
    d.set_defaults(func=cmd_delete_user)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
