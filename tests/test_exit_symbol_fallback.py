"""Exit resolution must find a price series for LEGACY execution symbols.

Positions store the pair they executed on (SOLCAD in the CAD-funded era), but
the resolution price cache is keyed by the analysis symbols (SOLUSD). Without
a base-asset fallback, past-horizon positions sit open in silence forever —
four SOLCAD positions did exactly that for three days."""

from __future__ import annotations

import datetime as dt
import uuid

from boardroom.brokers.base import Order, OrderSide
from boardroom.brokers.kraken import KrakenBroker
from boardroom.factory import build_default_org
from boardroom.persistence.repository import InMemoryRepository, OpenPosition


def _pos(symbol: str, *, days_ago: float = 6.0, live: bool = False) -> OpenPosition:
    return OpenPosition(
        decision_id=str(uuid.uuid4()), division="crypto_trend", venue="kraken",
        symbol=symbol, size_cad=25.0, predicted_return=0.02, predicted_confidence=0.6,
        cost_cad=0.1, stop_fraction=0.08, band_low=-0.11, band_high=0.15,
        horizon_days=5.0, live=live, qty=0.5,
        opened_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago),
    )


def test_legacy_cad_symbol_resolves_against_usd_series():
    # The synthetic org fetches XBTUSD/ETHUSD; the position holds XBTCAD.
    # Past its 5-day horizon, the fallback must still resolve it (paper close).
    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)
    pos = _pos("XBTCAD")
    repo.save_open_position(pos)

    updates = org.resolve_positions()

    assert updates, "past-horizon legacy position must resolve"
    assert repo.open_positions() == []
    assert any(e == "position_resolved" for e, _ in repo.audit_log)
    # The outcome names the coin — the scoreboard shows WHAT traded, not just who.
    assert repo.outcomes[-1].symbol == "XBTCAD"


def test_unpriceable_position_is_audited_not_silent():
    repo = InMemoryRepository()
    org = build_default_org(data_mode="synthetic", repo=repo)
    repo.save_open_position(_pos("ZZZCAD"))

    org.resolve_positions()

    stuck = [p for e, p in repo.audit_log if e == "resolution_no_data"]
    assert stuck and stuck[0]["symbols"] == ["ZZZCAD"]
    assert len(repo.open_positions()) == 1  # still open — but no longer invisibly


def test_cad_pair_order_sizes_in_cad_even_when_usd_funded(monkeypatch):
    """A legacy SOLCAD sell prices in CAD — converting its notional by the
    ACCOUNT quote (USD) would mis-size the volume by the FX rate."""
    kb = KrakenBroker()
    kb._quote_currency = "USD"
    monkeypatch.setattr(type(kb), "_has_creds", property(lambda self: True))
    monkeypatch.setattr(kb._settings, "live_trading", True)
    monkeypatch.setattr(kb, "_ticker_price", lambda pair: 150.0)  # CAD price
    sent = {}
    monkeypatch.setattr(kb, "_private", lambda method, data: sent.update(data) or {"txid": ["T"]})

    order = Order(
        symbol="SOLCAD", side=OrderSide.SELL, notional_cad=25.0,
        division="crypto_trend", client_order_id=str(uuid.uuid4()),
    )
    kb.place_order(order, live=True)

    assert sent["pair"] == "SOLCAD"
    # 25 CAD at a 150-CAD price -> 0.16666667 SOL (no USD conversion applied).
    assert abs(float(sent["volume"]) - round(25.0 / 150.0, 8)) < 1e-9
