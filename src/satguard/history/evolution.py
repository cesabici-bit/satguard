"""Pc evolution trend analysis.

Analyzes how collision probability changes over time for a conjunction pair.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from satguard.history.store import ConjunctionHistory


class TrendDirection(Enum):
    RISING = "RISING"
    FALLING = "FALLING"
    STABLE = "STABLE"


@dataclass(frozen=True, slots=True)
class PcTrend:
    """Trend analysis of Pc evolution."""

    direction: TrendDirection
    delta_pc: float
    """latest_pc - earliest_pc."""

    latest_pc: float
    snapshots_count: int


def pc_trend(history: ConjunctionHistory) -> PcTrend:
    """Compute the Pc trend from a conjunction history.

    Uses the Foster Pc values from the snapshots (sorted by timestamp).
    Direction is determined by comparing the last and first snapshot:
      - |delta| < 10% of max(first, last, 1e-15) → STABLE
      - delta > 0 → RISING
      - delta < 0 → FALLING

    Args:
        history: ConjunctionHistory with at least 1 snapshot.

    Returns:
        PcTrend with direction, delta, latest value, and count.
    """
    snaps = history.snapshots
    assert len(snaps) >= 1, "Need at least 1 snapshot for trend analysis"

    if len(snaps) == 1:
        return PcTrend(
            direction=TrendDirection.STABLE,
            delta_pc=0.0,
            latest_pc=snaps[0].pc_foster,
            snapshots_count=1,
        )

    first_pc = snaps[0].pc_foster
    last_pc = snaps[-1].pc_foster
    delta = last_pc - first_pc

    # Relative change threshold: 10%
    reference = max(abs(first_pc), abs(last_pc), 1e-15)
    if abs(delta) / reference < 0.10:
        direction = TrendDirection.STABLE
    elif delta > 0:
        direction = TrendDirection.RISING
    else:
        direction = TrendDirection.FALLING

    return PcTrend(
        direction=direction,
        delta_pc=delta,
        latest_pc=last_pc,
        snapshots_count=len(snaps),
    )


def time_to_threshold(
    history: ConjunctionHistory,
    threshold: float,
) -> timedelta | None:
    """Estimate time until Pc reaches the threshold via linear extrapolation.

    Uses the last two snapshots to extrapolate. Returns None if:
    - Less than 2 snapshots
    - Trend is falling or stable
    - Latest Pc already exceeds threshold
    - Slope is zero or negative

    Args:
        history: ConjunctionHistory with snapshots.
        threshold: Pc threshold to project toward.

    Returns:
        Estimated timedelta until threshold, or None.
    """
    snaps = history.snapshots
    if len(snaps) < 2:
        return None

    last = snaps[-1]
    prev = snaps[-2]

    if last.pc_foster >= threshold:
        return None  # Already exceeded

    dt_seconds = (last.timestamp - prev.timestamp).total_seconds()
    if dt_seconds <= 0:
        return None

    slope = (last.pc_foster - prev.pc_foster) / dt_seconds
    if slope <= 0:
        return None  # Falling or flat

    remaining = threshold - last.pc_foster
    seconds_to_threshold = remaining / slope
    return timedelta(seconds=seconds_to_threshold)
