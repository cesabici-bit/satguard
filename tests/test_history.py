"""Tests for Pc history store and evolution analysis (v0.2).

L1: Round-trip persistence, deduplication, trend detection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from satguard.history.evolution import TrendDirection, pc_trend, time_to_threshold
from satguard.history.store import ConjunctionHistory, HistoryStore, PcSnapshot


def _make_snapshot(
    hours_offset: float = 0.0,
    pc: float = 1e-5,
    miss_km: float = 5.0,
) -> PcSnapshot:
    """Helper to create a PcSnapshot with offsets from a base time."""
    base = datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC)
    tca = datetime(2026, 3, 20, 8, 0, 0, tzinfo=UTC)
    return PcSnapshot(
        timestamp=base + timedelta(hours=hours_offset),
        tca=tca,
        miss_distance_km=miss_km,
        pc_foster=pc,
        pc_chan=None,
        tle_epoch_primary=base,
        tle_epoch_secondary=base,
        covariance_source="default_LEO",
    )


class TestHistoryStore:
    """L1: JSON persistence round-trip tests."""

    def test_record_and_load(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        store = HistoryStore(base_dir=tmp_path)
        snap = _make_snapshot()
        store.record(snap, norad_primary=25544, norad_secondary=41335)

        history = store.load(25544, 41335, snap.tca)
        assert history is not None
        assert len(history.snapshots) == 1
        assert history.norad_id_a == 25544
        assert history.norad_id_b == 41335

    def test_round_trip_preserves_fields(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        store = HistoryStore(base_dir=tmp_path)
        snap = _make_snapshot(pc=3.14e-6, miss_km=12.5)
        store.record(snap, norad_primary=99999, norad_secondary=11111)

        history = store.load(11111, 99999, snap.tca)
        assert history is not None
        loaded = history.snapshots[0]
        assert loaded.pc_foster == pytest.approx(3.14e-6)
        assert loaded.miss_distance_km == pytest.approx(12.5)
        assert loaded.covariance_source == "default_LEO"
        assert loaded.pc_chan is None

    def test_norad_ids_are_sorted(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """min(a,b) is always norad_id_a regardless of record order."""
        store = HistoryStore(base_dir=tmp_path)
        snap = _make_snapshot()
        store.record(snap, norad_primary=50000, norad_secondary=10000)

        history = store.load(50000, 10000, snap.tca)
        assert history is not None
        assert history.norad_id_a == 10000
        assert history.norad_id_b == 50000

    def test_duplicate_timestamp_ignored(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        store = HistoryStore(base_dir=tmp_path)
        snap = _make_snapshot()
        store.record(snap, 25544, 41335)
        store.record(snap, 25544, 41335)  # Same timestamp

        history = store.load(25544, 41335, snap.tca)
        assert history is not None
        assert len(history.snapshots) == 1

    def test_multiple_snapshots_sorted(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        store = HistoryStore(base_dir=tmp_path)
        snap1 = _make_snapshot(hours_offset=0.0, pc=1e-6)
        snap2 = _make_snapshot(hours_offset=6.0, pc=5e-6)
        snap3 = _make_snapshot(hours_offset=3.0, pc=3e-6)

        store.record(snap1, 25544, 41335)
        store.record(snap3, 25544, 41335)  # Out of order
        store.record(snap2, 25544, 41335)

        history = store.load(25544, 41335, snap1.tca)
        assert history is not None
        assert len(history.snapshots) == 3
        # Should be sorted by timestamp
        pcs = [s.pc_foster for s in history.snapshots]
        assert pcs == [pytest.approx(1e-6), pytest.approx(3e-6), pytest.approx(5e-6)]

    def test_list_conjunctions(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        store = HistoryStore(base_dir=tmp_path)
        snap = _make_snapshot()
        store.record(snap, 25544, 41335)
        store.record(snap, 11111, 22222)

        conjs = store.list_conjunctions()
        assert len(conjs) == 2

    def test_load_nonexistent_returns_none(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        store = HistoryStore(base_dir=tmp_path)
        result = store.load(99999, 88888, datetime(2026, 1, 1, tzinfo=UTC))
        assert result is None

    def test_empty_dir_list_empty(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        store = HistoryStore(base_dir=tmp_path / "nonexistent")
        assert store.list_conjunctions() == []


class TestPcTrend:
    """L1: Trend detection on synthetic data."""

    def test_single_snapshot_stable(self) -> None:
        snap = _make_snapshot(pc=1e-5)
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snap.tca,
            snapshots=(snap,),
        )
        trend = pc_trend(history)
        assert trend.direction == TrendDirection.STABLE
        assert trend.snapshots_count == 1

    def test_rising_trend(self) -> None:
        snaps = (
            _make_snapshot(hours_offset=0, pc=1e-6),
            _make_snapshot(hours_offset=6, pc=5e-6),
            _make_snapshot(hours_offset=12, pc=1e-5),
        )
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snaps[0].tca,
            snapshots=snaps,
        )
        trend = pc_trend(history)
        assert trend.direction == TrendDirection.RISING
        assert trend.delta_pc > 0

    def test_falling_trend(self) -> None:
        snaps = (
            _make_snapshot(hours_offset=0, pc=1e-4),
            _make_snapshot(hours_offset=6, pc=5e-5),
            _make_snapshot(hours_offset=12, pc=1e-6),
        )
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snaps[0].tca,
            snapshots=snaps,
        )
        trend = pc_trend(history)
        assert trend.direction == TrendDirection.FALLING
        assert trend.delta_pc < 0

    def test_stable_small_change(self) -> None:
        """<10% relative change → STABLE."""
        snaps = (
            _make_snapshot(hours_offset=0, pc=1.00e-5),
            _make_snapshot(hours_offset=6, pc=1.05e-5),  # 5% change
        )
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snaps[0].tca,
            snapshots=snaps,
        )
        trend = pc_trend(history)
        assert trend.direction == TrendDirection.STABLE


class TestTimeToThreshold:
    """L1: time_to_threshold extrapolation."""

    def test_linear_extrapolation(self) -> None:
        """Two snapshots 6h apart, Pc doubled. Should estimate threshold crossing."""
        snaps = (
            _make_snapshot(hours_offset=0, pc=1e-5),
            _make_snapshot(hours_offset=6, pc=2e-5),
        )
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snaps[0].tca,
            snapshots=snaps,
        )
        result = time_to_threshold(history, threshold=1e-4)
        assert result is not None
        # Slope: 1e-5 / 6h. Need 8e-5 more. Time = 8e-5 / (1e-5/6h) = 48h
        expected_hours = 48.0
        assert result.total_seconds() / 3600 == pytest.approx(expected_hours, rel=0.01)

    def test_already_exceeded_returns_none(self) -> None:
        snaps = (
            _make_snapshot(hours_offset=0, pc=5e-4),
            _make_snapshot(hours_offset=6, pc=1e-3),
        )
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snaps[0].tca,
            snapshots=snaps,
        )
        assert time_to_threshold(history, threshold=1e-4) is None

    def test_falling_returns_none(self) -> None:
        snaps = (
            _make_snapshot(hours_offset=0, pc=1e-4),
            _make_snapshot(hours_offset=6, pc=5e-5),
        )
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snaps[0].tca,
            snapshots=snaps,
        )
        assert time_to_threshold(history, threshold=1e-3) is None

    def test_single_snapshot_returns_none(self) -> None:
        snap = _make_snapshot(pc=1e-5)
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snap.tca,
            snapshots=(snap,),
        )
        assert time_to_threshold(history, threshold=1e-4) is None
