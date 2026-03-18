"""Tests for covariance realism assessment (v0.2).

Oracle L2: NASA CARA, Hejduk et al. 2013 — "Covariance Realism".
"""

import numpy as np
import pytest

from satguard.covariance.realism import (
    CovarianceAssessment,
    CovarianceMatrix,
    assess_covariance,
    default_covariance,
    scale_covariance,
)


class TestAssessCovariance:
    """L1: assess_covariance unit tests."""

    def test_default_leo_flagged_as_default(self) -> None:
        cov = default_covariance("LEO")
        result = assess_covariance(cov)
        assert result.realism_flag == "DEFAULT"

    def test_default_meo_flagged_as_default(self) -> None:
        cov = default_covariance("MEO")
        result = assess_covariance(cov)
        assert result.realism_flag == "DEFAULT"

    def test_default_geo_flagged_as_default(self) -> None:
        cov = default_covariance("GEO")
        result = assess_covariance(cov)
        assert result.realism_flag == "DEFAULT"

    def test_isotropic_eigenvalue_ratio_one(self) -> None:
        """Isotropic diagonal covariance → eigenvalue ratio = 1.0."""
        cov = default_covariance("LEO")
        result = assess_covariance(cov)
        assert result.eigenvalue_ratio == pytest.approx(1.0)

    def test_realistic_non_default_matrix(self) -> None:
        """A valid non-default PSD matrix should be REALISTIC."""
        # SOURCE: Plausible covariance for a well-tracked LEO object
        # Position sigmas: R=0.5km, T=2km, N=0.8km; velocity ~1e-3 km/s
        # Condition number ~4.0/1e-4 = 4e4 < 1e6 threshold
        diag = np.array([0.25, 4.0, 0.64, 1e-4, 4e-4, 1e-4])
        cov = CovarianceMatrix(np.diag(diag))
        result = assess_covariance(cov)
        assert result.realism_flag == "REALISTIC"
        assert result.eigenvalue_ratio == pytest.approx(4.0 / 0.25)  # 16.0
        assert result.is_positive_definite

    def test_highly_anisotropic_flagged_suspect(self) -> None:
        """Eigenvalue ratio > 1000 → SUSPECT.
        # SOURCE: NASA CARA Hejduk et al. 2013 — extreme anisotropy indicates
        # possible data quality issues or incorrect frame transformation.
        """
        # Position sigmas: R=0.01km, T=100km → ratio = 10000/0.0001 = 1e8
        diag = np.array([0.0001, 10000.0, 1.0, 1e-6, 1e-6, 1e-6])
        cov = CovarianceMatrix(np.diag(diag))
        result = assess_covariance(cov)
        assert result.realism_flag == "SUSPECT"
        assert result.eigenvalue_ratio > 1000.0

    def test_non_pd_flagged_suspect(self) -> None:
        """Non-positive-definite matrix → SUSPECT."""
        mat = np.diag([1.0, 1.0, -0.1, 1e-6, 1e-6, 1e-6])
        cov = CovarianceMatrix(mat)
        result = assess_covariance(cov)
        assert result.realism_flag == "SUSPECT"
        assert not result.is_positive_definite

    def test_sigma_values_correct(self) -> None:
        """Position sigma max/min should be sqrt of eigenvalues."""
        diag = np.array([4.0, 9.0, 1.0, 1e-6, 1e-6, 1e-6])
        cov = CovarianceMatrix(np.diag(diag))
        result = assess_covariance(cov)
        assert result.position_sigma_max_km == pytest.approx(3.0)
        assert result.position_sigma_min_km == pytest.approx(1.0)

    def test_returns_frozen_dataclass(self) -> None:
        cov = default_covariance("LEO")
        result = assess_covariance(cov)
        assert isinstance(result, CovarianceAssessment)
        with pytest.raises(AttributeError):
            result.realism_flag = "HACKED"  # type: ignore[misc]


class TestScaleCovariance:
    """L1: scale_covariance tests."""

    def test_scale_by_two(self) -> None:
        cov = default_covariance("LEO")
        scaled = scale_covariance(cov, 2.0)
        np.testing.assert_allclose(scaled.matrix, cov.matrix * 2.0)

    def test_scale_preserves_frame(self) -> None:
        cov = default_covariance("LEO")
        scaled = scale_covariance(cov, 3.0)
        assert scaled.frame == cov.frame

    def test_negative_factor_raises(self) -> None:
        cov = default_covariance("LEO")
        with pytest.raises(AssertionError):
            scale_covariance(cov, -1.0)

    def test_scaled_is_no_longer_default(self) -> None:
        """Scaled default matrix should NOT be flagged as DEFAULT."""
        cov = default_covariance("LEO")
        scaled = scale_covariance(cov, 1.5)
        result = assess_covariance(scaled)
        assert result.realism_flag != "DEFAULT"
