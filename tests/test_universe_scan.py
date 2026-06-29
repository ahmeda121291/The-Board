"""Multi-symbol universe scanning — divisions pitch one idea per qualifying symbol."""

from functools import partial

from boardroom.data.sources import synthetic_bars
from boardroom.divisions.directional import DirectionalDivision
from boardroom.schemas import Venue


def _fetchers(n):
    # Distinct seeds/drifts so each symbol is a different series.
    return [
        partial(synthetic_bars, f"SYM{i}", Venue.IBKR, n=160, seed=100 + i,
                drift=0.001 + i * 0.0003, vol=0.012 + i * 0.001)
        for i in range(n)
    ]


def test_propose_all_scans_each_symbol():
    div = DirectionalDivision(fetchers=_fetchers(5), venue=Venue.IBKR)
    pitches = div.propose_all(bankroll_cad=200.0)
    # Every returned pitch is a distinct symbol; never more pitches than symbols.
    assert len(pitches) <= 5
    symbols = [p.symbol for p in pitches]
    assert len(symbols) == len(set(symbols))
    assert "scanned 5" in div.last_status or "of 5 scanned" in div.last_status


def test_propose_all_falls_back_to_single_fetch():
    div = DirectionalDivision(fetch=_fetchers(1)[0], venue=Venue.IBKR)
    pitches = div.propose_all(bankroll_cad=200.0)
    assert len(pitches) <= 1


def test_propose_all_empty_when_disabled():
    div = DirectionalDivision(fetchers=_fetchers(3), venue=Venue.IBKR, enabled=False)
    assert div.propose_all(bankroll_cad=200.0) == []
