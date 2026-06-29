"""Test isolation — the suite must NEVER touch a real venue or the live database.

Boardroom runs on the operator's own machine, where ``.env`` holds real Kraken /
SnapTrade credentials, ``LIVE_TRADING``, and the Supabase service key. Pydantic's
``Settings`` reads that ``.env`` by default — so without isolation, running
``pytest`` on that machine picks up live credentials and the broker/loop tests
attempt REAL orders and write to the PRODUCTION database (observed: a broker test
submitting a live Kraken AddOrder, and loop tests writing to live Supabase).

This autouse fixture makes every test hermetic: it strips all sensitive env vars,
forces ``LIVE_TRADING`` off, stops ``Settings`` from reading ``.env``, and clears
the settings cache before and after each test. It is defense in depth around the
one thing that spends real money — tests stay fully offline regardless of the
machine they run on.
"""

from __future__ import annotations

import pytest

from boardroom.config import Settings, get_settings

#: Anything that could point the system at a real venue, the live DB, or live mode.
_SENSITIVE = (
    "LIVE_TRADING",
    "KRAKEN_API_KEY",
    "KRAKEN_API_SECRET",
    "SNAPTRADE_CLIENT_ID",
    "SNAPTRADE_CONSUMER_KEY",
    "SNAPTRADE_USER_ID",
    "SNAPTRADE_USER_SECRET",
    "SNAPTRADE_ACCOUNT_ID",
    "IBKR_ACCOUNT_ID",
    "IBKR_GATEWAY_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "ANTHROPIC_API_KEY",
    "NEWS_API_KEY",
    "MARKET_DATA_API_KEY",
)


@pytest.fixture(autouse=True)
def hermetic_settings(monkeypatch):
    """Force a safe, credential-free configuration for every test."""
    for var in _SENSITIVE:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LIVE_TRADING", "false")
    # Never read the operator's real .env during tests.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
