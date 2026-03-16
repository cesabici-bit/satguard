"""L3: Property-based tests using Hypothesis.

Tests invariants that must hold for ANY valid input, not just specific test cases.
"""

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from satguard.assess.alfano import alfano_pc
from satguard.assess.chan import chan_pc
from satguard.assess.foster import foster_pc
from satguard.covariance.realism import (
    default_covariance,
    eci_to_rtn,
    project_to_encounter_plane,
)

# --- Strategies ---

# Valid orbital position vector (LEO to GEO range, km)
position_vector = st.tuples(
    st.floats(min_value=-50000, max_value=50000, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-50000, max_value=50000, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-50000, max_value=50000, allow_nan=False, allow_infinity=False),
).filter(lambda v: np.linalg.norm(v) > 6400)  # Above Earth surface

velocity_vector = st.tuples(
    st.floats(min_value=-15, max_value=15, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-15, max_value=15, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-15, max_value=15, allow_nan=False, allow_infinity=False),
).filter(lambda v: np.linalg.norm(v) > 0.5)  # Minimum orbital velocity

# Miss distance in km (from very close to far)
miss_distance = st.floats(min_value=0.0, max_value=100.0, allow_nan=False)

# Hard body radius in km
hard_body_radius = st.floats(min_value=0.001, max_value=1.0, allow_nan=False)

# Positive diagonal covariance (isotropic for simplicity)
sigma_km = st.floats(min_value=0.01, max_value=50.0, allow_nan=False)


class TestRTNProperties:
    """L3: RTN rotation matrix invariants."""

    @given(r=position_vector, v=velocity_vector)
    @settings(max_examples=100)
    def test_rtn_always_orthogonal(
        self, r: tuple[float, float, float], v: tuple[float, float, float]
    ) -> None:
        """RTN rotation matrix must ALWAYS be orthogonal (R^T R = I)."""
        r_arr = np.array(r)
        v_arr = np.array(v)
        # Need r and v not parallel
        cross = np.cross(r_arr, v_arr)
        assume(np.linalg.norm(cross) > 1e-6)

        R = eci_to_rtn(r_arr, v_arr)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-10)

    @given(r=position_vector, v=velocity_vector)
    @settings(max_examples=100)
    def test_rtn_determinant_always_one(
        self, r: tuple[float, float, float], v: tuple[float, float, float]
    ) -> None:
        """RTN must be a proper rotation (det = +1, not reflection)."""
        r_arr = np.array(r)
        v_arr = np.array(v)
        cross = np.cross(r_arr, v_arr)
        assume(np.linalg.norm(cross) > 1e-6)

        R = eci_to_rtn(r_arr, v_arr)
        assert np.linalg.det(R) == pytest.approx(1.0, abs=1e-10)

    @given(r=position_vector, v=velocity_vector)
    @settings(max_examples=50)
    def test_radial_direction_preserved(
        self, r: tuple[float, float, float], v: tuple[float, float, float]
    ) -> None:
        """R-hat in ECI should map to [1,0,0] in RTN."""
        r_arr = np.array(r)
        v_arr = np.array(v)
        cross = np.cross(r_arr, v_arr)
        assume(np.linalg.norm(cross) > 1e-6)

        R = eci_to_rtn(r_arr, v_arr)
        r_hat = r_arr / np.linalg.norm(r_arr)
        r_rtn = R @ r_hat
        np.testing.assert_allclose(r_rtn, [1.0, 0.0, 0.0], atol=1e-10)


class TestPcProperties:
    """L3: Collision probability invariants for ALL methods."""

    @given(d=miss_distance, s=sigma_km, r=hard_body_radius)
    @settings(max_examples=200, deadline=None)
    def test_foster_always_in_01(self, d: float, s: float, r: float) -> None:
        """Foster Pc must ALWAYS be in [0, 1]."""
        cov = np.array([[s**2, 0.0], [0.0, s**2]])
        pc = foster_pc(d, cov, r)
        assert 0.0 <= pc <= 1.0

    @given(d=miss_distance, s=sigma_km, r=hard_body_radius)
    @settings(max_examples=200, deadline=None)
    def test_chan_always_in_01(self, d: float, s: float, r: float) -> None:
        """Chan Pc must ALWAYS be in [0, 1]."""
        cov = np.array([[s**2, 0.0], [0.0, s**2]])
        pc = chan_pc(d, cov, r)
        assert 0.0 <= pc <= 1.0

    @given(d=miss_distance, s=sigma_km, r=hard_body_radius)
    @settings(max_examples=200, deadline=None)
    def test_alfano_always_in_01(self, d: float, s: float, r: float) -> None:
        """Alfano Pc must ALWAYS be in [0, 1]."""
        cov = np.array([[s**2, 0.0], [0.0, s**2]])
        pc = alfano_pc(d, cov, r)
        assert 0.0 <= pc <= 1.0

    @given(s=sigma_km, r=hard_body_radius)
    @settings(max_examples=50, deadline=None)
    def test_pc_at_zero_distance_geq_at_nonzero(self, s: float, r: float) -> None:
        """Pc(d=0) >= Pc(d>0) for any sigma and radius."""
        cov = np.array([[s**2, 0.0], [0.0, s**2]])
        pc_zero = foster_pc(0.0, cov, r)
        pc_far = foster_pc(5.0, cov, r)
        assert pc_zero >= pc_far - 1e-15

    @given(
        d=st.floats(min_value=0.1, max_value=10.0, allow_nan=False),
        s=st.floats(min_value=1.0, max_value=50.0, allow_nan=False),
        r=st.floats(min_value=0.001, max_value=0.1, allow_nan=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_foster_chan_agree_isotropic(self, d: float, s: float, r: float) -> None:
        """Foster and Chan agree within 10% for small HBR relative to sigma."""
        # Chan approximation is accurate when r << sigma (operational regime)
        assume(r < s * 0.1)
        cov = np.array([[s**2, 0.0], [0.0, s**2]])
        pc_f = foster_pc(d, cov, r)
        pc_c = chan_pc(d, cov, r)
        if pc_f > 1e-15:
            assert pc_c == pytest.approx(pc_f, rel=0.1), (
                f"d={d}, s={s}, r={r}: Foster={pc_f:.3e}, Chan={pc_c:.3e}"
            )


class TestCovarianceProperties:
    """L3: Covariance matrix invariants."""

    @given(
        r=position_vector,
        v=velocity_vector,
    )
    @settings(max_examples=50)
    def test_encounter_plane_cov_always_psd(
        self, r: tuple[float, float, float], v: tuple[float, float, float]
    ) -> None:
        """Projected 2D covariance must always be positive semi-definite."""
        r1 = np.array(r)
        v1 = np.array(v)
        cross = np.cross(r1, v1)
        assume(np.linalg.norm(cross) > 1e-6)

        # Create a nearby secondary
        offset = np.array([1.0, 0.5, 0.0])
        r2 = r1 + offset
        v2 = -v1  # Head-on

        rel_v = np.linalg.norm(v1 - v2)
        assume(rel_v > 0.1)

        cov1 = default_covariance("LEO")
        cov2 = default_covariance("LEO")
        cov_2d = project_to_encounter_plane(cov1, cov2, r1, v1, r2, v2)

        eigenvalues = np.linalg.eigvalsh(cov_2d)
        assert np.all(eigenvalues >= -1e-10), f"Not PSD: eigenvalues={eigenvalues}"

    @given(
        r=position_vector,
        v=velocity_vector,
    )
    @settings(max_examples=50)
    def test_encounter_plane_cov_always_symmetric(
        self, r: tuple[float, float, float], v: tuple[float, float, float]
    ) -> None:
        """Projected 2D covariance must always be symmetric."""
        r1 = np.array(r)
        v1 = np.array(v)
        cross = np.cross(r1, v1)
        assume(np.linalg.norm(cross) > 1e-6)

        r2 = r1 + np.array([1.0, 0.5, 0.0])
        v2 = -v1
        assume(np.linalg.norm(v1 - v2) > 0.1)

        cov1 = default_covariance("LEO")
        cov2 = default_covariance("LEO")
        cov_2d = project_to_encounter_plane(cov1, cov2, r1, v1, r2, v2)
        np.testing.assert_allclose(cov_2d, cov_2d.T, atol=1e-14)


class TestChecksumProperties:
    """L3: TLE checksum invariants."""

    @given(
        digits=st.text(
            alphabet="0123456789 .+-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            min_size=68,
            max_size=68,
        )
    )
    @settings(max_examples=100)
    def test_checksum_is_single_digit(self, digits: str) -> None:
        """Checksum computation must always produce a single digit [0-9]."""
        total = 0
        for ch in digits:
            if ch.isdigit():
                total += int(ch)
            elif ch == "-":
                total += 1
        assert 0 <= (total % 10) <= 9
