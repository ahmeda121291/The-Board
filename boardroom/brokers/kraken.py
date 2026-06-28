"""Kraken broker — the Yield (floor) and Event legs.

Live order placement uses Kraken's REST private API. Two hard safety properties:

  1. ``supports_withdrawal`` is False and there is NO withdrawal code path here.
     The credential must be scoped trade+staking only; this class can't move
     funds off the exchange even if asked.
  2. A live order is placed ONLY when BOTH the per-call ``live`` flag AND the
     global ``LIVE_TRADING`` setting are true AND credentials are present.
     Otherwise it simulates (no network, no money), exactly like the stub.

Network is imported lazily and only touched on a genuinely live action, so the
package imports and tests run with no keys and no connectivity.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
from datetime import datetime, timezone

from boardroom.brokers.base import Broker, Fill, Order
from boardroom.config import get_settings
from boardroom.schemas import Venue

_API = "https://api.kraken.com"


def sign(path: str, data: dict, secret: str) -> str:
    """Kraken's API-Sign: HMAC-SHA512(path + SHA256(nonce + postdata), b64secret)."""
    postdata = urllib.parse.urlencode(data)
    encoded = (str(data["nonce"]) + postdata).encode()
    message = path.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()


def volume_from_notional(notional_cad: float, price: float) -> float:
    """Base-asset volume for a quote-CAD notional at ``price`` (quote per base)."""
    if price <= 0:
        raise ValueError("price must be positive")
    return round(notional_cad / price, 8)


class KrakenBroker(Broker):
    venue = Venue.KRAKEN
    supports_withdrawal = False  # never enabled; no withdraw code exists here

    def __init__(self, *, cad_asset: str = "ZCAD") -> None:
        self._settings = get_settings()
        self._cad_asset = cad_asset

    # ---- credentials / gating ------------------------------------------------
    @property
    def _has_creds(self) -> bool:
        return bool(self._settings.kraken_api_key and self._settings.kraken_api_secret)

    def _effective_live(self, live: bool) -> bool:
        return bool(live and self._settings.live_trading and self._has_creds)

    # ---- private REST --------------------------------------------------------
    def _private(self, method: str, data: dict | None = None) -> dict:
        import httpx

        data = dict(data or {})
        data["nonce"] = int(time.time() * 1000)
        path = f"/0/private/{method}"
        headers = {
            "API-Key": self._settings.kraken_api_key.get_secret_value(),
            "API-Sign": sign(path, data, self._settings.kraken_api_secret.get_secret_value()),
        }
        resp = httpx.post(_API + path, data=data, headers=headers, timeout=20.0)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("error"):
            raise RuntimeError(f"Kraken {method} error: {payload['error']}")
        return payload["result"]

    def _ticker_price(self, pair: str) -> float:
        import httpx

        resp = httpx.get(f"{_API}/0/public/Ticker", params={"pair": pair}, timeout=20.0)
        resp.raise_for_status()
        result = resp.json()["result"]
        key = next(iter(result))
        return float(result[key]["c"][0])  # last trade close price

    # ---- Broker interface ----------------------------------------------------
    def health_check(self) -> bool:
        if not self._has_creds:
            return False
        try:
            self._private("Balance")
            return True
        except Exception:
            return False

    def get_cash_cad(self) -> float:
        if not self._has_creds:
            return 0.0
        bal = self._private("Balance")
        return float(bal.get(self._cad_asset, 0.0))

    # ---- floor APR provider --------------------------------------------------
    def staking_apr(self, assets: tuple[str, ...] = ("USD", "USDC", "USDT", "DAI")) -> float:
        """Best available staking/earn APR (as a FRACTION) across ``assets``.

        Queries Kraken's Earn strategies and returns the largest *low* (i.e.
        conservative) APR estimate among the requested low-risk floor assets,
        converted from percent to a fraction. Raises if no usable estimate is
        found — the caller (:meth:`YieldModel.resolve_carry`) treats any raise as
        "keep the configured carry", so a missing/changed endpoint never corrupts
        the hurdle. Requires credentials.
        """
        if not self._has_creds:
            raise RuntimeError("no Kraken credentials for staking APR")
        result = self._private("Earn/Strategies")
        items = result.get("items", result) if isinstance(result, dict) else result
        wanted = {a.upper() for a in assets}
        best: float | None = None
        for it in items or []:
            if not isinstance(it, dict):
                continue
            if it.get("asset", "").upper() not in wanted:
                continue
            est = it.get("apr_estimate") or {}
            low = est.get("low")
            if low is None:
                continue
            apr_fraction = float(low) / 100.0  # Kraken reports percent
            if best is None or apr_fraction > best:
                best = apr_fraction
        if best is None:
            raise RuntimeError("no Earn APR estimate for the requested floor assets")
        return best

    def place_order(self, order: Order, *, live: bool) -> Fill:
        effective_live = self._effective_live(live)
        if not effective_live:
            return self._simulate(order)

        price = self._ticker_price(order.symbol)
        volume = volume_from_notional(order.notional_cad, price)
        payload = {
            "pair": order.symbol,
            "type": order.side.value,
            "ordertype": "limit" if order.limit_price else "market",
            "volume": volume,
            "userref": _userref(order.client_order_id),
        }
        if order.limit_price:
            payload["price"] = order.limit_price
        result = self._private("AddOrder", payload)
        fee = abs(order.notional_cad) * 0.0026
        return Fill(
            client_order_id=order.client_order_id,
            venue=self.venue,
            symbol=order.symbol,
            side=order.side,
            filled_qty=volume,
            avg_price=price,
            fee_cad=fee,
            fx_cost_cad=0.0,
            filled_at=datetime.now(timezone.utc),
            is_live=True,
            raw=result,
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
            fee_cad=abs(order.notional_cad) * 0.0026,
            fx_cost_cad=0.0,
            filled_at=datetime.now(timezone.utc),
            is_live=False,
            raw={"simulated": True},
        )


def _userref(client_order_id: str) -> int:
    # Kraken userref is a 32-bit int; derive a stable one from the client id.
    return int(hashlib.sha256(client_order_id.encode()).hexdigest(), 16) % (2**31)
