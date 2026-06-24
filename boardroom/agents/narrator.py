"""The division narrator — authors the two prose fields of a pitch.

It receives the COMPUTED evidence and writes ``opportunity`` and ``why_now``. It
may NOT touch a number: this function returns a copy of the pitch with only the
two narrative strings replaced. That invariant is the whole point of §5.
"""

from __future__ import annotations

from boardroom.agents.llm import LLM
from boardroom.schemas import Pitch

_SYSTEM = (
    "You are a division analyst in an autonomous capital-allocation system. You "
    "are given COMPUTED, real numbers (expected return, win probability, risk, "
    "the features behind them). Write a crisp two-part pitch: (1) the opportunity "
    "and the exact action, (2) why now — the catalyst, grounded ONLY in the "
    "numbers given. You MUST NOT invent or restate any quantitative value as if "
    "you derived it. Prose only, no new numbers. Be concrete and skeptical."
)


def _fallback(pitch: Pitch) -> tuple[str, str]:
    f = pitch.signals.features
    feat = ", ".join(f"{k}={v:.4f}" for k, v in list(f.items())[:4])
    opp = (
        f"{pitch.division.value.title()} on {pitch.symbol} via {pitch.venue.value}: "
        f"model {pitch.signals.model_name}:{pitch.signals.model_version} computes "
        f"expected_return={pitch.expected_return:.4f} at win_prob={pitch.confidence:.2f}, "
        f"horizon {pitch.time_horizon_days:.0f}d, size {pitch.capital_required:.2f} CAD, "
        f"max_loss {pitch.max_loss:.2f} CAD."
    )
    why = f"Triggering features: {feat}." if feat else "Computed signals crossed the model threshold."
    return opp, why


def narrate_pitch(pitch: Pitch, llm: LLM | None = None) -> Pitch:
    """Return a copy of ``pitch`` with narrative fields filled. Numbers untouched."""
    llm = llm or LLM()
    user = (
        f"Division: {pitch.division.value}\nSymbol: {pitch.symbol}\nVenue: {pitch.venue.value}\n"
        f"expected_return: {pitch.expected_return}\nwin_probability: {pitch.confidence}\n"
        f"time_horizon_days: {pitch.time_horizon_days}\ncapital_required_cad: {pitch.capital_required}\n"
        f"max_loss_cad: {pitch.max_loss}\nexpected_cost_cad: {pitch.expected_cost}\n"
        f"model: {pitch.signals.model_name}:{pitch.signals.model_version}\n"
        f"features: {pitch.signals.features}\n\n"
        "Write:\nOPPORTUNITY: <one or two sentences>\nWHY_NOW: <one sentence>"
    )
    text = llm.complete(system=_SYSTEM, user=user, max_tokens=400)
    if not text:
        opp, why = _fallback(pitch)
    else:
        opp, why = _parse(text, pitch)
    return pitch.model_copy(update={"opportunity": opp, "why_now": why})


def _parse(text: str, pitch: Pitch) -> tuple[str, str]:
    opp, why = "", ""
    for line in text.splitlines():
        low = line.lower()
        if low.startswith("opportunity:"):
            opp = line.split(":", 1)[1].strip()
        elif low.startswith("why_now:") or low.startswith("why now:"):
            why = line.split(":", 1)[1].strip()
    if not opp or not why:
        fb_opp, fb_why = _fallback(pitch)
        opp = opp or fb_opp
        why = why or fb_why
    return opp, why
