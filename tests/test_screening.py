"""Tests for conjunction screening.

Oracle L2: CelesTrak SOCRATES — conjunction events for known objects.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from satguard.propagate.sgp4 import StateVector
from satguard.screen.screener import screen


def _make_state(
    t: datetime,
    pos: list[float],
    vel: list[float],
    norad_id: int = 1,
) -> StateVector:
    return StateVector(
        epoch=t,
        position_km=np.array(pos, dtype=np.float64),
        velocity_km_s=np.array(vel, dtype=np.float64),
        norad_id=norad_id,
    )


class TestScreening:
    """L1: Screening logic tests."""

    def test_close_objects_detected(self) -> None:
        """Two objects passing within threshold should produce a conjunction."""
        t0 = datetime(2024, 1, 1, tzinfo=UTC)
        primary = [
            _make_state(
                t0 + timedelta(seconds=i * 60),
                [7000.0 + i * 0.1, 0.0, 0.0], [7.5, 0.0, 0.0], norad_id=1,
            )
            for i in range(100)
        ]
        secondary = [
            _make_state(
                t0 + timedelta(seconds=i * 60),
                [7005.0, (i - 50) * 0.2, 0.0], [0.0, 7.5, 0.0], norad_id=2,
            )
            for i in range(100)
        ]
        events = screen(primary, secondary, threshold_km=20.0)
        assert len(events) > 0
        assert events[0].miss_distance_km < 20.0

    def test_far_objects_no_conjunction(self) -> None:
        """Objects far apart should produce no conjunctions."""
        t0 = datetime(2024, 1, 1, tzinfo=UTC)
        primary = [
            _make_state(
                t0 + timedelta(seconds=i * 60),
                [7000.0, 0.0, 0.0], [7.5, 0.0, 0.0], norad_id=1,
            )
            for i in range(50)
        ]
        secondary = [
            _make_state(
                t0 + timedelta(seconds=i * 60),
                [42000.0, 0.0, 0.0], [3.0, 0.0, 0.0], norad_id=2,
            )
            for i in range(50)
        ]
        events = screen(primary, secondary, threshold_km=50.0)
        assert len(events) == 0

    def test_empty_states(self) -> None:
        events = screen([], [], threshold_km=50.0)
        assert len(events) == 0

    def test_conjunction_event_fields(self) -> None:
        """# SOURCE: CelesTrak SOCRATES format — events have TCA, miss distance."""
        t0 = datetime(2024, 1, 1, tzinfo=UTC)
        primary = [_make_state(t0, [7000.0, 0.0, 0.0], [0.0, 7.5, 0.0], norad_id=100)]
        secondary = [
            _make_state(t0, [7001.0, 0.0, 0.0], [0.0, -7.5, 0.0], norad_id=200)
        ]
        events = screen(primary, secondary, threshold_km=5.0)
        assert len(events) == 1
        event = events[0]
        assert event.norad_id_primary == 100
        assert event.norad_id_secondary == 200
        assert event.miss_distance_km == pytest.approx(1.0, abs=0.1)
        assert event.relative_velocity_km_s == pytest.approx(15.0, abs=0.1)

    def test_events_sorted_by_distance(self) -> None:
        """Events should be sorted by miss distance ascending."""
        t0 = datetime(2024, 1, 1, tzinfo=UTC)
        primary = [
            _make_state(
                t0 + timedelta(minutes=i),
                [7000.0 + i * 100, 0.0, 0.0], [7.5, 0.0, 0.0],
            )
            for i in range(200)
        ]
        secondary = [
            _make_state(
                t0 + timedelta(minutes=i),
                [7003.0 + i * 100, 5.0, 0.0], [7.5, 0.0, 0.0],
            )
            for i in range(200)
        ]
        events = screen(primary, secondary, threshold_km=10.0)
        for i in range(1, len(events)):
            assert events[i].miss_distance_km >= events[i - 1].miss_distance_km
