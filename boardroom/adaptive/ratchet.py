"""The gains ratchet (scope §9).

Compounding wants you to reinvest everything; survival wants you to protect
gains. The ratchet resolves it: when equity sets a new high-water mark, move a
slice of the gain into an UNTOUCHABLE reserve. The reserve only ever grows;
agents can never claw it back because it is subtracted from the investable base
the caps resolve against. Most of the compounding benefit, ruin structurally
removed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RatchetState:
    reserve_cad: float
    hwm_cad: float


def ratchet_update(
    *,
    equity_cad: float,
    state: RatchetState,
    capture_fraction: float = 0.25,
    min_gain_step: float = 10.0,
) -> RatchetState:
    """Return the new reserve/high-water-mark.

    When equity exceeds the high-water mark by at least ``min_gain_step``, sweep
    ``capture_fraction`` of the gain-above-HWM into the reserve and raise the HWM
    to the new equity. Otherwise just track the peak. The reserve never shrinks.
    """
    if equity_cad > state.hwm_cad + min_gain_step:
        gain = equity_cad - state.hwm_cad
        captured = max(0.0, capture_fraction) * gain
        return RatchetState(
            reserve_cad=round(state.reserve_cad + captured, 2),
            hwm_cad=round(equity_cad, 2),
        )
    # New marginal high but below the step — track the peak, don't sweep yet.
    return RatchetState(
        reserve_cad=state.reserve_cad,
        hwm_cad=round(max(state.hwm_cad, equity_cad), 2),
    )


def investable_cad(equity_cad: float, reserve_cad: float) -> float:
    """The base the caps resolve against — equity minus the protected reserve."""
    return max(0.0, equity_cad - reserve_cad)
