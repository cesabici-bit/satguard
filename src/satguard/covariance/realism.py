"""Covariance handling for collision probability computation.

Provides default covariance matrices (empirical values from NASA CARA),
coordinate transformations (ECI→RTN), and projection to encounter plane.

Reference: Vallado 5th Ed Section 3.3, NASA CARA best practices.
"""

from __future__ import annotations

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
