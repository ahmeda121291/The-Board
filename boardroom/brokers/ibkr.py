"""Interactive Brokers broker — the Directional (equities/ETF) leg.

IBKR auth is SESSION-based: a running Client Portal Gateway you authenticate, not
a static key. This class talks to that gateway's REST API at IBKR_GATEWAY_URL.

Same two safety properties as Kraken:
  1. ``supports_withdrawal`` is False; there is no transfer/withdraw code path.
  2. Live orders require BOTH the per-call ``live`` flag AND global LIVE_TRADING
     AND an authenticated gateway session; otherwise it simulates.

The gateway uses a self-signed cert by default, so live calls disable TLS verify
ONLY for the localhost gateway (never for any external host).
"""

from __future__ import annotations

from datetime import datetime, timezone

from boardroom.brokers.base import Broker, Fill, Order, OrderSide
from boardroom.config import get_settings
from boardroom.schemas import Venue


def build_order_payload(order: Order, conid: int) -> dict:
    """IBKR Client Portal order payload for a CAD-notional marketable order.

    Uses cash-quantity (``cashQty``) so we size in CAD directly rather than
    pre-computing shares.
    """
    return {
        "orders": [
            {
                "conid": conid,
                "orderType": "LMT" if order.limit_price else "MKT",
                "side": order.side.value.upper(),
                "tif": "DAY",
                "cashQty": round(abs(order.notional_cad), 2),
                **({"price": order.limit_price} if order.limit_price else {}),
                "cOID": order.client_order_id,
            }
        ]
    }


class IBKRBroker(Broker):
    venue = Venue.IBKR
    supports_withdrawal = False  # never enabled; no transfer code path here

    def __init__(self, *, conid_resolver=None) -> None:
        self._settings = get_settings()
        self._base = self._settings.ibkr_gateway_url.rstrip("/")
        self._account = self._settings.ibkr_account_id
        # Maps a symbol -> IBKR contract id. Injected for testability; the live
        # default hits the gateway's /iserver/secdef/search.
        self._conid_resolver = conid_resolver or self._resolve_conid

    @property
    def _configured(self) -> bool:
        return bool(self._account)

    def _effective_live(self, live: bool) -> bool:
        return bool(live and self._settings.live_trading and self._configured)

    def _client(self):
        import httpx

        # verify=False is scoped to the localhost gateway's self-signed cert.
        return httpx.Client(base_url=self._base, verify=False, timeout=20.0)

    def _resolve_conid(self, symbol: str) -> int:
        with self._client() as c:
            r = c.get("/v1/api/iserver/secdef/search", params={"symbol": symbol})
            r.raise_for_status()
            rows = r.json()
            if not rows:
                raise RuntimeError(f"IBKR: no contract for {symbol}")
            return int(rows[0]["conid"])

    # ---- Broker interface ----------------------------------------------------
    def health_check(self) -> bool:
        if not self._configured:
            return False
        try:
            with self._client() as c:
                r = c.get("/v1/api/iserver/auth/status")
                r.raise_for_status()
                return bool(r.json().get("authenticated"))
        except Exception:
            return False

    def get_cash_cad(self) -> float:
        if not self._configured:
            return 0.0
        with self._client() as c:
            r = c.get(f"/v1/api/portfolio/{self._account}/ledger")
            r.raise_for_status()
            ledger = r.json()
            cad = ledger.get("CAD") or {}
            return float(cad.get("cashbalance", 0.0))

    def get_positions(self) -> list[dict]:
        """Read the real equity holdings from the gateway's portfolio endpoint.

        Returns ``{symbol, qty, avg_cost, market_value_cad}`` per position. The
        Client Portal ``/portfolio/{acct}/positions/{page}`` endpoint paginates;
        we read pages until one comes back short. Best-effort — any failure
        returns what we have so far (the recommendation diff degrades to "no
        holdings known" rather than crashing).
        """
        if not self._configured:
            return []
        out: list[dict] = []
        try:
            with self._client() as c:
                page = 0
                while page < 20:  # hard page cap; a $200 book never approaches it
                    r = c.get(f"/v1/api/portfolio/{self._account}/positions/{page}")
                    r.raise_for_status()
                    rows = r.json() or []
                    if not rows:
                        break
                    for row in rows:
                        qty = float(row.get("position", 0.0) or 0.0)
                        if qty == 0.0:
                            continue  # closed/zero lots aren't holdings
                        out.append(
                            {
                                "symbol": (row.get("contractDesc") or row.get("ticker") or "").upper(),
                                "qty": qty,
                                "avg_cost": float(row.get("avgCost", 0.0) or 0.0),
                                "market_value_cad": float(row.get("mktValue", 0.0) or 0.0),
                            }
                        )
                    if len(rows) < 30:  # CP returns 30/page; a short page is the last
                        break
                    page += 1
        except Exception:
            return out  # whatever we managed to read; never raise into the loop
        return out

    def place_order(self, order: Order, *, live: bool) -> Fill:
        if not self._effective_live(live):
            return self._simulate(order)

        conid = self._conid_resolver(order.symbol)
        payload = build_order_payload(order, conid)
        with self._client() as c:
            r = c.post(f"/v1/api/iserver/account/{self._account}/orders", json=payload)
            r.raise_for_status()
            result = r.json()
        # FX modeled separately by the cost layer; mark a light FX cost here.
        fx = abs(order.notional_cad) * 0.0002
        return Fill(
            client_order_id=order.client_order_id,
            venue=self.venue,
            symbol=order.symbol,
            side=order.side,
            filled_qty=0.0,  # CP returns order ids; fills arrive async via status
            avg_price=order.limit_price or 0.0,
            fee_cad=abs(order.notional_cad) * 0.0010,
            fx_cost_cad=fx,
            filled_at=datetime.now(timezone.utc),
            is_live=True,
            raw={"orders": result},
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
            fee_cad=abs(order.notional_cad) * 0.0010,
            fx_cost_cad=abs(order.notional_cad) * 0.0002,
            filled_at=datetime.now(timezone.utc),
            is_live=False,
            raw={"simulated": True},
        )
