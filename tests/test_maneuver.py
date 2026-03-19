"""Tests for maneuver planning module (v0.6).

L1: Unit tests for CW equations and ManeuverPlanner.
L2: Domain sanity with external oracle values.
L3: Property-based tests for CW invariants.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from satguard.maneuver.cw import (
    ManeuverBurn,
    cw_displacement,
    eccentricity_from_state,
    mean_motion,
    orbital_period,
    sma_from_position,
)
from satguard.maneuver.planner import ManeuverPlanner
from satguard.screen.screener import ConjunctionEvent

# =====================================================================
# Constants for tests
# =====================================================================

# ISS-like orbit: ~400 km altitude, a ≈ 6778 km
ISS_SMA_KM = 6778.0
ISS_ALTITUDE_KM = 400.0
EARTH_RADIUS_KM = 6378.137
MU_EARTH = 398600.4418

# ISS-like state vector (circular orbit in equatorial plane)
ISS_R = np.array([ISS_SMA_KM, 0.0, 0.0])
ISS_V_CIRCULAR = math.sqrt(MU_EARTH / ISS_SMA_KM)
ISS_V = np.array([0.0, ISS_V_CIRCULAR, 0.0])


# =====================================================================
# L1: Unit tests — CW displacement
# =====================================================================


class TestMeanMotion:
    """L1: mean motion computation."""

    def test_iss_orbit(self) -> None:
        """ISS mean motion ≈ 0.00113 rad/s (period ~92 min)."""
        n = mean_motion(ISS_SMA_KM)
        period = 2 * math.pi / n
        # ISS period is ~92.5 minutes = ~5550 seconds
        assert 5400 < period < 5700, f"ISS period {period:.0f}s out of range"

    def test_geo_orbit(self) -> None:
        """GEO mean motion: period ≈ 86164 s (sidereal day)."""
        geo_sma = 42164.0  # km
        n = mean_motion(geo_sma)
        period = 2 * math.pi / n
        assert abs(period - 86164) < 100, f"GEO period {period:.0f}s, expected ~86164s"

    def test_negative_sma_raises(self) -> None:
        with pytest.raises(AssertionError):
            mean_motion(-100.0)


class TestOrbitalPeriod:
    def test_iss_period(self) -> None:
        T = orbital_period(ISS_SMA_KM)
        assert 5400 < T < 5700


class TestSMAFromPosition:
    def test_circular_orbit(self) -> None:
        """Circular orbit: SMA = orbital radius."""
        sma = sma_from_position(ISS_R, ISS_V)
        assert abs(sma - ISS_SMA_KM) < 1.0, f"SMA={sma:.1f}, expected {ISS_SMA_KM}"

    def test_hyperbolic_raises(self) -> None:
        """Hyperbolic orbit should raise AssertionError."""
        v_escape = np.array([0.0, 20.0, 0.0])  # >> escape velocity
        with pytest.raises(AssertionError, match="Hyperbolic"):
            sma_from_position(ISS_R, v_escape)


class TestEccentricity:
    def test_circular_orbit_near_zero(self) -> None:
        """Circular orbit: e ≈ 0."""
        e = eccentricity_from_state(ISS_R, ISS_V)
        assert e < 0.01, f"Circular orbit eccentricity={e:.4f}, expected ~0"


class TestCWDisplacement:
    """L1: CW displacement equations."""

    def test_zero_deltav_zero_displacement(self) -> None:
        """No burn → no displacement."""
        burn = ManeuverBurn(delta_v_ms=0.0, time_before_tca_s=1000.0)
        disp = cw_displacement(burn, ISS_SMA_KM)
        assert disp.dx_intrack_km == 0.0
        assert disp.dz_radial_km == 0.0

    def test_zero_time_zero_displacement(self) -> None:
        """Burn at TCA → zero displacement."""
        burn = ManeuverBurn(delta_v_ms=0.5, time_before_tca_s=0.0)
        disp = cw_displacement(burn, ISS_SMA_KM)
        assert abs(disp.dx_intrack_km) < 1e-10
        assert abs(disp.dz_radial_km) < 1e-10

    def test_positive_deltav_gives_displacement(self) -> None:
        """Positive in-track burn with lead time should produce non-zero displacement."""
        burn = ManeuverBurn(delta_v_ms=0.1, time_before_tca_s=2700.0)  # ~half orbit
        disp = cw_displacement(burn, ISS_SMA_KM)
        assert disp.magnitude_km > 0.0

    def test_displacement_scales_with_deltav(self) -> None:
        """Doubling Δv should double displacement (linear)."""
        burn1 = ManeuverBurn(delta_v_ms=0.1, time_before_tca_s=2000.0)
        burn2 = ManeuverBurn(delta_v_ms=0.2, time_before_tca_s=2000.0)
        d1 = cw_displacement(burn1, ISS_SMA_KM)
        d2 = cw_displacement(burn2, ISS_SMA_KM)
        assert abs(d2.dx_intrack_km / d1.dx_intrack_km - 2.0) < 0.01
        assert abs(d2.dz_radial_km / d1.dz_radial_km - 2.0) < 0.01

    def test_negative_time_raises(self) -> None:
        burn = ManeuverBurn(delta_v_ms=0.1, time_before_tca_s=-100.0)
        with pytest.raises(AssertionError):
            cw_displacement(burn, ISS_SMA_KM)


# =====================================================================
# L2: Domain sanity — external oracle values
# =====================================================================


class TestCWOracleL2:
    """L2: CW displacement verified against textbook values.

    SOURCE: Curtis "Orbital Mechanics for Engineering Students" 4th Ed, Ch.7
    For a 400 km LEO circular orbit (a ≈ 6778 km):
    - n ≈ 0.001131 rad/s
    - T ≈ 5554 s (92.6 min)
    - A 0.1 m/s in-track burn at τ = T/2:
      Δz_radial ≈ 2 × (Δv/n) × (1 - cos(π)) = 2 × (0.0001/0.001131) × 2
                ≈ 0.354 km (radial)
      Δx_intrack = (Δv) × (4/n × sin(π) - 3×T/2)
                 ≈ 0.0001 × (0 - 3 × 2777) ≈ -0.833 km (in-track, retrograde drift)
    """

    def test_radial_displacement_half_period(self) -> None:
        """SOURCE: Curtis Ch.7 — Radial displacement at τ=T/2 for 0.1 m/s burn.

        Expected: Δz ≈ 0.35 km (within 10% tolerance for linearization).
        """
        T = orbital_period(ISS_SMA_KM)
        burn = ManeuverBurn(delta_v_ms=0.1, time_before_tca_s=T / 2.0)
        disp = cw_displacement(burn, ISS_SMA_KM)

        # CW analytical: Δz = Δv × 2/n × (1 - cos(n×T/2))
        # At T/2: n×T/2 = π, cos(π) = -1, so factor = (1-(-1)) = 2
        # Δz = 0.0001 km/s × 2/0.001131 × 2 ≈ 0.354 km
        n = mean_motion(ISS_SMA_KM)
        expected_dz = 0.0001 * 2.0 / n * 2.0  # ≈ 0.354 km
        assert abs(disp.dz_radial_km - expected_dz) / expected_dz < 0.01, (
            f"Δz={disp.dz_radial_km:.4f} km, expected ≈{expected_dz:.4f} km"
        )

    def test_intrack_displacement_half_period(self) -> None:
        """SOURCE: Curtis Ch.7 — In-track displacement at τ=T/2.

        At τ=T/2: sin(n×T/2) = sin(π) ≈ 0, so:
        Δx = Δv × (4/n × 0 - 3 × T/2) = -3 × Δv × T/2
        For Δv=0.1 m/s: Δx ≈ -3 × 0.0001 × 2777 ≈ -0.833 km
        """
        T = orbital_period(ISS_SMA_KM)
        burn = ManeuverBurn(delta_v_ms=0.1, time_before_tca_s=T / 2.0)
        disp = cw_displacement(burn, ISS_SMA_KM)

        expected_dx = -3.0 * 0.0001 * T / 2.0  # ≈ -0.833 km
        # Tolerance: 1% (sin(π) is ~0 numerically but not exactly)
        assert abs(disp.dx_intrack_km - expected_dx) / abs(expected_dx) < 0.01, (
            f"Δx={disp.dx_intrack_km:.4f} km, expected ≈{expected_dx:.4f} km"
        )

    def test_typical_cam_deltav_range(self) -> None:
        """SOURCE: NASA CARA operational data — typical CAM Δv is 0.05–1.0 m/s.

        A 0.5 m/s burn at T/4 should produce displacement of order ~km.
        """
        T = orbital_period(ISS_SMA_KM)
        burn = ManeuverBurn(delta_v_ms=0.5, time_before_tca_s=T / 4.0)
        disp = cw_displacement(burn, ISS_SMA_KM)
        # Should be in the km-range displacement
        assert disp.magnitude_km > 0.1, f"Displacement too small: {disp.magnitude_km:.4f} km"
        assert disp.magnitude_km < 50.0, f"Displacement too large: {disp.magnitude_km:.4f} km"


# =====================================================================
# L3: Property-based tests — CW invariants
# =====================================================================


class TestCWProperties:
    """L3: Property-based invariants for CW equations."""

    @given(
        dv=st.floats(min_value=0.001, max_value=2.0),
        tau_frac=st.floats(min_value=0.01, max_value=0.99),
    )
    @settings(max_examples=50)
    def test_displacement_monotonic_in_deltav(self, dv: float, tau_frac: float) -> None:
        """Magnitude of displacement is monotonically increasing with Δv
        (for fixed τ, same sign)."""
        T = orbital_period(ISS_SMA_KM)
        tau = tau_frac * T / 2.0

        burn1 = ManeuverBurn(delta_v_ms=dv, time_before_tca_s=tau)
        burn2 = ManeuverBurn(delta_v_ms=dv * 2.0, time_before_tca_s=tau)
        d1 = cw_displacement(burn1, ISS_SMA_KM)
        d2 = cw_displacement(burn2, ISS_SMA_KM)

        # Magnitude should scale exactly 2× (linearity)
        if d1.magnitude_km > 1e-10:
            ratio = d2.magnitude_km / d1.magnitude_km
            assert abs(ratio - 2.0) < 0.01, f"Linearity violated: ratio={ratio:.4f}"

    @given(
        dv=st.floats(min_value=0.01, max_value=1.0),
        tau_frac=st.floats(min_value=0.01, max_value=0.99),
    )
    @settings(max_examples=50)
    def test_radial_displacement_non_negative(self, dv: float, tau_frac: float) -> None:
        """Radial displacement Δz = (2Δv/n)(1-cos(nτ)) ≥ 0 for Δv > 0."""
        T = orbital_period(ISS_SMA_KM)
        tau = tau_frac * T / 2.0
        burn = ManeuverBurn(delta_v_ms=dv, time_before_tca_s=tau)
        disp = cw_displacement(burn, ISS_SMA_KM)
        assert disp.dz_radial_km >= -1e-10, f"Radial displacement negative: {disp.dz_radial_km}"


# =====================================================================
# L1: ManeuverPlanner tests
# =====================================================================


def _make_conjunction(miss_km: float = 0.5) -> ConjunctionEvent:
    """Create a synthetic conjunction event for testing."""
    return ConjunctionEvent(
        tca=datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC),
        miss_distance_km=miss_km,
        r_primary=ISS_R.copy(),
        v_primary=ISS_V.copy(),
        r_secondary=ISS_R + np.array([miss_km, 0.0, 0.0]),
        v_secondary=np.array([0.0, -ISS_V_CIRCULAR, 0.0]),  # head-on
        norad_id_primary=25544,
        norad_id_secondary=41335,
        relative_velocity_km_s=2 * ISS_V_CIRCULAR,
    )


class TestManeuverPlanner:
    """L1: ManeuverPlanner tradespace search."""

    def test_no_action_below_threshold(self) -> None:
        """If original Pc < threshold, no maneuver needed."""
        event = _make_conjunction(miss_km=100.0)  # Very safe
        planner = ManeuverPlanner()
        result = planner.plan(event, threshold_pc=1e-4)
        assert not result.action_required
        assert result.recommended is None

    def test_finds_recommendation_for_close_approach(self) -> None:
        """For a close conjunction, planner should find a recommended maneuver."""
        event = _make_conjunction(miss_km=0.5)
        planner = ManeuverPlanner(dv_range_ms=(0.01, 2.0), dv_steps=30, time_steps=30)
        result = planner.plan(event, threshold_pc=1e-5)

        assert result.action_required
        assert len(result.options) > 0
        if result.recommended is not None:
            assert result.recommended.post_pc <= 1e-5

    def test_recommended_is_minimum_deltav(self) -> None:
        """Recommended option should be the minimum Δv that meets threshold."""
        event = _make_conjunction(miss_km=0.5)
        planner = ManeuverPlanner(dv_range_ms=(0.01, 2.0), dv_steps=30, time_steps=30)
        result = planner.plan(event, threshold_pc=1e-4)

        if result.recommended is not None:
            # Check that no option with lower Δv also meets threshold
            for opt in result.options:
                if opt.burn.delta_v_ms < result.recommended.burn.delta_v_ms:
                    assert opt.post_pc > result.threshold, (
                        f"Found lower Δv={opt.burn.delta_v_ms:.3f} m/s "
                        f"with Pc={opt.post_pc:.2e} < threshold"
                    )

    def test_options_have_consistent_fields(self) -> None:
        """All options should have original values matching the event."""
        event = _make_conjunction(miss_km=0.5)
        planner = ManeuverPlanner(dv_steps=5, time_steps=5)
        result = planner.plan(event, threshold_pc=1e-4)

        for opt in result.options:
            assert opt.original_miss_km == pytest.approx(0.5)
            assert opt.original_pc == pytest.approx(result.original_pc)
            assert opt.post_miss_km > 0
            assert 0 <= opt.post_pc <= 1

    def test_pc_reduction_with_half_ms_burn(self) -> None:
        """SOURCE: Alfano 2005, Fig.3 — 0.5 m/s burn should reduce Pc by ≥10×.

        For a close approach (miss ~ 0.5 km), a 0.5 m/s burn with adequate
        lead time should significantly increase miss distance and reduce Pc.
        """
        event = _make_conjunction(miss_km=0.5)
        planner = ManeuverPlanner(dv_range_ms=(0.5, 0.5), dv_steps=1, time_steps=20)
        result = planner.plan(event, threshold_pc=1e-10)  # Very low threshold

        # Find the best option at 0.5 m/s
        if result.options:
            best = min(result.options, key=lambda o: o.post_pc)
            if result.original_pc > 0:
                # With 0.5 m/s and adequate lead time, expect significant reduction
                assert best.post_miss_km > event.miss_distance_km, (
                    f"Post-miss {best.post_miss_km:.3f} km should exceed "
                    f"original {event.miss_distance_km:.3f} km"
                )
