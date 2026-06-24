"""SnapTrade broker — the Directional leg via a connected brokerage (Wealthsimple).

SnapTrade is a brokerage aggregator: it gives a Canadian programmatic access to
Wealthsimple (which has no public developer API of its own). The app authenticates
with clientId + consumerKey; per-user access is scoped by userSecret + accountId
created when YOU connect your brokerage in SnapTrade's portal.

Same two hard safety properties as the other venues:
  1. ``supports_withdrawal`` is False; there is NO transfer/withdraw code path.
     SnapTrade trading access cannot move your funds.
  2. A live order is placed ONLY when the per-call ``live`` flag AND the global
     LIVE_TRADING flag AND full credentials are present; otherwise it simulates.

The SDK is imported lazily (optional dependency ``snaptrade-python-sdk``), so the
package imports and tests run without it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from boardroom.brokers.base import Broker, Fill, Order
from boardroom.config import get_settings
from boardroom.schemas import Venue


def build_force_order_payload(order: Order, account_id: str) -> dict:
    """Pure builder for a SnapTrade force-order body.

    Market orders size by ``notional_value`` (CAD) so fractional-share brokerages
    like Wealthsimple can fill an exact dollar amount; limit orders size by units
    computed from the limit price.
    """
    action = "BUY" if order.side.value == "buy" else "SELL"
    body: dict = {
        "account_id": account_id,
        "action": action,
        "time_in_force": "Day",
        "symbol": order.symbol,
    }
    if order.limit_price:
        body["order_type"] = "Limit"
        body["price"] = order.limit_price
        body["units"] = round(abs(order.notional_cad) / order.limit_price, 6)
    else:
        body["order_type"] = "Market"
        body["notional_value"] = {"amount": round(abs(order.notional_cad), 2), "currency": "CAD"}
    return body


class SnapTradeBroker(Broker):
    venue = Venue.SNAPTRADE
    supports_withdrawal = False  # never enabled; no transfer code path here

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None

    # ---- credentials / gating ------------------------------------------------
    @property
    def _configured(self) -> bool:
        s = self._settings
        return bool(
            s.snaptrade_client_id
            and s.snaptrade_consumer_key
            and s.snaptrade_user_id
            and s.snaptrade_user_secret
            and s.snaptrade_account_id
        )

    def _effective_live(self, live: bool) -> bool:
        return bool(live and self._settings.live_trading and self._configured)

    def _sdk(self):
        if self._client is None:
            from snaptrade_client import SnapTrade

            self._client = SnapTrade(
                consumer_key=self._settings.snaptrade_consumer_key.get_secret_value(),
                client_id=self._settings.snaptrade_client_id,
            )
        return self._client

    def _user_args(self) -> dict:
        return {
            "user_id": self._settings.snaptrade_user_id,
            "user_secret": self._settings.snaptrade_user_secret.get_secret_value(),
        }

    # ---- Broker interface ----------------------------------------------------
    def health_check(self) -> bool:
        if not self._configured:
            return False
        try:
            resp = self._sdk().account_information.list_user_accounts(**self._user_args())
            accounts = resp.body if hasattr(resp, "body") else resp
            ids = {str(a.get("id")) for a in accounts}
            return self._settings.snaptrade_account_id in ids
        except Exception:
            return False

    def get_cash_cad(self) -> float:
        if not self._configured:
            return 0.0
        resp = self._sdk().account_information.get_user_account_balance(
            account_id=self._settings.snaptrade_account_id, **self._user_args()
        )
        balances = resp.body if hasattr(resp, "body") else resp
        for b in balances:
            cur = (b.get("currency") or {}).get("code") if isinstance(b.get("currency"), dict) else b.get("currency")
            if cur == "CAD":
                return float(b.get("cash") or 0.0)
        return 0.0

    def place_order(self, order: Order, *, live: bool) -> Fill:
        if not self._effective_live(live):
            return self._simulate(order)

        body = build_force_order_payload(order, self._settings.snaptrade_account_id)
        result = self._sdk().trading.place_force_order(**self._user_args(), **body)
        raw = result.body if hasattr(result, "body") else result
        fx = abs(order.notional_cad) * 0.015 if order.symbol.upper().endswith(("US", "USD")) else 0.0
        return Fill(
            client_order_id=order.client_order_id,
            venue=self.venue,
            symbol=order.symbol,
            side=order.side,
            filled_qty=0.0,  # SnapTrade fills arrive async; poll order status
            avg_price=order.limit_price or 0.0,
            fee_cad=0.0,
            fx_cost_cad=fx,
            filled_at=datetime.now(timezone.utc),
            is_live=True,
            raw={"snaptrade": str(raw)[:500]},
        )

    def _simulate(self, order: Order) -> Fill:
        price = order.limit_price or 1.0
        return Fill(
            client_order_id=order.client_order_id,
            venue=self.venue,
            symbol=order.symbol,
            side=order.side,
            filled_qty=order.notional_cad / price if price else 0.0,
            avg_price=price,
            fee_cad=0.0,
            fx_cost_cad=0.0,
            filled_at=datetime.now(timezone.utc),
            is_live=False,
            raw={"simulated": True},
        )
