"""Smoke test for SatGuard v0.2 — full pipeline with history + alerts.

M3: End-to-end test exercising:
  screen → record history → re-screen with different data → check evolution → alert logic
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from satguard.alert.rules import AlertConfig, should_alert
from satguard.assess.foster import foster_pc
from satguard.covariance.realism import (
    assess_covariance,
    default_covariance,
    project_to_encounter_plane,
)
from satguard.history.evolution import TrendDirection, pc_trend, time_to_threshold
from satguard.history.store import ConjunctionHistory, HistoryStore, PcSnapshot
from satguard.screen.screener import ConjunctionEvent


def _make_event(miss_km: float = 5.0) -> ConjunctionEvent:
    tca = datetime(2026, 3, 20, 8, 0, 0, tzinfo=UTC)
    return ConjunctionEvent(
        tca=tca,
        miss_distance_km=miss_km,
        r_primary=np.array([7000.0, 0.0, 0.0]),
        v_primary=np.array([0.0, 7.5, 0.0]),
        r_secondary=np.array([7000.0 + miss_km, 0.0, 0.0]),
        v_secondary=np.array([0.0, -7.5, 0.0]),
        norad_id_primary=25544,
        norad_id_secondary=41335,
        relative_velocity_km_s=15.0,
    )


class TestSmokeV02:
    """M3: Full v0.2 pipeline smoke test."""

    def test_full_pipeline(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Screen → record → re-assess → check evolution → alert trigger."""
        store = HistoryStore(base_dir=tmp_path)
        base_time = datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC)

        # --- Phase 1: First screening (Pc low) ---
        event1 = _make_event(miss_km=10.0)
        cov = default_covariance("LEO")
        cov_2d = project_to_encounter_plane(
            cov, cov,
            event1.r_primary, event1.v_primary,
            event1.r_secondary, event1.v_secondary,
        )
        pc1 = foster_pc(event1.miss_distance_km, cov_2d, hard_body_radius=0.02)

        snap1 = PcSnapshot(
            timestamp=base_time,
            tca=event1.tca,
            miss_distance_km=event1.miss_distance_km,
            pc_foster=pc1,
            pc_chan=None,
            tle_epoch_primary=base_time,
            tle_epoch_secondary=base_time,
            covariance_source="default_LEO",
        )
        store.record(snap1, 25544, 41335)

        # --- Phase 2: Second screening 6h later (Pc rising) ---
        event2 = _make_event(miss_km=1.0)  # Much closer now
        cov_2d_2 = project_to_encounter_plane(
            cov, cov,
            event2.r_primary, event2.v_primary,
            event2.r_secondary, event2.v_secondary,
        )
        pc2 = foster_pc(event2.miss_distance_km, cov_2d_2, hard_body_radius=0.02)

        snap2 = PcSnapshot(
            timestamp=base_time + timedelta(hours=6),
            tca=event2.tca,
            miss_distance_km=event2.miss_distance_km,
            pc_foster=pc2,
            pc_chan=None,
            tle_epoch_primary=base_time + timedelta(hours=6),
            tle_epoch_secondary=base_time + timedelta(hours=6),
            covariance_source="default_LEO",
        )
        store.record(snap2, 25544, 41335)

        # --- Phase 3: Load history and check evolution ---
        history = store.load(25544, 41335, event1.tca)
        assert history is not None
        assert len(history.snapshots) == 2

        trend = pc_trend(history)
        assert trend.snapshots_count == 2
        assert trend.latest_pc == pytest.approx(pc2)
        # Closer miss → higher Pc → RISING
        assert pc2 > pc1
        assert trend.direction == TrendDirection.RISING

        # --- Phase 4: Covariance assessment ---
        assessment = assess_covariance(cov)
        assert assessment.realism_flag == "DEFAULT"
        assert assessment.is_positive_definite

        # --- Phase 5: Alert logic ---
        # Set threshold between pc1 and pc2 so that:
        # - snap1 (pc1) is BELOW threshold
        # - snap2 (pc2) is ABOVE threshold → should trigger alert
        threshold = (pc1 + pc2) / 2
        assert pc1 < threshold < pc2, f"pc1={pc1}, threshold={threshold}, pc2={pc2}"

        config = AlertConfig(
            webhook_url="https://hooks.example.com/test",
            pc_threshold=threshold,
            notify_on_new=True,
            notify_on_rise=True,
            cooldown_minutes=60,
        )

        # History has snap1 (below threshold) as latest → new pc2 above → alert
        history_before_snap2 = ConjunctionHistory(
            norad_id_a=25544, norad_id_b=41335,
            tca_window_center=event1.tca,
            snapshots=(snap1,),
        )
        assert should_alert(config, history_before_snap2, new_pc=pc2) is True

        # After recording snap2 (above threshold), re-alerting should NOT fire
        assert should_alert(config, history, new_pc=pc2 * 1.1) is False

    def test_time_to_threshold_integration(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Verify time_to_threshold with realistic Pc progression."""
        store = HistoryStore(base_dir=tmp_path)
        base_time = datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC)
        tca = datetime(2026, 3, 20, 8, 0, 0, tzinfo=UTC)

        # Two snapshots: Pc doubling every 6 hours
        for i, pc in enumerate([1e-6, 2e-6]):
            snap = PcSnapshot(
                timestamp=base_time + timedelta(hours=6 * i),
                tca=tca,
                miss_distance_km=10.0 - i,
                pc_foster=pc,
                pc_chan=None,
                tle_epoch_primary=base_time + timedelta(hours=6 * i),
                tle_epoch_secondary=base_time + timedelta(hours=6 * i),
                covariance_source="default_LEO",
            )
            store.record(snap, 25544, 41335)

        history = store.load(25544, 41335, tca)
        assert history is not None

        result = time_to_threshold(history, threshold=1e-4)
        assert result is not None
        # Slope: 1e-6 per 6h. Need 9.8e-5 more. Time = 9.8e-5 / (1e-6/6h) = 588h
        expected_hours = (1e-4 - 2e-6) / (1e-6 / 6)
        assert result.total_seconds() / 3600 == pytest.approx(expected_hours, rel=0.01)
