"""Dynamic scan universe: every liquid USD-quoted Kraken pair, filtered from
raw exchange payloads — so a surging coin can't hide outside a curated list."""

from __future__ import annotations

from boardroom.data.sources import _usd_universe_from


def _pair(ws: str, alt: str) -> dict:
    return {"wsname": ws, "altname": alt}


def _tick(last: float, vol_24h: float) -> dict:
    return {"c": [str(last), "1"], "v": ["0", str(vol_24h)]}


ASSET_PAIRS = {
    "XXBTZUSD": _pair("XBT/USD", "XBTUSD"),
    "SOLUSD": _pair("SOL/USD", "SOLUSD"),
    "XDGUSD": _pair("XDG/USD", "XDGUSD"),          # DOGE under Kraken's name
    "PONZIUSD": _pair("PONZI/USD", "PONZIUSD"),    # illiquid junk
    "USDTZUSD": _pair("USDT/USD", "USDTUSD"),      # stablecoin — cash, not a trade
    "EURUSD": _pair("EUR/USD", "EURUSD"),          # fiat cross
    "XXBTZUSD.d": _pair("XBT/USD", "XBTUSD.D"),    # dark pool variant
    "AAPLXUSD": _pair("AAPLx/USD", "AAPLXUSD"),    # tokenized equity
    "SOLEUR": _pair("SOL/EUR", "SOLEUR"),          # wrong quote
}

TICKERS = {
    "XXBTZUSD": _tick(100_000.0, 500.0),   # $50M — deepest
    "SOLUSD": _tick(150.0, 40_000.0),      # $6M
    "XDGUSD": _tick(0.2, 5_000_000.0),     # $1M — DOGE finally scannable
    "PONZIUSD": _tick(0.01, 100_000.0),    # $1k — filtered out
    "USDTZUSD": _tick(1.0, 90_000_000.0),  # huge but excluded (stable)
    "EURUSD": _tick(1.1, 50_000_000.0),    # excluded (fiat)
    "AAPLXUSD": _tick(200.0, 100_000.0),   # excluded (tokenized stock)
    "SOLEUR": _tick(140.0, 1_000_000.0),   # excluded (EUR quote)
}


def test_filters_and_ranks_by_liquidity():
    got = _usd_universe_from(ASSET_PAIRS, TICKERS, min_usd_volume=250_000, max_pairs=150)
    assert got == ["XBTUSD", "SOLUSD", "XDGUSD"]  # volume-descending, junk gone


def test_doge_is_in_under_krakens_own_name():
    got = _usd_universe_from(ASSET_PAIRS, TICKERS, min_usd_volume=250_000, max_pairs=150)
    assert "XDGUSD" in got  # a DOGEUSD guess would never match the exchange


def test_max_pairs_caps_but_keeps_the_deepest():
    got = _usd_universe_from(ASSET_PAIRS, TICKERS, min_usd_volume=250_000, max_pairs=2)
    assert got == ["XBTUSD", "SOLUSD"]


def test_empty_payloads_yield_empty_not_crash():
    assert _usd_universe_from({}, {}, min_usd_volume=1, max_pairs=10) == []
