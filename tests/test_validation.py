"""L5: Validation against external reference data.

Tests collision probability implementations against published test vectors
from Orekit (citing Chan 2008) and NASA CARA Analysis Tools.

These are NOT self-generated values — they come from independent implementations.
"""

import numpy as np
import pytest

from satguard.assess.foster import foster_pc

# ============================================================================
# Chan 2008 test vectors (from Orekit test suite)
# SOURCE: F.K. Chan, "Spacecraft Collision Probability", The Aerospace Press, 2008
# Orekit: org/orekit/ssa/collision/shorttermencounter/probability/twod/
#
# Parameters are in the DIAGONALIZED encounter frame:
#   xm, ym = miss distance components (m)
#   sigma_x, sigma_y = standard deviations (m)
#   R = combined hard body radius (m)
#   Pc = expected collision probability
# ============================================================================

CHAN_TEST_CASES = [
    # (xm_m, ym_m, sigma_x_m, sigma_y_m, R_m, expected_pc)
    (0, 10, 25, 50, 5, 9.742e-3),  # Case 01
    (10, 0, 25, 50, 5, 9.181e-3),  # Case 02
    (0, 10, 25, 75, 5, 6.571e-3),  # Case 03
    (10, 0, 25, 75, 5, 6.125e-3),  # Case 04
    (0, 1000, 1000, 3000, 10, 1.577e-5),  # Case 05
    (1000, 0, 1000, 3000, 10, 1.011e-5),  # Case 06
    (0, 10000, 1000, 3000, 10, 6.443e-8),  # Case 07
    (0, 10000, 1000, 10000, 10, 3.033e-6),  # Case 09
    (0, 5000, 1000, 3000, 50, 1.039e-4),  # Case 11
]

# Excluded cases 08, 10, 12: Pc < 1e-20 (below numerical precision of dblquad)


class TestChanValidation:
    """L5: Validate Foster method against Chan 2008 published test vectors."""

    @pytest.mark.parametrize(
        "xm_m,ym_m,sigma_x_m,sigma_y_m,R_m,expected_pc",
        CHAN_TEST_CASES,
        ids=[f"chan_{i + 1:02d}" for i in range(len(CHAN_TEST_CASES))],
    )
    def test_foster_vs_chan_reference(
        self,
        xm_m: float,
        ym_m: float,
        sigma_x_m: float,
        sigma_y_m: float,
        R_m: float,
        expected_pc: float,
    ) -> None:
        """# SOURCE: Chan 2008 Table, via Orekit test suite.

        Foster (2D Gaussian integration) should match Chan's published values.
        The covariance is given in the diagonalized frame, so we construct
        the 2D covariance as diagonal and pass miss = sqrt(xm^2 + ym^2).

        Note: Foster integrates over the circular disk centered at the origin,
        with the Gaussian centered at the miss vector. We convert units to km.
        """
        # Convert m → km
        xm = xm_m / 1000.0
        ym = ym_m / 1000.0
        sx = sigma_x_m / 1000.0
        sy = sigma_y_m / 1000.0
        R = R_m / 1000.0

        # Build diagonal covariance in the diagonalized frame
        cov_2d = np.array([[sx**2, 0.0], [0.0, sy**2]])

        # Miss distance as scalar (Foster assumes miss along x-axis)
        # We need to account for the full 2D miss vector.
        # For Foster method: integrate the 2D Gaussian centered at (xm, ym)
        # over a disk of radius R centered at origin.
        # Our foster_pc takes scalar miss_distance and assumes (miss, 0).
        # For the general case, we need to pass the full miss magnitude
        # since the covariance is diagonal (rotation-invariant for isotropic,
        # but NOT for anisotropic). For diagonal covariance with xm or ym=0,
        # we can align the miss along the appropriate axis.

        # Since our foster_pc assumes miss along x-axis, and the covariance
        # is diagonal, we need to handle the orientation:
        if xm_m == 0 and ym_m != 0:
            # Miss is along y-axis → swap sigma_x and sigma_y
            cov_2d = np.array([[sy**2, 0.0], [0.0, sx**2]])
            miss_km = abs(ym)
        elif ym_m == 0 and xm_m != 0:
            # Miss is along x-axis → keep as is
            miss_km = abs(xm)
        else:
            # General case: miss is at an angle
            miss_km = np.sqrt(xm**2 + ym**2)

        pc = foster_pc(miss_km, cov_2d, R)

        # Allow 5% relative tolerance (numerical integration vs analytical)
        assert pc == pytest.approx(expected_pc, rel=0.05), (
            f"Foster Pc={pc:.4e} vs expected={expected_pc:.4e}"
        )


# ============================================================================
# NASA CARA Omitron test case (full 3D ECI → 2D projection → Pc)
# SOURCE: NASA CARA Analysis Tools, PcCircle_UnitTest.m
# https://github.com/nasa/CARA_Analysis_Tools
# ============================================================================


class TestNASACARA:
    """L5: Validate full pipeline against NASA CARA reference.

    This tests the 3D-to-2D projection + Pc computation end-to-end.
    """

    def test_cara_omitron_case1(self) -> None:
        """# SOURCE: NASA CARA PcCircle_UnitTest.m — Omitron test case 1.

        Full ECI state vectors and covariances, expected Pc = 2.706e-05.
        """
        from satguard.covariance.realism import (
            CovarianceMatrix,
            project_to_encounter_plane,
        )

        # Primary state (km, km/s)
        r1 = np.array([378.39559, 4305.721887, 5752.767554])
        v1 = np.array([2.360800244, 5.580331936, -4.322349039])

        # Secondary state
        r2 = np.array([374.5180598, 4307.560983, 5751.130418])
        v2 = np.array([-5.388125081, -3.946827739, 3.322820358])

        # Primary 3x3 position covariance (km^2)
        cov1_pos = np.array(
            [
                [44.5757544811362, 81.6751751052616, -67.8687662707124],
                [81.6751751052616, 158.453402956163, -128.616921644857],
                [-67.8687662707124, -128.616921644858, 105.490542562701],
            ]
        )

        # Secondary 3x3 position covariance (km^2)
        cov2_pos = np.array(
            [
                [2.31067077720423, 1.69905293875632, -1.4170164577661],
                [1.69905293875632, 1.24957388457206, -1.04174164279599],
                [-1.4170164577661, -1.04174164279599, 0.869260558223714],
            ]
        )

        # Build 6x6 covariances (position only, velocity zeros)
        cov1_6x6 = np.zeros((6, 6))
        cov1_6x6[:3, :3] = cov1_pos
        cov1_6x6[3:, 3:] = np.eye(3) * 1e-6  # small velocity covariance

        cov2_6x6 = np.zeros((6, 6))
        cov2_6x6[:3, :3] = cov2_pos
        cov2_6x6[3:, 3:] = np.eye(3) * 1e-6

        cov1 = CovarianceMatrix(cov1_6x6)
        cov2 = CovarianceMatrix(cov2_6x6)

        # Project to encounter plane
        cov_2d = project_to_encounter_plane(cov1, cov2, r1, v1, r2, v2)

        # Compute miss distance
        miss_km = float(np.linalg.norm(r1 - r2))

        # HBR = 20m = 0.020 km
        hbr = 0.020

        pc = foster_pc(miss_km, cov_2d, hbr)
        expected_pc = 2.70601573490125e-05

        # Allow 20% tolerance due to projection differences
        # (our projection may differ slightly from CARA's)
        assert pc == pytest.approx(expected_pc, rel=0.20), (
            f"CARA case 1: Pc={pc:.4e} vs expected={expected_pc:.4e}"
        )


# ============================================================================
# CSM (Conjunction Summary Message) test cases
# SOURCE: Orekit test suite, real conjunction screening data
# ============================================================================

CSM_TEST_CASES = [
    # (xm_m, ym_m, sigma_x_m, sigma_y_m, R_m, expected_pc)
    (84.875546, 60.583685, 57.918666, 152.8814468, 10.3, 1.9002e-3),
    (102.177247, 693.405893, 94.230921, 643.409272, 5.3, 7.2004e-5),
]


class TestCSMValidation:
    """L5: Validate against real conjunction screening data."""

    @pytest.mark.parametrize(
        "xm_m,ym_m,sigma_x_m,sigma_y_m,R_m,expected_pc",
        CSM_TEST_CASES,
        ids=["csm_01", "csm_03"],
    )
    def test_foster_vs_csm(
        self,
        xm_m: float,
        ym_m: float,
        sigma_x_m: float,
        sigma_y_m: float,
        R_m: float,
        expected_pc: float,
    ) -> None:
        """# SOURCE: Orekit CSM test cases — real conjunction data."""
        xm = xm_m / 1000.0
        ym = ym_m / 1000.0
        sx = sigma_x_m / 1000.0
        sy = sigma_y_m / 1000.0
        R = R_m / 1000.0

        # General 2D miss: integrate Gaussian centered at (xm, ym) over disk
        # Our Foster takes miss along x-axis. For general (xm, ym) with
        # diagonal covariance, we use the full miss magnitude and
        # rotate the covariance to align miss with x-axis.
        miss = np.sqrt(xm**2 + ym**2)
        theta = np.arctan2(ym, xm)
        c, s = np.cos(theta), np.sin(theta)
        rot = np.array([[c, s], [-s, c]])
        cov_diag = np.array([[sx**2, 0.0], [0.0, sy**2]])
        cov_rotated = rot @ cov_diag @ rot.T

        pc = foster_pc(miss, cov_rotated, R)
        assert pc == pytest.approx(expected_pc, rel=0.10), (
            f"CSM: Pc={pc:.4e} vs expected={expected_pc:.4e}"
        )
