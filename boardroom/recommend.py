"""The equities recommendation engine — advisory, never auto-traded.

The system auto-trades crypto only. For stocks it is an *analyst*: it scans a
wide universe, ranks the survivors deterministically, and publishes a target
("recommended") portfolio. Twice a day it also reads the user's ACTUAL IBKR
holdings and diffs them against the recommendation to produce plain-English
buy / sell / trim / add actions.

The grounding law still holds (scope §2): every number here — score, weight,
target dollars, the buy/sell deltas — is computed by this module from real
pitch data. The LLM only writes the narrative summary (``boardroom.agents.advisor``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from boardroom.ceo.hurdle import risk_adjusted_score
from boardroom.config import RiskCaps
from boardroom.schemas import Pitch, Venue


# Equity venues whose pitches are eligible for the recommended stock portfolio.
_EQUITY_VENUES = {Venue.IBKR}


@dataclass
class RecommendedHolding:
    """One name in the target portfolio, with code-computed sizing."""

    symbol: str
    rank: int
    score: float                 # risk-adjusted score (net excess edge / unit risk)
    expected_return: float       # fractional
    confidence: float            # [0,1]
    price: float                 # reference (last) price the pitch was built on
    target_weight: float         # fraction of the stock book
    target_cad: float            # target dollar allocation
    horizon_days: float
    division: str
    rationale: str = ""          # LLM narrative (optional; filled later)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "rank": self.rank,
            "score": round(self.score, 5),
            "expected_return": round(self.expected_return, 5),
            "confidence": round(self.confidence, 4),
            "price": round(self.price, 4),
            "target_weight": round(self.target_weight, 4),
            "target_cad": round(self.target_cad, 2),
            "horizon_days": self.horizon_days,
            "division": self.division,
            "rationale": self.rationale,
        }


@dataclass
class CurrentHolding:
    """A position actually held in the IBKR account (read from the broker)."""

    symbol: str
    qty: float
    avg_cost: float
    market_value_cad: float

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "qty": round(self.qty, 6),
            "avg_cost": round(self.avg_cost, 4),
            "market_value_cad": round(self.market_value_cad, 2),
        }


@dataclass
class PortfolioAction:
    """A single rebalancing instruction the user executes by hand in IBKR."""

    symbol: str
    action: str          # "buy" | "add" | "trim" | "sell" | "hold"
    current_cad: float
    target_cad: float
    delta_cad: float     # target - current (positive = buy more)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "current_cad": round(self.current_cad, 2),
            "target_cad": round(self.target_cad, 2),
            "delta_cad": round(self.delta_cad, 2),
            "reason": self.reason,
        }


@dataclass
class RecommendationReport:
    """The full advisory output for one checkpoint."""

    generated_at: str
    stock_equity_cad: float
    cash_weight: float
    holdings: list[RecommendedHolding] = field(default_factory=list)
    current: list[CurrentHolding] = field(default_factory=list)
    actions: list[PortfolioAction] = field(default_factory=list)
    narrative: str = ""
    universe_size: int = 0

    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "stock_equity_cad": round(self.stock_equity_cad, 2),
            "cash_weight": round(self.cash_weight, 4),
            "holdings": [h.as_dict() for h in self.holdings],
            "current": [c.as_dict() for c in self.current],
            "actions": [a.as_dict() for a in self.actions],
            "narrative": self.narrative,
            "universe_size": self.universe_size,
        }


def _price_of(pitch: Pitch) -> float:
    return float(pitch.signals.features.get("price", 0.0))


def build_recommended_portfolio(
    pitches: list[Pitch],
    *,
    hurdle_rate: float,
    stock_equity_cad: float,
    caps: RiskCaps,
    top_n: int = 8,
) -> list[RecommendedHolding]:
    """Rank equity pitches and turn the survivors into a weighted target book.

    Deterministic end to end:
      1. keep equity-venue pitches that beat the floor net of cost (score > 0),
      2. rank by risk-adjusted score (the same metric the CEO uses for crypto),
      3. weight proportional to score, cap any single name at the per-trade cap,
      4. scale so the book stays within the deployable cap (the rest is cash).
    """
    equities = [p for p in pitches if p.venue in _EQUITY_VENUES and _price_of(p) > 0]
    scored = [(p, risk_adjusted_score(p, hurdle_rate)) for p in equities]
    survivors = sorted(
        ((p, s) for p, s in scored if s > 0), key=lambda t: t[1], reverse=True
    )[:top_n]
    if not survivors or stock_equity_cad <= 0:
        return []

    deployable = caps.total_deployable_pct           # e.g. 0.80
    per_name_cap = caps.per_trade_max_pct            # e.g. 0.20
    total_score = sum(s for _, s in survivors)

    holdings: list[RecommendedHolding] = []
    for rank, (p, score) in enumerate(survivors, start=1):
        raw_weight = (score / total_score) if total_score > 0 else (1.0 / len(survivors))
        weight = min(raw_weight * deployable, per_name_cap)
        holdings.append(
            RecommendedHolding(
                symbol=p.symbol,
                rank=rank,
                score=score,
                expected_return=p.expected_return,
                confidence=p.confidence,
                price=_price_of(p),
                target_weight=weight,
                target_cad=round(weight * stock_equity_cad, 2),
                horizon_days=p.time_horizon_days,
                division=p.division.value,
            )
        )
    return holdings


def diff_portfolio(
    current: list[CurrentHolding],
    recommended: list[RecommendedHolding],
    *,
    rebalance_band: float = 0.25,
    min_action_cad: float = 10.0,
) -> list[PortfolioAction]:
    """Compare the held book to the target book → ordered buy/sell/trim actions.

    A delta is only surfaced as an action when it exceeds a band (the larger of
    ``min_action_cad`` and ``rebalance_band`` × target) — small drifts read as
    HOLD so the user isn't told to trade noise. Sells (names not recommended)
    come first, then buys/adds, then holds.
    """
    cur_by_sym = {c.symbol: c for c in current}
    rec_by_sym = {h.symbol: h for h in recommended}
    actions: list[PortfolioAction] = []

    # Names held but no longer recommended → sell.
    for sym, c in cur_by_sym.items():
        if sym not in rec_by_sym:
            actions.append(
                PortfolioAction(
                    symbol=sym,
                    action="sell",
                    current_cad=c.market_value_cad,
                    target_cad=0.0,
                    delta_cad=-c.market_value_cad,
                    reason="not in the recommended portfolio",
                )
            )

    # Recommended names → buy / add / trim / hold vs what's held.
    for sym, h in rec_by_sym.items():
        c = cur_by_sym.get(sym)
        current_cad = c.market_value_cad if c else 0.0
        delta = h.target_cad - current_cad
        band = max(min_action_cad, rebalance_band * h.target_cad)
        if c is None:
            action, reason = "buy", f"new — target {h.target_weight:.0%} of the stock book"
        elif delta > band:
            action, reason = "add", "below target weight"
        elif delta < -band:
            action, reason = "trim", "above target weight"
        else:
            action, reason = "hold", "within target band"
        actions.append(
            PortfolioAction(
                symbol=sym,
                action=action,
                current_cad=current_cad,
                target_cad=h.target_cad,
                delta_cad=delta,
                reason=reason,
            )
        )

    order = {"sell": 0, "buy": 1, "add": 2, "trim": 3, "hold": 4}
    actions.sort(key=lambda a: (order.get(a.action, 9), -abs(a.delta_cad)))
    return actions
