"""Chan collision probability method.

Uses the non-central chi-squared CDF approach for efficient computation.

Reference:
  Chan, F.K. (2008), "Spacecraft Collision Probability", Chapter 4.
  Alfano, S. (2005), Table 1 — cross-validation values.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def chan_pc(
    miss_distance: float,
    cov_2d: NDArray[np.float64],
    hard_body_radius: float = 0.02,
) -> float:
    """Compute collision probability using the Chan method.

    Transforms the problem to a non-central chi-squared distribution.
    Efficient and accurate for most encounter geometries.

    Args:
        miss_distance: Miss distance in km.
        cov_2d: 2x2 combined covariance matrix in encounter plane [km^2].
        hard_body_radius: Combined hard-body radius in km.

    Returns:
        Collision probability (0 ≤ Pc ≤ 1).
    """
    assert cov_2d.shape == (2, 2)
    assert hard_body_radius > 0

    # Eigendecompose to get principal axes
    eigenvalues, eigenvectors = np.linalg.eigh(cov_2d)
    assert np.all(eigenvalues > 0), f"Covariance must be positive definite, got {eigenvalues}"

    sigma_1_sq = eigenvalues[0]
    sigma_2_sq = eigenvalues[1]

    # Transform miss vector to principal axes
    miss_vec = np.array([miss_distance, 0.0])
    miss_rotated = eigenvectors.T @ miss_vec
    mu_1 = miss_rotated[0]
    mu_2 = miss_rotated[1]

    # If covariance is approximately circular, use Rice distribution approach
    ratio = sigma_1_sq / sigma_2_sq if sigma_2_sq > 0 else 1.0

    if 0.99 < ratio < 1.01:
        # Nearly circular — use simple exponential formula
        sigma_sq = (sigma_1_sq + sigma_2_sq) / 2.0
        d_sq = miss_distance**2
        r_sq = hard_body_radius**2
        pc = (r_sq / (2.0 * sigma_sq)) * np.exp(-d_sq / (2.0 * sigma_sq))
        return float(np.clip(pc, 0.0, 1.0))

    # General case: use series expansion
    # Following Chan's formulation via the non-central chi-squared approach
    # Scale variables by the smaller eigenvalue
    min(sigma_1_sq, sigma_2_sq)
    max(sigma_1_sq, sigma_2_sq)

    # Non-centrality parameter
    nc = (mu_1**2 / sigma_1_sq) + (mu_2**2 / sigma_2_sq)

    # Equivalent radius squared scaled by variance
    u = hard_body_radius**2 / (2.0 * np.sqrt(sigma_1_sq * sigma_2_sq))

    # Use direct series expansion for Pc
    # Pc = exp(-nc/2) * sum_{k=0}^{inf} (nc/2)^k / k! * (1 - exp(-u) * sum_{j=0}^{k} u^j/j!)
    max_terms = 200
    pc = 0.0
    nc_half = nc / 2.0

    # Precompute exp(-u)
    exp_neg_u = np.exp(-u)

    # Compute terms using recurrence for stability
    poisson_term = np.exp(-nc_half)  # (nc/2)^k / k! * exp(-nc/2)
    inner_sum = 1.0  # sum_{j=0}^{k} u^j / j!, starts at k=0 with value 1

    for k in range(max_terms):
        if k > 0:
            poisson_term *= nc_half / k
            inner_sum += (u**k) / _factorial(k)

        incomplete_gamma_part = 1.0 - exp_neg_u * inner_sum
        pc += poisson_term * incomplete_gamma_part

        # Convergence check
        if k > 5 and abs(poisson_term) < 1e-16:
            break

    return float(np.clip(pc, 0.0, 1.0))


def _factorial(n: int) -> float:
    """Compute factorial using float to avoid overflow."""
    result = 1.0
    for i in range(2, n + 1):
        result *= i
    return result
