"""Critic: the answer to question (B) — *was each decision sound?*

Decision quality is judged independently of P&L. A good process can lose money
(unlucky) and a bad process can make it (lucky); the Critic refuses to confuse
the two. It scores calibration (did stated confidence match reality?), Brier
accuracy, how often outcomes landed inside the predicted band, and tags every
decision on the process/luck 2x2.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from boardroom.schemas import ProcessLuckTag, ResolvedOutcome


def tag_process_luck(*, good_process: bool, win: bool) -> ProcessLuckTag:
    """Place a decision on the process/luck 2x2 (scope §8)."""
    if good_process and win:
        return ProcessLuckTag.GOOD_PROCESS_GOOD_OUTCOME
    if good_process and not win:
        return ProcessLuckTag.GOOD_PROCESS_BAD_OUTCOME  # unlucky — don't punish
    if not good_process and win:
        return ProcessLuckTag.BAD_PROCESS_GOOD_OUTCOME  # lucky — don't reward
    return ProcessLuckTag.BAD_PROCESS_BAD_OUTCOME


def calibration_error(
    predicted_confidences: list[float],
    wins: list[bool],
    n_bins: int = 5,
) -> float:
    """Expected Calibration Error (ECE).

    Bin predictions into ``n_bins`` equal-width buckets over [0, 1]. For each
    non-empty bin compute the gap between the mean predicted confidence and the
    empirical win-rate, weight by the bin's share of the data, and sum. Lower is
    better; 0 means perfectly calibrated. Returns 0.0 on empty input.
    """
    if not predicted_confidences:
        return 0.0
    if len(predicted_confidences) != len(wins):
        raise ValueError("predicted_confidences and wins must be the same length")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")

    n = len(predicted_confidences)
    bin_conf_sums = [0.0] * n_bins
    bin_win_sums = [0.0] * n_bins
    bin_counts = [0] * n_bins

    for p, w in zip(predicted_confidences, wins):
        # Clamp into [0, 1] then bucket; the top edge (1.0) lands in the last bin.
        pc = min(max(p, 0.0), 1.0)
        idx = int(pc * n_bins)
        if idx == n_bins:
            idx = n_bins - 1
        bin_conf_sums[idx] += pc
        bin_win_sums[idx] += 1.0 if w else 0.0
        bin_counts[idx] += 1

    ece = 0.0
    for i in range(n_bins):
        count = bin_counts[i]
        if count == 0:
            continue
        mean_conf = bin_conf_sums[i] / count
        win_rate = bin_win_sums[i] / count
        ece += (count / n) * abs(mean_conf - win_rate)
    return ece


def brier_score(predicted_confidences: list[float], wins: list[bool]) -> float:
    """Mean squared error between predicted confidence and 0/1 outcome.

    0.0 is perfect, 1.0 is maximally wrong. Returns 0.0 on empty input.
    """
    if not predicted_confidences:
        return 0.0
    if len(predicted_confidences) != len(wins):
        raise ValueError("predicted_confidences and wins must be the same length")
    total = 0.0
    for p, w in zip(predicted_confidences, wins):
        outcome = 1.0 if w else 0.0
        total += (p - outcome) ** 2
    return total / len(predicted_confidences)


@dataclass
class CriticReport:
    """The Critic's deterministic decision-quality summary."""

    n_resolved: int
    calibration_error: float
    brier_score: float
    inside_band_rate: float
    process_luck_counts: dict[str, int]

    def summary_lines(self) -> list[str]:
        lines = [
            f"Critiqued {self.n_resolved} resolved decision(s).",
            f"Calibration error (ECE): {self.calibration_error:.3f}.",
            f"Brier score: {self.brier_score:.3f}.",
            f"Inside-band rate: {self.inside_band_rate * 100:.1f}%.",
        ]
        for tag, count in sorted(self.process_luck_counts.items()):
            lines.append(f"  {tag}: {count}")
        return lines


def critique(outcomes: list[ResolvedOutcome]) -> CriticReport:
    """Build a :class:`CriticReport` from resolved outcomes."""
    n = len(outcomes)
    confidences = [o.predicted_confidence for o in outcomes]
    wins = [o.win for o in outcomes]

    ece = calibration_error(confidences, wins)
    brier = brier_score(confidences, wins)
    inside_band_rate = (
        sum(1 for o in outcomes if o.inside_band) / n if n else 0.0
    )

    counts: Counter[str] = Counter()
    for o in outcomes:
        if o.process_luck is not None:
            counts[o.process_luck.value] += 1

    return CriticReport(
        n_resolved=n,
        calibration_error=ece,
        brier_score=brier,
        inside_band_rate=inside_band_rate,
        process_luck_counts=dict(counts),
    )
