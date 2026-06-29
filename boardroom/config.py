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

    # ---- Hard caps — PERCENT of the current total portfolio value -------------
    # The CEO cannot override these. They are fractions of live portfolio value,
    # NOT fixed dollar amounts, so every ceiling scales automatically as the
    # account grows (a $40 cap at $200 becomes $400 at $2,000 — same 20%). They
    # are resolved to CAD at decision time against current equity.
    # See docs/RISK_MODEL.md.
    account_base_currency: str = Field(default="CAD", alias="ACCOUNT_BASE_CURRENCY")
    total_deployable_pct: float = Field(default=0.80, alias="TOTAL_DEPLOYABLE_PCT")
    per_trade_max_pct: float = Field(default=0.20, alias="PER_TRADE_MAX_PCT")
    event_hard_cap_pct: float = Field(default=0.05, alias="EVENT_HARD_CAP_PCT")
    daily_loss_limit_pct: float = Field(default=0.06, alias="DAILY_LOSS_LIMIT_PCT")
    max_drawdown_pct: float = Field(default=0.15, alias="MAX_DRAWDOWN_PCT")
    fee_drag_limit_pct: float = Field(default=0.05, alias="FEE_DRAG_LIMIT_PCT")
    # Reference portfolio value, used when live equity isn't supplied (CLI
    # display, dry-run). Your funding baseline — caps resolve against this until
    # live equity is wired in.
    starting_portfolio_cad: float = Field(default=200.0, alias="STARTING_PORTFOLIO_CAD")

    # The floor's annualized carry — the hurdle every other division must beat.
    # Set this to the APR you actually earn (Kraken staking/lending). When the
    # live Kraken venue is wired it can refresh this automatically within a sanity
    # band; on any failure the system falls back to this configured value.
    floor_carry_apr: float = Field(default=0.04, alias="FLOOR_CARRY_APR")

    # Daily checkpoint time (UTC, "HH:MM") — when the CEO convenes once a day.
    # 19:00 UTC ≈ 3pm ET (summer) — INSIDE the equities regular session (closes
    # 4pm ET) so the Directional leg can actually fill. Crypto is 24/7. If you
    # drive runs via Task Scheduler --once, the trigger's LOCAL time is what
    # matters; set it to 15:00 local (always 1h before the 4pm-local close).
    checkpoint_utc: str = Field(default="19:00", alias="CHECKPOINT_UTC")

    # ---- LLM (the agents' brain) --------------------------------------------
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_model: str = Field(default="claude-opus-4-8", alias="BOARDROOM_LLM_MODEL")

    # ---- Supabase (state/metrics — no trading power) ------------------------
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_service_key: SecretStr | None = Field(default=None, alias="SUPABASE_SERVICE_KEY")

    # ---- Kraken (Yield + Event) — Milestone 6 -------------------------------
    kraken_api_key: SecretStr | None = Field(default=None, alias="KRAKEN_API_KEY")
    kraken_api_secret: SecretStr | None = Field(default=None, alias="KRAKEN_API_SECRET")

    # ---- IBKR (Directional / equities) — Client Portal Gateway --------------
    # Session-based: run the Client Portal Gateway locally and authenticate in a
    # browser (https://localhost:5000). No static API key. Set the account id.
    ibkr_gateway_url: str = Field(default="https://localhost:5000", alias="IBKR_GATEWAY_URL")
    ibkr_account_id: str | None = Field(default=None, alias="IBKR_ACCOUNT_ID")

    # ---- Optional market data ------------------------------------------------
    market_data_api_key: SecretStr | None = Field(default=None, alias="MARKET_DATA_API_KEY")
    # Optional news feed (CryptoPanic) for the Event division's catalyst gate.
    # Unset -> the Event division stays price-only, exactly as before.
    news_api_key: SecretStr | None = Field(default=None, alias="NEWS_API_KEY")

    # ---- Derived helpers -----------------------------------------------------
    @property
    def caps(self) -> "RiskCaps":
        return RiskCaps(
            total_deployable_pct=self.total_deployable_pct,
            per_trade_max_pct=self.per_trade_max_pct,
            event_hard_cap_pct=self.event_hard_cap_pct,
            daily_loss_limit_pct=self.daily_loss_limit_pct,
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
    """Immutable snapshot of the hard caps as FRACTIONS of portfolio value.

    Every cap is a percentage of the *current* total portfolio value, resolved
    to CAD against live equity at decision time — so a growing account gets
    proportionally larger (never stale) ceilings. Kept as a plain object (not a
    Settings subset) so it can be constructed in tests without the environment.
    """

    __slots__ = (
        "total_deployable_pct",
        "per_trade_max_pct",
        "event_hard_cap_pct",
        "daily_loss_limit_pct",
        "max_drawdown_pct",
        "fee_drag_limit_pct",
    )

    def __init__(
        self,
        total_deployable_pct: float,
        per_trade_max_pct: float,
        event_hard_cap_pct: float,
        daily_loss_limit_pct: float,
        max_drawdown_pct: float,
        fee_drag_limit_pct: float,
    ) -> None:
        self.total_deployable_pct = total_deployable_pct
        self.per_trade_max_pct = per_trade_max_pct
        self.event_hard_cap_pct = event_hard_cap_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.fee_drag_limit_pct = fee_drag_limit_pct

    # ---- resolve fractions to CAD against the current portfolio value -------
    def deployable_cad(self, portfolio_value_cad: float) -> float:
        """Max CAD the agents may deploy out of the floor."""
        return self.total_deployable_pct * max(0.0, portfolio_value_cad)

    def per_trade_cad(self, portfolio_value_cad: float) -> float:
        return self.per_trade_max_pct * max(0.0, portfolio_value_cad)

    def daily_loss_limit_cad(self, portfolio_value_cad: float) -> float:
        return self.daily_loss_limit_pct * max(0.0, portfolio_value_cad)

    def cap_for(self, division: str, portfolio_value_cad: float) -> float:
        """The maximum a single division may be sized to, in CAD, at this
        portfolio value. Event is hard-capped to the smaller of its own cap and
        the per-trade cap."""
        pv = max(0.0, portfolio_value_cad)
        if division == "event":
            return min(self.event_hard_cap_pct, self.per_trade_max_pct) * pv
        return self.per_trade_max_pct * pv


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
