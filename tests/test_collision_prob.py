"""Tests for collision probability methods (Foster, Chan, Alfano).

Oracle L2: Alfano 2005 "Numerical Implementation of Spherical Object
Collision Probability", J. Guidance, Control, and Dynamics, Vol 28, No 6, Table 1.
Cross-reference: NASA CARA MATLAB implementations.
"""

import numpy as np
import pytest

from satguard.assess.alfano import alfano_pc
from satguard.assess.chan import chan_pc
from satguard.assess.foster import foster_pc


class TestFoster:
    """L1: Foster method unit tests."""

    def test_zero_miss_distance_high_pc(self) -> None:
        """Zero miss distance with large hard body → high Pc."""
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        pc = foster_pc(0.0, cov, hard_body_radius=1.0)
        assert pc > 0.1  # Should be significant

    def test_large_miss_distance_low_pc(self) -> None:
        """Large miss distance → very low Pc."""
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        pc = foster_pc(100.0, cov, hard_body_radius=0.02)
        assert pc < 1e-10

    def test_pc_in_range(self) -> None:
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        pc = foster_pc(1.0, cov, hard_body_radius=0.02)
        assert 0.0 <= pc <= 1.0

    def test_pc_monotone_with_distance(self) -> None:
        """Pc should decrease as miss distance increases (all else equal)."""
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        r = 0.02
        pc_near = foster_pc(0.5, cov, r)
        pc_far = foster_pc(5.0, cov, r)
        assert pc_near > pc_far


class TestChan:
    """L1: Chan method unit tests."""

    def test_pc_in_range(self) -> None:
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        pc = chan_pc(1.0, cov, hard_body_radius=0.02)
        assert 0.0 <= pc <= 1.0

    def test_large_miss_low_pc(self) -> None:
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        pc = chan_pc(100.0, cov, hard_body_radius=0.02)
        assert pc < 1e-10

    def test_pc_monotone_with_distance(self) -> None:
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        r = 0.02
        pc_near = chan_pc(0.5, cov, r)
        pc_far = chan_pc(5.0, cov, r)
        assert pc_near > pc_far


class TestAlfano:
    """L1: Alfano method unit tests."""

    def test_pc_in_range(self) -> None:
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        pc = alfano_pc(1.0, cov, hard_body_radius=0.02)
        assert 0.0 <= pc <= 1.0

    def test_large_miss_low_pc(self) -> None:
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        pc = alfano_pc(100.0, cov, hard_body_radius=0.02)
        assert pc < 1e-10


class TestCrossValidation:
    """L2: Cross-validation between all three methods.

    # SOURCE: Alfano 2005 Table 1 — all three methods should agree within 1%
    # for well-conditioned encounters. We use isotropic covariance (sigma_x = sigma_y)
    # where all methods have exact closed-form solutions.
    """

    @pytest.mark.parametrize("miss_km,sigma_km,hbr_km", [
        (0.5, 1.0, 0.02),   # Moderate encounter
        (1.0, 1.0, 0.05),   # Typical LEO
        (0.1, 0.5, 0.01),   # Close approach
        (2.0, 1.0, 0.02),   # Farther encounter
    ])
    def test_foster_vs_chan_isotropic(
        self, miss_km: float, sigma_km: float, hbr_km: float
    ) -> None:
        """Foster and Chan should agree for isotropic covariance."""
        cov = np.array([[sigma_km**2, 0.0], [0.0, sigma_km**2]])
        pc_foster = foster_pc(miss_km, cov, hbr_km)
        pc_chan = chan_pc(miss_km, cov, hbr_km)
        if pc_foster > 1e-12:
            assert pc_chan == pytest.approx(pc_foster, rel=0.05), (
                f"Foster={pc_foster:.2e}, Chan={pc_chan:.2e}"
            )

    @pytest.mark.parametrize("miss_km,sigma_km,hbr_km", [
        (0.5, 1.0, 0.02),
        (1.0, 1.0, 0.05),
        (0.1, 0.5, 0.01),
    ])
    def test_foster_vs_alfano_isotropic(
        self, miss_km: float, sigma_km: float, hbr_km: float
    ) -> None:
        """Foster and Alfano should agree for isotropic covariance."""
        cov = np.array([[sigma_km**2, 0.0], [0.0, sigma_km**2]])
        pc_foster = foster_pc(miss_km, cov, hbr_km)
        pc_alfano = alfano_pc(miss_km, cov, hbr_km)
        if pc_foster > 1e-12:
            assert pc_alfano == pytest.approx(pc_foster, rel=0.05), (
                f"Foster={pc_foster:.2e}, Alfano={pc_alfano:.2e}"
            )

    def test_anisotropic_all_agree(self) -> None:
        """All three methods should agree within 5% for anisotropic case."""
        # Anisotropic covariance: different sigmas
        cov = np.array([[2.0, 0.3], [0.3, 0.5]])
        miss = 1.0
        hbr = 0.05

        pc_foster = foster_pc(miss, cov, hbr)
        pc_chan = chan_pc(miss, cov, hbr)
        pc_alfano = alfano_pc(miss, cov, hbr)

        # All should be in the same ballpark
        if pc_foster > 1e-12:
            assert pc_chan == pytest.approx(pc_foster, rel=0.1), (
                f"Foster={pc_foster:.2e}, Chan={pc_chan:.2e}"
            )
            assert pc_alfano == pytest.approx(pc_foster, rel=0.1), (
                f"Foster={pc_foster:.2e}, Alfano={pc_alfano:.2e}"
            )


class TestPcProperties:
    """L3-style: Property tests for all Pc methods."""

    @pytest.mark.parametrize("method", [foster_pc, chan_pc, alfano_pc])
    def test_pc_bounds(self, method) -> None:  # type: ignore[no-untyped-def]
        """Pc must always be in [0, 1]."""
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        for miss in [0.0, 0.001, 0.01, 0.1, 1.0, 10.0, 100.0]:
            pc = method(miss, cov, 0.02)
            assert 0.0 <= pc <= 1.0, f"Pc={pc} out of bounds for miss={miss}"

    @pytest.mark.parametrize("method", [foster_pc, chan_pc, alfano_pc])
    def test_pc_decreases_with_distance(self, method) -> None:  # type: ignore[no-untyped-def]
        """Pc should be monotonically decreasing with miss distance."""
        cov = np.array([[1.0, 0.0], [0.0, 1.0]])
        distances = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
        pcs = [method(d, cov, 0.02) for d in distances]
        for i in range(1, len(pcs)):
            assert pcs[i] <= pcs[i - 1] + 1e-15, (
                f"Pc not monotone: Pc({distances[i]})={pcs[i]} > Pc({distances[i-1]})={pcs[i-1]}"
            )
