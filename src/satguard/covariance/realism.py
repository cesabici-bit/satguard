"""Covariance handling for collision probability computation.

Provides default covariance matrices (empirical values from NASA CARA),
coordinate transformations (ECI→RTN), projection to encounter plane,
and covariance realism assessment.

Reference: Vallado 5th Ed Section 3.3, NASA CARA best practices.
Assessment: Hejduk et al. 2013, "Covariance Realism" (NASA CARA).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

# Default covariance values (diagonal, in km^2 and km^2/s^2)
# SOURCE: NASA CARA empirical covariance estimates for TLE-derived orbits
# These are conservative estimates for objects without real covariance data
_DEFAULT_COV = {
    "LEO": {
        "pos_sigma_km": np.array([1.0, 1.0, 1.0]),  # ~1 km position uncertainty
        "vel_sigma_km_s": np.array([0.001, 0.001, 0.001]),
    },
    "MEO": {
        "pos_sigma_km": np.array([5.0, 5.0, 5.0]),
        "vel_sigma_km_s": np.array([0.005, 0.005, 0.005]),
    },
    "GEO": {
        "pos_sigma_km": np.array([10.0, 10.0, 10.0]),
        "vel_sigma_km_s": np.array([0.01, 0.01, 0.01]),
    },
}


class CovarianceMatrix:
    """6x6 position-velocity covariance matrix in a specified frame."""

    def __init__(self, matrix: NDArray[np.float64], frame: str = "ECI") -> None:
        assert matrix.shape == (6, 6), f"Expected 6x6, got {matrix.shape}"
        self.matrix = matrix
        self.frame = frame

    @property
    def position_cov(self) -> NDArray[np.float64]:
        """3x3 position covariance submatrix."""
        return self.matrix[:3, :3]

    @property
    def velocity_cov(self) -> NDArray[np.float64]:
        """3x3 velocity covariance submatrix."""
        return self.matrix[3:6, 3:6]

    def is_positive_semidefinite(self) -> bool:
        """Check if the covariance matrix is positive semi-definite."""
        eigenvalues = np.linalg.eigvalsh(self.matrix)
        return bool(np.all(eigenvalues >= -1e-10))


def default_covariance(regime: str = "LEO") -> CovarianceMatrix:
    """Get a default diagonal covariance matrix for a given orbit regime.

    Args:
        regime: One of 'LEO', 'MEO', 'GEO'.

    Returns:
        CovarianceMatrix with empirical default values.
    """
    regime = regime.upper()
    if regime not in _DEFAULT_COV:
        raise ValueError(f"Unknown regime '{regime}'. Use LEO, MEO, or GEO.")

    vals = _DEFAULT_COV[regime]
    diag = np.concatenate([vals["pos_sigma_km"] ** 2, vals["vel_sigma_km_s"] ** 2])
    matrix = np.diag(diag)
    return CovarianceMatrix(matrix, frame="ECI")


def eci_to_rtn(
    r: NDArray[np.float64],
    v: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Compute the ECI→RTN rotation matrix.

    RTN (Radial, Transverse, Normal) frame:
      R = r_hat (radial)
      N = (r × v) / |r × v| (orbit normal)
      T = N × R (transverse, along-track)

    Reference: Vallado 5th Ed Section 3.3

    Args:
        r: Position vector [km] in ECI.
        v: Velocity vector [km/s] in ECI.

    Returns:
        3x3 rotation matrix R such that v_RTN = R @ v_ECI.
    """
    r_hat = r / np.linalg.norm(r)
    h = np.cross(r, v)
    n_hat = h / np.linalg.norm(h)
    t_hat = np.cross(n_hat, r_hat)

    # Each row is a unit vector of the RTN frame expressed in ECI
    rotation = np.array([r_hat, t_hat, n_hat])
    return rotation


def _transform_covariance(
    cov: CovarianceMatrix,
    r: NDArray[np.float64],
    v: NDArray[np.float64],
) -> CovarianceMatrix:
    """Transform a 6x6 covariance from ECI to RTN frame.

    C_RTN = T @ C_ECI @ T^T where T is the block-diagonal rotation matrix.
    """
    rot_3x3 = eci_to_rtn(r, v)
    # Build 6x6 block-diagonal transformation
    T = np.zeros((6, 6))
    T[:3, :3] = rot_3x3
    T[3:6, 3:6] = rot_3x3
    transformed = T @ cov.matrix @ T.T
    return CovarianceMatrix(transformed, frame="RTN")


def project_to_encounter_plane(
    cov_primary: CovarianceMatrix,
    cov_secondary: CovarianceMatrix,
    r_primary: NDArray[np.float64],
    v_primary: NDArray[np.float64],
    r_secondary: NDArray[np.float64],
    v_secondary: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Project combined covariance onto the 2D encounter plane.

    The encounter plane is perpendicular to the relative velocity vector.
    Returns a 2x2 covariance matrix in the encounter plane.

    This follows the standard conjunction assessment methodology:
    1. Transform both covariances to a common frame
    2. Sum the position covariances (combined uncertainty)
    3. Project onto the plane perpendicular to relative velocity

    Args:
        cov_primary: Covariance of primary object.
        cov_secondary: Covariance of secondary object.
        r_primary, v_primary: Primary state at TCA.
        r_secondary, v_secondary: Secondary state at TCA.

    Returns:
        2x2 numpy array — covariance in the encounter plane.
    """
    # Relative velocity defines the encounter plane normal
    v_rel = v_primary - v_secondary
    v_rel_mag = np.linalg.norm(v_rel)
    assert v_rel_mag > 1e-10, "Relative velocity too small for encounter plane projection"

    # Build encounter plane basis
    # z_hat = relative velocity direction (normal to encounter plane)
    z_hat = v_rel / v_rel_mag

    # x_hat = perpendicular in the radial-ish direction
    miss_vec = r_primary - r_secondary
    # Remove component along z_hat
    miss_perp = miss_vec - np.dot(miss_vec, z_hat) * z_hat
    miss_perp_mag = np.linalg.norm(miss_perp)
    if miss_perp_mag < 1e-10:
        # Miss vector is along relative velocity — pick arbitrary perpendicular
        x_hat = np.array([1.0, 0.0, 0.0])
        if abs(np.dot(x_hat, z_hat)) > 0.9:
            x_hat = np.array([0.0, 1.0, 0.0])
        x_hat = x_hat - np.dot(x_hat, z_hat) * z_hat
        x_hat = x_hat / np.linalg.norm(x_hat)
    else:
        x_hat = miss_perp / miss_perp_mag

    # y_hat completes the right-handed frame
    y_hat = np.cross(z_hat, x_hat)

    # Projection matrix: 2x3, maps 3D position to 2D encounter plane
    P = np.array([x_hat, y_hat])  # shape (2, 3)

    # Combined 3x3 position covariance in ECI
    cov_combined_3d = cov_primary.position_cov + cov_secondary.position_cov

    # Project to 2D: C_2d = P @ C_3d @ P^T
    cov_2d = P @ cov_combined_3d @ P.T

    return cov_2d


# ---------------------------------------------------------------------------
# Covariance realism assessment (v0.2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CovarianceAssessment:
    """Result of covariance realism assessment.

    Metrics based on NASA CARA best practices (Hejduk et al. 2013).
    """

    eigenvalue_ratio: float
    """Max / min eigenvalue of 3x3 position covariance. ~1 = isotropic."""

    condition_number: float
    """Condition number of full 6x6 matrix."""

    is_positive_definite: bool
    """True if all eigenvalues are strictly positive."""

    position_sigma_max_km: float
    """sqrt(max eigenvalue) of position covariance [km]."""

    position_sigma_min_km: float
    """sqrt(min eigenvalue) of position covariance [km]."""

    realism_flag: str
    """'REALISTIC', 'SUSPECT', or 'DEFAULT'."""


def assess_covariance(cov: CovarianceMatrix) -> CovarianceAssessment:
    """Assess realism of a covariance matrix.

    Criteria (SOURCE: NASA CARA, Hejduk et al. 2013):
    - Eigenvalue ratio > 1000 → SUSPECT (overly elongated uncertainty ellipsoid)
    - Condition number > 1e6 → SUSPECT
    - Diagonal matrix matching a default → DEFAULT

    Args:
        cov: CovarianceMatrix to assess.

    Returns:
        CovarianceAssessment with quality metrics and flag.
    """
    pos_cov = cov.position_cov
    pos_eig = np.linalg.eigvalsh(pos_cov)
    full_eig = np.linalg.eigvalsh(cov.matrix)

    eig_min = float(pos_eig[0])
    eig_max = float(pos_eig[-1])

    # Guard against zero/negative eigenvalues
    is_pd = bool(np.all(full_eig > 1e-15))

    eigenvalue_ratio = eig_max / eig_min if eig_min > 1e-15 else float("inf")

    full_eig_abs = np.abs(full_eig)
    if full_eig_abs[0] > 1e-30:
        condition_number = float(full_eig_abs[-1] / full_eig_abs[0])
    else:
        condition_number = float("inf")

    sigma_max = float(np.sqrt(max(eig_max, 0.0)))
    sigma_min = float(np.sqrt(max(eig_min, 0.0)))

    # Determine realism flag
    flag = _classify_covariance(cov, eigenvalue_ratio, condition_number, is_pd)

    return CovarianceAssessment(
        eigenvalue_ratio=eigenvalue_ratio,
        condition_number=condition_number,
        is_positive_definite=is_pd,
        position_sigma_max_km=sigma_max,
        position_sigma_min_km=sigma_min,
        realism_flag=flag,
    )


def _classify_covariance(
    cov: CovarianceMatrix,
    eigenvalue_ratio: float,
    condition_number: float,
    is_pd: bool,
) -> str:
    """Classify covariance as REALISTIC, SUSPECT, or DEFAULT."""
    # Check if it matches a default diagonal matrix
    for regime_vals in _DEFAULT_COV.values():
        diag = np.concatenate(
            [regime_vals["pos_sigma_km"] ** 2, regime_vals["vel_sigma_km_s"] ** 2]
        )
        if np.allclose(cov.matrix, np.diag(diag), atol=1e-15):
            return "DEFAULT"

    if not is_pd:
        return "SUSPECT"
    if eigenvalue_ratio > 1000.0:
        return "SUSPECT"
    if condition_number > 1e6:
        return "SUSPECT"

    return "REALISTIC"


def scale_covariance(
    cov: CovarianceMatrix, factor: float,
) -> CovarianceMatrix:
    """Scale a covariance matrix by a scalar factor.

    Useful for sensitivity analysis (e.g., factor=2 doubles uncertainty).

    Args:
        cov: Original covariance matrix.
        factor: Scaling factor (must be positive).

    Returns:
        New CovarianceMatrix with scaled values.
    """
    assert factor > 0, f"Scale factor must be positive, got {factor}"
    return CovarianceMatrix(cov.matrix * factor, frame=cov.frame)
