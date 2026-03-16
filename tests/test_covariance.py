"""Tests for covariance handling.

Oracle L2: Vallado 5th Ed Section 3.3 — RTN frame transformation.
"""

import numpy as np
import pytest

from satguard.covariance.realism import (
    default_covariance,
    eci_to_rtn,
    project_to_encounter_plane,
)


class TestCovarianceMatrix:
    """L1: CovarianceMatrix dataclass tests."""

    def test_default_leo_is_psd(self) -> None:
        cov = default_covariance("LEO")
        assert cov.is_positive_semidefinite()

    def test_default_meo_is_psd(self) -> None:
        cov = default_covariance("MEO")
        assert cov.is_positive_semidefinite()

    def test_default_geo_is_psd(self) -> None:
        cov = default_covariance("GEO")
        assert cov.is_positive_semidefinite()

    def test_unknown_regime_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown regime"):
            default_covariance("HEO")

    def test_position_cov_shape(self) -> None:
        cov = default_covariance("LEO")
        assert cov.position_cov.shape == (3, 3)

    def test_velocity_cov_shape(self) -> None:
        cov = default_covariance("LEO")
        assert cov.velocity_cov.shape == (3, 3)


class TestECItoRTN:
    """L2: RTN rotation matrix properties.
    # SOURCE: Vallado 5th Ed Section 3.3 — RTN is orthonormal right-handed frame.
    """

    def test_rotation_is_orthogonal(self) -> None:
        """R^T @ R = I for any valid position/velocity."""
        r = np.array([7000.0, 0.0, 0.0])
        v = np.array([0.0, 7.5, 0.0])
        R = eci_to_rtn(r, v)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)

    def test_determinant_is_one(self) -> None:
        """Proper rotation (not reflection)."""
        r = np.array([7000.0, 0.0, 0.0])
        v = np.array([0.0, 7.5, 0.0])
        R = eci_to_rtn(r, v)
        assert np.linalg.det(R) == pytest.approx(1.0, abs=1e-12)

    def test_radial_maps_to_r_hat(self) -> None:
        """Position vector should map to radial direction [1,0,0] in RTN."""
        r = np.array([7000.0, 0.0, 0.0])
        v = np.array([0.0, 7.5, 0.0])
        R = eci_to_rtn(r, v)
        r_rtn = R @ (r / np.linalg.norm(r))
        np.testing.assert_allclose(r_rtn, [1.0, 0.0, 0.0], atol=1e-12)

    def test_inclined_orbit(self) -> None:
        """Test with inclined orbit (not aligned with axes)."""
        r = np.array([5000.0, 5000.0, 0.0])
        v = np.array([-3.0, 3.0, 5.0])
        R = eci_to_rtn(r, v)
        # Must still be orthogonal
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)


class TestEncounterPlaneProjection:
    """L1: Tests for 2D encounter plane projection."""

    def test_combined_cov_is_2x2(self) -> None:
        cov1 = default_covariance("LEO")
        cov2 = default_covariance("LEO")
        r1 = np.array([7000.0, 0.0, 0.0])
        v1 = np.array([0.0, 7.5, 0.0])
        r2 = np.array([7001.0, 0.0, 0.0])
        v2 = np.array([0.0, -7.5, 0.0])
        cov_2d = project_to_encounter_plane(cov1, cov2, r1, v1, r2, v2)
        assert cov_2d.shape == (2, 2)

    def test_projected_cov_is_psd(self) -> None:
        """Combined projected covariance must be positive semi-definite."""
        cov1 = default_covariance("LEO")
        cov2 = default_covariance("LEO")
        r1 = np.array([7000.0, 0.0, 0.0])
        v1 = np.array([0.0, 7.5, 0.0])
        r2 = np.array([7001.0, 0.0, 0.0])
        v2 = np.array([0.0, -7.5, 0.0])
        cov_2d = project_to_encounter_plane(cov1, cov2, r1, v1, r2, v2)
        eigenvalues = np.linalg.eigvalsh(cov_2d)
        assert np.all(eigenvalues >= -1e-10)

    def test_symmetric(self) -> None:
        cov1 = default_covariance("LEO")
        cov2 = default_covariance("LEO")
        r1 = np.array([7000.0, 0.0, 0.0])
        v1 = np.array([0.0, 7.5, 0.0])
        r2 = np.array([7001.0, 0.0, 0.0])
        v2 = np.array([0.0, -7.5, 0.0])
        cov_2d = project_to_encounter_plane(cov1, cov2, r1, v1, r2, v2)
        np.testing.assert_allclose(cov_2d, cov_2d.T, atol=1e-15)
