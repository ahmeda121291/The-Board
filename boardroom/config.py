"""Configuration & the hard safety rails.

These caps are enforced in code, *outside* any agent's control. The CEO can
choose how to allocate within them; it can never widen them. Breaching a cap
forces all capital back to the floor (see ``risk.caps``).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration, loaded from environment / ``.env``.

    Secrets are typed as ``SecretStr`` so they never accidentally render in
    logs, repr, or LLM prompts.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ---- Master live switch --------------------------------------------------
    # The whole system runs the real decision loop in dry-run until this is
    # flipped true *after* the accounts are funded.
    live_trading: bool = Field(default=False, alias="LIVE_TRADING")

    # ---- Hard caps (CAD) — the CEO cannot override these ---------------------
    account_base_currency: str = Field(default="CAD", alias="ACCOUNT_BASE_CURRENCY")
    total_deployable_cad: float = Field(default=160.0, alias="TOTAL_DEPLOYABLE_CAD")
    per_trade_max_cad: float = Field(default=40.0, alias="PER_TRADE_MAX_CAD")
    event_hard_cap_cad: float = Field(default=10.0, alias="EVENT_HARD_CAP_CAD")
    daily_loss_limit_cad: float = Field(default=12.0, alias="DAILY_LOSS_LIMIT_CAD")
    max_drawdown_pct: float = Field(default=0.15, alias="MAX_DRAWDOWN_PCT")
    fee_drag_limit_pct: float = Field(default=0.05, alias="FEE_DRAG_LIMIT_PCT")

    # ---- LLM (the agents' brain) --------------------------------------------
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_model: str = Field(default="claude-opus-4-8", alias="BOARDROOM_LLM_MODEL")

    # ---- Supabase (state/metrics — no trading power) ------------------------
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_service_key: SecretStr | None = Field(default=None, alias="SUPABASE_SERVICE_KEY")

    # ---- Kraken (Yield + Event) — Milestone 6 -------------------------------
    kraken_api_key: SecretStr | None = Field(default=None, alias="KRAKEN_API_KEY")
    kraken_api_secret: SecretStr | None = Field(default=None, alias="KRAKEN_API_SECRET")

    # ---- IBKR (Directional) — Milestone 6 -----------------------------------
    ibkr_gateway_url: str = Field(default="https://localhost:5000", alias="IBKR_GATEWAY_URL")
    ibkr_account_id: str | None = Field(default=None, alias="IBKR_ACCOUNT_ID")

    # ---- Optional market data ------------------------------------------------
    market_data_api_key: SecretStr | None = Field(default=None, alias="MARKET_DATA_API_KEY")

    # ---- Derived helpers -----------------------------------------------------
    @property
    def caps(self) -> "RiskCaps":
        return RiskCaps(
            total_deployable_cad=self.total_deployable_cad,
            per_trade_max_cad=self.per_trade_max_cad,
            event_hard_cap_cad=self.event_hard_cap_cad,
            daily_loss_limit_cad=self.daily_loss_limit_cad,
            max_drawdown_pct=self.max_drawdown_pct,
            fee_drag_limit_pct=self.fee_drag_limit_pct,
        )

    def require_anthropic(self) -> str:
        if not self.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. The agents cannot reason without it."
            )
        return self.anthropic_api_key.get_secret_value()

    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


class RiskCaps:
    """Immutable snapshot of the hard caps, passed to the risk layer.

    Kept as a plain object (not a Settings subset) so it can be constructed in
    tests without touching the environment.
    """

    __slots__ = (
        "total_deployable_cad",
        "per_trade_max_cad",
        "event_hard_cap_cad",
        "daily_loss_limit_cad",
        "max_drawdown_pct",
        "fee_drag_limit_pct",
    )

    def __init__(
        self,
        total_deployable_cad: float,
        per_trade_max_cad: float,
        event_hard_cap_cad: float,
        daily_loss_limit_cad: float,
        max_drawdown_pct: float,
        fee_drag_limit_pct: float,
    ) -> None:
        self.total_deployable_cad = total_deployable_cad
        self.per_trade_max_cad = per_trade_max_cad
        self.event_hard_cap_cad = event_hard_cap_cad
        self.daily_loss_limit_cad = daily_loss_limit_cad
        self.max_drawdown_pct = max_drawdown_pct
        self.fee_drag_limit_pct = fee_drag_limit_pct

    def cap_for(self, division: str) -> float:
        """The maximum a single division may be sized to, in CAD."""
        if division == "event":
            return min(self.event_hard_cap_cad, self.per_trade_max_cad)
        return self.per_trade_max_cad


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
