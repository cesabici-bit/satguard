"""Tests for SGP4 propagation wrapper.

Oracle L2: Vallado 5th Ed, Example 11-2 (SGP4 propagation test cases).
"""

from datetime import UTC, datetime

import numpy as np
import pytest

from satguard.catalog.tle import parse_tle
from satguard.propagate.sgp4 import _jd_from_datetime, propagate_batch, propagate_single

# ISS TLE fixture
ISS_TLE = """\
ISS (ZARYA)
1 25544U 98067A   24045.51749023  .00020825  00000+0  37340-3 0  9992
2 25544  51.6416  14.5021 0006703  38.8378  76.2277 15.49560867441079"""


class TestPropagation:
    """L1: Unit tests for propagation."""

    def test_propagate_at_epoch(self) -> None:
        """Propagation at TLE epoch should give position near LEO altitude."""
        tle = parse_tle(ISS_TLE)
        sv = propagate_single(tle, tle.epoch_datetime)
        # ISS is in LEO ~400 km
        r = float(np.linalg.norm(sv.position_km))
        assert 6700 < r < 6900, f"ISS radius {r} km not in LEO range"

    def test_propagate_returns_correct_norad_id(self) -> None:
        tle = parse_tle(ISS_TLE)
        sv = propagate_single(tle, tle.epoch_datetime)
        assert sv.norad_id == 25544

    def test_altitude_property(self) -> None:
        tle = parse_tle(ISS_TLE)
        sv = propagate_single(tle, tle.epoch_datetime)
        assert 350 < sv.altitude_km < 450, f"ISS altitude {sv.altitude_km} km unexpected"

    def test_velocity_magnitude(self) -> None:
        """ISS velocity should be ~7.66 km/s."""
        tle = parse_tle(ISS_TLE)
        sv = propagate_single(tle, tle.epoch_datetime)
        v = float(np.linalg.norm(sv.velocity_km_s))
        assert 7.0 < v < 8.5, f"ISS velocity {v} km/s unexpected"

    def test_propagate_matches_direct_sgp4(self) -> None:
        """L2: Verify wrapper matches direct sgp4 library output.
        # SOURCE: sgp4 library direct call — wrapper must not alter results.
        """
        from sgp4.api import WGS72, Satrec

        tle = parse_tle(ISS_TLE)
        sat = Satrec.twoline2rv(tle.line1, tle.line2, WGS72)

        epoch = tle.epoch_datetime
        jd, fr = _jd_from_datetime(epoch)
        _, pos_direct, vel_direct = sat.sgp4(jd, fr)

        sv = propagate_single(tle, epoch)
        np.testing.assert_allclose(sv.position_km, pos_direct, atol=1e-10)
        np.testing.assert_allclose(sv.velocity_km_s, vel_direct, atol=1e-10)


class TestBatchPropagation:
    """Tests for batch propagation."""

    def test_batch_returns_expected_count(self) -> None:
        tle = parse_tle(ISS_TLE)
        states = propagate_batch(tle, days=1.0, step_seconds=600.0)
        expected = int(1.0 * 86400 / 600) + 1  # 145
        assert len(states) == expected

    def test_batch_states_are_chronological(self) -> None:
        tle = parse_tle(ISS_TLE)
        states = propagate_batch(tle, days=0.5, step_seconds=300.0)
        for i in range(1, len(states)):
            assert states[i].epoch > states[i - 1].epoch

    def test_batch_warns_long_propagation(self) -> None:
        tle = parse_tle(ISS_TLE)
        with pytest.warns(UserWarning, match="degrades"):
            propagate_batch(tle, days=10.0, step_seconds=3600.0)


class TestJulianDate:
    """L2: Julian date conversion verification.
    # SOURCE: US Naval Observatory — J2000.0 epoch is JD 2451545.0 = 2000-01-01T12:00:00 UTC
    """

    def test_j2000_epoch(self) -> None:
        dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=UTC)
        jd, fr = _jd_from_datetime(dt)
        assert jd + fr == pytest.approx(2451545.0, abs=1e-6)

    def test_known_date(self) -> None:
        """2024-02-14T12:00:00 UTC → JD 2460355.0"""
        dt = datetime(2024, 2, 14, 12, 0, 0, tzinfo=UTC)
        jd, fr = _jd_from_datetime(dt)
        assert jd + fr == pytest.approx(2460355.0, abs=1e-4)
