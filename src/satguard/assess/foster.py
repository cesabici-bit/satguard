"""Foster collision probability method.

Computes collision probability using 2D Gaussian integration over a
circular hard-body region in the encounter plane.

Reference:
  Foster, J.L. (1992), "The Analytic Basis for Debris Avoidance Operations
  for the International Space Station"
  Alfano, S. (2005), "Numerical Implementation of Spherical Object
  Collision Probability", J. Guidance, Control, and Dynamics, Vol 28, No 6.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import dblquad


def foster_pc(
    miss_distance: float,
    cov_2d: NDArray[np.float64],
    hard_body_radius: float = 0.02,
) -> float:
    """Compute collision probability using the Foster (2D Gaussian integration) method.

    Integrates the joint probability density over a circular hard-body region
    centered at the miss distance vector in the encounter plane.

    Args:
        miss_distance: Miss distance in km (scalar — assumed along x-axis of encounter plane).
        cov_2d: 2x2 combined covariance matrix in encounter plane [km^2].
        hard_body_radius: Combined hard-body radius in km (default 20m = 0.02 km).

    Returns:
        Collision probability (0 ≤ Pc ≤ 1).
    """
    assert cov_2d.shape == (2, 2), f"Expected 2x2 covariance, got {cov_2d.shape}"
    assert hard_body_radius > 0, "Hard-body radius must be positive"

    # Eigendecompose the 2x2 covariance
    eigenvalues = np.linalg.eigvalsh(cov_2d)
    assert np.all(eigenvalues > 0), (
        f"Covariance must be positive definite, eigenvalues={eigenvalues}"
    )

    # Miss vector in encounter plane: [miss_distance, 0]
    mx = miss_distance
    my = 0.0

    # Inverse of covariance
    det_C = np.linalg.det(cov_2d)
    C_inv = np.linalg.inv(cov_2d)

    # 2D Gaussian PDF
    norm_const = 1.0 / (2.0 * np.pi * np.sqrt(det_C))

    def integrand(y: float, x: float) -> float:
        dx = x - mx
        dy = y - my
        v = np.array([dx, dy])
        exponent = -0.5 * v @ C_inv @ v
        return float(norm_const * np.exp(exponent))

    # Integration bounds: circle of radius hard_body_radius centered at origin
    r = hard_body_radius

    def y_lower(x: float) -> float:
        d = r * r - x * x
        return -np.sqrt(max(d, 0.0))

    def y_upper(x: float) -> float:
        d = r * r - x * x
        return np.sqrt(max(d, 0.0))

    result, _error = dblquad(
        integrand,
        -r,  # x lower
        r,   # x upper
        y_lower,
        y_upper,
        epsabs=1e-14,
        epsrel=1e-10,
    )

    # Clamp to [0, 1] (numerical errors can produce tiny negatives)
    return float(np.clip(result, 0.0, 1.0))
