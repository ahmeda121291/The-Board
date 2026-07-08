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


#: Cached pair names per quote currency — listings change rarely, one fetch per
#: process is plenty. Only successful lookups are cached, so a transient
#: failure retries on the next checkpoint.
_pairs_cache: dict[str, frozenset[str]] = {}


def tradable_pairs_for(quote: str = "CAD", timeout: float = 15.0) -> frozenset[str] | None:
    """Every pair name Kraken actually lists in ``quote`` (public AssetPairs).

    Includes both the ``altname`` (e.g. ``SOLCAD``) and the compact ``wsname``
    (``SOL/CAD`` → ``SOLCAD``) so a membership test against ``exec_pair_for``
    output is reliable. Returns ``None`` on any failure — callers must then
    fall back to letting execution error cleanly, never to a static guess.
    """
    q = (quote or "CAD").upper()
    if q in _pairs_cache:
        return _pairs_cache[q]
    try:
        import httpx  # lazy: keep package importable offline

        resp = httpx.get(f"{_API}/0/public/AssetPairs", timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("error"):
            return None
        pairs: set[str] = set()
        for info in payload["result"].values():
            ws = str(info.get("wsname") or "").upper()
            alt = str(info.get("altname") or "").upper()
            if ws.endswith(f"/{q}"):
                pairs.add(ws.replace("/", ""))
                if alt:
                    pairs.add(alt)
            elif alt.endswith(q):
                pairs.add(alt)
        if not pairs:
            return None
        _pairs_cache[q] = frozenset(pairs)
        return _pairs_cache[q]
    except Exception:
        return None


def tradable_cad_pairs(timeout: float = 15.0) -> frozenset[str] | None:
    """Back-compat alias: the CAD-quoted pair list."""
    return tradable_pairs_for("CAD", timeout=timeout)


def quote_to_cad_rate(quote: str, timeout: float = 15.0) -> float | None:
    """CAD per 1 unit of ``quote`` (USDCAD ≈ 1.37). 1.0 for CAD; None on failure.

    The system's risk unit is CAD everywhere (caps, equity, P&L); when the
    account is funded in another currency this rate converts at the broker
    boundary. Never guessed — a failed lookup returns None and the caller must
    refuse to size an order rather than trade at a stale/wrong rate.
    """
    q = (quote or "CAD").upper()
    if q == "CAD":
        return 1.0
    try:
        import httpx

        resp = httpx.get(f"{_API}/0/public/Ticker", params={"pair": f"{q}CAD"}, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        result = payload.get("result") or {}
        if payload.get("error") or not result:
            return None
        rate = float(result[next(iter(result))]["c"][0])
        return rate if rate > 0 else None
    except Exception:
        return None


def exec_pair_for(symbol: str, quote: str = "CAD") -> str:
    """Translate a data-universe pair to the account's quote currency for orders.

    Our crypto signals run on USD-quoted pairs (deeper history), but the order
    must settle in the account's funding currency. A CAD account can't buy
    ``XBTUSD`` (no USD balance) — it buys ``XBTCAD``. So swap a trailing USD/USDT
    quote for the account quote. Already-correct pairs pass through unchanged.
    """
    s = symbol.upper()
    q = quote.upper()
    for stub in ("USDT", "USDC", "USD"):
        if s.endswith(stub) and not s.endswith(q):
            return s[: -len(stub)] + q
    return s


class KrakenBroker(Broker):
    venue = Venue.KRAKEN
    supports_withdrawal = False  # never enabled; no withdraw code exists here

    def __init__(self, *, cad_asset: str = "ZCAD") -> None:
        self._settings = get_settings()
        self._cad_asset = cad_asset
        # The account's funding/quote currency — live orders settle in this, so
        # USD-quoted signal pairs are translated to it before execution.
        self._quote_currency = getattr(self._settings, "account_base_currency", "CAD") or "CAD"

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
        payload = resp.json()
        # An unknown pair (e.g. a coin with no CAD market) comes back as an error
        # with an empty result — surface a clear message instead of KeyError.
        result = payload.get("result") or {}
        if payload.get("error") or not result:
            raise RuntimeError(f"Kraken: no market for pair {pair} ({payload.get('error')})")
        key = next(iter(result))
        return float(result[key]["c"][0])  # last trade close price

    def _ticker_full(self, pair: str) -> tuple[float, float]:
        """(last_price, today_open) for a pair — used to value a holding and
        compute its intraday change. Raises on an unknown pair (caller skips)."""
        import httpx

        resp = httpx.get(f"{_API}/0/public/Ticker", params={"pair": pair}, timeout=20.0)
        resp.raise_for_status()
        payload = resp.json()
        result = payload.get("result") or {}
        if payload.get("error") or not result:
            raise RuntimeError(f"Kraken: no market for pair {pair} ({payload.get('error')})")
        key = next(iter(result))
        row = result[key]
        last = float(row["c"][0])         # last trade close
        opn = float(row["o"])             # today's opening price
        return last, opn

    def get_positions(self) -> list[dict]:
        """Read crypto holdings from the Balance endpoint and value each in CAD.

        Returns ``{symbol, qty, market_value_cad, day_change_pct}`` per coin held
        (fiat cash is excluded — that's reported by ``get_cash_cad``). Each coin
        is priced via the account-quote market (``{ASSET}USD`` when USD-funded,
        ``{ASSET}CAD`` when CAD-funded) and converted to CAD at the live FX
        rate; a CAD-market fallback covers coins missing the quote market. A
        coin that can't be priced (or the FX rate being unavailable) is listed
        unpriced rather than guessed, so the numbers shown are always real.
        Best-effort: returns what it can, never raises into the loop.
        """
        if not self._has_creds:
            return []
        try:
            balances = self._private("Balance")
        except Exception:
            return []
        quote = self._quote_currency
        rate = quote_to_cad_rate(quote)  # 1.0 in CAD mode; None on FX failure
        out: list[dict] = []
        for asset, amount_str in (balances or {}).items():
            try:
                qty = float(amount_str)
            except (TypeError, ValueError):
                continue
            if qty <= 1e-8:
                continue  # dust / zero
            if asset.upper().startswith("Z") or asset == self._cad_asset:
                continue  # fiat (ZCAD/ZUSD/ZEUR…) is cash, not a coin holding
            base = _normalize_kraken_asset(asset)
            last = opn = None
            to_cad = rate
            try:
                last, opn = self._ticker_full(f"{base}{quote}")
            except Exception:
                if quote != "CAD":
                    try:
                        last, opn = self._ticker_full(f"{base}CAD")
                        to_cad = 1.0
                    except Exception:
                        pass
            if last is None or to_cad is None:
                # No priceable market (or no FX rate) — list the coin without a
                # fabricated value rather than dropping it silently.
                out.append(
                    {"symbol": base, "qty": round(qty, 8), "market_value_cad": None,
                     "day_change_pct": None}
                )
                continue
            day_change = ((last - opn) / opn) if opn else None
            out.append(
                {
                    "symbol": base,
                    "qty": round(qty, 8),
                    "market_value_cad": round(qty * last * to_cad, 2),
                    "day_change_pct": round(day_change, 4) if day_change is not None else None,
                }
            )
        return out

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
        """Fiat cash valued in CAD — ZCAD at face value plus ZUSD converted at
        the live USDCAD rate. Handles both funding modes (and the transition:
        a half-converted account is simply the sum). If the FX rate is
        unavailable, USD is counted at 1:1 — an UNDERstatement, so the caps
        that resolve against equity err small, never large."""
        if not self._has_creds:
            return 0.0
        bal = self._private("Balance")
        cash = float(bal.get(self._cad_asset, 0.0))
        usd = float(bal.get("ZUSD", 0.0))
        if usd > 1e-9:
            rate = quote_to_cad_rate("USD")
            cash += usd * (rate if rate else 1.0)
        return cash

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

        # Execute in the ACCOUNT's quote currency. The data/signal universe is
        # USD-quoted (deeper history), but the order must settle in whatever
        # fiat the account actually holds — a CAD-funded account buys CAD
        # pairs, a USD-funded account buys USD pairs. Coins with no market in
        # that quote raise here and are skipped upstream (executability gate).
        exec_pair = exec_pair_for(order.symbol, self._quote_currency)
        price = self._ticker_price(exec_pair)
        # The system's risk unit is CAD: sizing, caps, and P&L are CAD numbers.
        # Convert the CAD notional into the EXEC PAIR's own quote currency at
        # the live FX rate BEFORE sizing the volume — otherwise a $25 CAD
        # intent becomes a $25 USD (~$34 CAD) order and quietly breaches the
        # caps. The pair's quote, not the account's: a legacy CAD-pair sell on
        # a USD-funded account prices in CAD and must size in CAD. No rate,
        # no trade: a clean error beats a mis-sized live order.
        pair_quote = next(
            (q for q in ("USDT", "USDC", "USD", "CAD") if exec_pair.endswith(q)),
            self._quote_currency,
        )
        rate = quote_to_cad_rate("USD" if pair_quote in ("USDT", "USDC") else pair_quote)
        if rate is None or rate <= 0:
            raise RuntimeError(
                f"Kraken: no CAD FX rate for {pair_quote} — refusing to size order"
            )
        notional_quote = order.notional_cad / rate
        # Closing a position sells the exact held quantity; opening sizes from
        # the (quote-converted) notional.
        volume = (
            round(order.base_qty, 8)
            if order.base_qty is not None
            else volume_from_notional(notional_quote, price)
        )
        payload = {
            "pair": exec_pair,
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


def _normalize_kraken_asset(asset: str) -> str:
    """Map a Kraken Balance asset code to a tradable base symbol.

    Kraken's legacy 4-char codes are X-prefixed (XXBT→XBT, XETH→ETH, XXRP→XRP,
    XLTC→LTC, XXDG→XDG); newer assets (SOL, ADA, DOT, USDC…) are already clean.
    Staked variants carry suffixes like ``.S``/``.F``/``.B`` (ETH2.S, DOT.S) —
    we strip those so the staked position prices against the spot pair.
    """
    code = asset.split(".")[0]  # drop staking suffix (.S, .F, .B, .M …)
    if len(code) == 4 and code.startswith("X"):
        return code[1:]         # XXBT→XBT, XETH→ETH
    return code
