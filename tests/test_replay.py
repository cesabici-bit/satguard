"""Tests for historical replay module (v0.6).

L1: Unit tests for replay mechanics.
L2: Domain sanity — replayed values should match stored values (within tolerance).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from satguard.history.replay import ReplayResult, replay_conjunction
from satguard.history.store import ConjunctionHistory, HistoryStore, PcSnapshot

# ISS TLE (epoch 2024 — used for testing, not current)
# SOURCE: CelesTrak ISS TLE archive (checksums corrected)
ISS_LINE1 = "1 25544U 98067A   24045.54896898  .00016717  00000+0  10270-3 0  9020"
ISS_LINE2 = "2 25544  51.6400 208.3894 0004478  98.1262 261.9912 15.49571089 13602"

# Synthetic secondary (NORAD 41335, epoch close to ISS for test, valid checksums)
DEB_LINE1 = "1 41335U 10057B   24045.48789750  .00001430  00000+0  32457-4 0  9994"
DEB_LINE2 = "2 41335  35.0087 128.3456 0045678 260.1234  99.5678 15.12345678 12344"


def _make_snapshot_with_tles(
    hours_offset: float = 0.0,
    pc: float = 1e-5,
    miss_km: float = 5.0,
) -> PcSnapshot:
    """Create a PcSnapshot with TLE lines archived."""
    base = datetime(2024, 2, 14, 12, 0, 0, tzinfo=UTC)
    # TCA a few hours after base — within TLE validity
    tca = datetime(2024, 2, 14, 18, 0, 0, tzinfo=UTC)
    return PcSnapshot(
        timestamp=base + timedelta(hours=hours_offset),
        tca=tca,
        miss_distance_km=miss_km,
        pc_foster=pc,
        pc_chan=None,
        tle_epoch_primary=base,
        tle_epoch_secondary=base,
        covariance_source="default_LEO",
        tle_line1_primary=ISS_LINE1,
        tle_line2_primary=ISS_LINE2,
        tle_line1_secondary=DEB_LINE1,
        tle_line2_secondary=DEB_LINE2,
    )


def _make_snapshot_without_tles(
    hours_offset: float = 0.0,
    pc: float = 1e-5,
    miss_km: float = 5.0,
) -> PcSnapshot:
    """Create a PcSnapshot WITHOUT TLE lines (old format)."""
    base = datetime(2024, 2, 14, 12, 0, 0, tzinfo=UTC)
    tca = datetime(2024, 2, 14, 18, 0, 0, tzinfo=UTC)
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


class TestReplayConjunction:
    """L1: Replay mechanics."""

    def test_replay_with_tles(self) -> None:
        """Replay with TLE-equipped snapshots produces timeline."""
        snaps = (
            _make_snapshot_with_tles(hours_offset=0.0, miss_km=5.0, pc=1e-5),
            _make_snapshot_with_tles(hours_offset=6.0, miss_km=4.0, pc=5e-5),
        )
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snaps[0].tca,
            snapshots=snaps,
        )
        result = replay_conjunction(history)

        assert isinstance(result, ReplayResult)
        assert result.norad_a == 25544
        assert result.norad_b == 41335
        assert len(result.timeline) == 2
        # All replay points should have computed values
        for pt in result.timeline:
            assert pt.miss_km > 0
            assert 0 <= pt.pc <= 1
            assert pt.tle_age_primary_h >= 0
            assert pt.tle_age_secondary_h >= 0

    def test_replay_without_tles_skips(self) -> None:
        """Snapshots without TLE lines are skipped."""
        snaps = (
            _make_snapshot_without_tles(hours_offset=0.0),
            _make_snapshot_without_tles(hours_offset=6.0),
        )
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snaps[0].tca,
            snapshots=snaps,
        )
        result = replay_conjunction(history)
        assert len(result.timeline) == 0
        assert result.peak_pc == 0.0
        assert result.final_pc == 0.0

    def test_replay_mixed_snapshots(self) -> None:
        """Mix of TLE-equipped and old snapshots: only TLE ones replayed."""
        snaps = (
            _make_snapshot_without_tles(hours_offset=0.0),
            _make_snapshot_with_tles(hours_offset=6.0),
        )
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snaps[0].tca,
            snapshots=snaps,
        )
        result = replay_conjunction(history)
        assert len(result.timeline) == 1

    def test_replay_preserves_stored_values(self) -> None:
        """Replay points should include the originally stored values for comparison."""
        snap = _make_snapshot_with_tles(miss_km=5.123, pc=2.5e-5)
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snap.tca,
            snapshots=(snap,),
        )
        result = replay_conjunction(history)
        assert len(result.timeline) == 1
        pt = result.timeline[0]
        assert pt.stored_miss_km == pytest.approx(5.123)
        assert pt.stored_pc == pytest.approx(2.5e-5)

    def test_peak_and_final_pc(self) -> None:
        """peak_pc and final_pc should be correct."""
        snaps = (
            _make_snapshot_with_tles(hours_offset=0.0, miss_km=5.0, pc=1e-5),
            _make_snapshot_with_tles(hours_offset=6.0, miss_km=3.0, pc=1e-4),
        )
        history = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=snaps[0].tca,
            snapshots=snaps,
        )
        result = replay_conjunction(history)
        assert len(result.timeline) == 2
        assert result.peak_pc == max(pt.pc for pt in result.timeline)
        assert result.final_pc == result.timeline[-1].pc


class TestPcSnapshotBackwardCompat:
    """L1: PcSnapshot backward compatibility (S0)."""

    def test_old_json_loads_without_tle_fields(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Old JSON files without TLE fields should still load correctly."""
        import json

        store = HistoryStore(base_dir=tmp_path)
        # Write old-format JSON manually
        old_data = {
            "norad_id_a": 25544,
            "norad_id_b": 41335,
            "tca_window_center": "2024-02-14T18:00:00Z",
            "snapshots": [{
                "timestamp": "2024-02-14T12:00:00Z",
                "tca": "2024-02-14T18:00:00Z",
                "miss_distance_km": 5.0,
                "pc_foster": 1e-5,
                "pc_chan": None,
                "tle_epoch_primary": "2024-02-14T12:00:00Z",
                "tle_epoch_secondary": "2024-02-14T12:00:00Z",
                "covariance_source": "default_LEO",
                # NOTE: no tle_line* fields — old format
            }],
        }
        fpath = tmp_path / "25544_41335_20240214.json"
        fpath.write_text(json.dumps(old_data, indent=2), encoding="utf-8")

        # Should load without error
        history = store.load(
            25544, 41335,
            datetime(2024, 2, 14, tzinfo=UTC),
        )
        assert history is not None
        assert len(history.snapshots) == 1
        snap = history.snapshots[0]
        assert snap.tle_line1_primary is None
        assert snap.tle_line2_primary is None
        assert snap.tle_line1_secondary is None
        assert snap.tle_line2_secondary is None

    def test_new_json_round_trip_with_tles(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """New snapshots with TLE lines should round-trip through JSON."""
        store = HistoryStore(base_dir=tmp_path)
        snap = _make_snapshot_with_tles()
        store.record(snap, norad_primary=25544, norad_secondary=41335)

        history = store.load(25544, 41335, snap.tca)
        assert history is not None
        loaded = history.snapshots[0]
        assert loaded.tle_line1_primary == ISS_LINE1
        assert loaded.tle_line2_primary == ISS_LINE2
        assert loaded.tle_line1_secondary == DEB_LINE1
        assert loaded.tle_line2_secondary == DEB_LINE2
