"""Clohessy-Wiltshire (CW) linearized relative motion equations.

Computes the displacement at TCA caused by an impulsive in-track burn
at time τ before TCA for a circular reference orbit.

Reference:
  Curtis, H. "Orbital Mechanics for Engineering Students", 4th Ed, Ch.7
  Clohessy & Wiltshire (1960), "Terminal Guidance System for Satellite Rendezvous"

Validity: quasi-circular orbits (e < 0.05), burn-to-TCA < 1 orbital period.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Earth gravitational parameter [km³/s²]
MU_EARTH = 398600.4418


@dataclass(frozen=True, slots=True)
class ManeuverBurn:
    """An impulsive in-track burn."""

    delta_v_ms: float
    """Delta-v magnitude in m/s (positive = along-track prograde)."""

    time_before_tca_s: float
    """Time before TCA at which the burn is performed [seconds]."""

    direction: str = "in-track"
    """Burn direction (currently only 'in-track' supported)."""


@dataclass(frozen=True, slots=True)
class CWDisplacement:
    """Displacement at TCA resulting from a CW maneuver."""

    dx_intrack_km: float
    """Along-track (in-track) displacement at TCA [km]."""

    dz_radial_km: float
    """Radial displacement at TCA [km]."""

    @property
    def magnitude_km(self) -> float:
        """Total displacement magnitude [km]."""
        return math.sqrt(self.dx_intrack_km**2 + self.dz_radial_km**2)


def mean_motion(semi_major_axis_km: float) -> float:
    """Compute mean motion n = sqrt(μ/a³) in rad/s.

    Args:
        semi_major_axis_km: Semi-major axis in km. Must be > 0.

    Returns:
        Mean motion in rad/s.
    """
    assert semi_major_axis_km > 0, f"SMA must be positive, got {semi_major_axis_km}"
    return math.sqrt(MU_EARTH / semi_major_axis_km**3)


def orbital_period(semi_major_axis_km: float) -> float:
    """Compute orbital period T = 2π/n in seconds.

    Args:
        semi_major_axis_km: Semi-major axis in km.

    Returns:
        Orbital period in seconds.
    """
    n = mean_motion(semi_major_axis_km)
    return 2.0 * math.pi / n


def cw_displacement(
    burn: ManeuverBurn,
    semi_major_axis_km: float,
) -> CWDisplacement:
    """Compute CW displacement at TCA from an impulsive in-track burn.

    The CW equations for an in-track impulse Δv applied at time τ before TCA:
        Δx_intrack = Δv × (4/n × sin(n×τ) - 3τ)
        Δz_radial  = Δv × (2/n × (1 - cos(n×τ)))

    Reference: Curtis Ch.7, CW linearized equations for circular orbits.

    Args:
        burn: ManeuverBurn with delta-v [m/s] and time before TCA [s].
        semi_major_axis_km: Semi-major axis of the reference orbit [km].

    Returns:
        CWDisplacement with in-track and radial components [km].
    """
    assert burn.direction == "in-track", f"Only in-track burns supported, got '{burn.direction}'"
    assert burn.time_before_tca_s >= 0, (
        f"Time before TCA must be >= 0, got {burn.time_before_tca_s}"
    )

    n = mean_motion(semi_major_axis_km)
    tau = burn.time_before_tca_s
    # Convert m/s to km/s for consistent units
    dv_km_s = burn.delta_v_ms / 1000.0

    nt = n * tau
    dx = dv_km_s * (4.0 / n * math.sin(nt) - 3.0 * tau)
    dz = dv_km_s * (2.0 / n * (1.0 - math.cos(nt)))

    return CWDisplacement(dx_intrack_km=dx, dz_radial_km=dz)


def sma_from_position(r_km: np.ndarray, v_km_s: np.ndarray) -> float:
    """Compute semi-major axis from state vector using vis-viva.

    a = -μ / (2ε)  where ε = v²/2 - μ/r

    Args:
        r_km: Position vector [km].
        v_km_s: Velocity vector [km/s].

    Returns:
        Semi-major axis in km.
    """
    r = float(np.linalg.norm(r_km))
    v = float(np.linalg.norm(v_km_s))
    energy = v**2 / 2.0 - MU_EARTH / r
    assert energy < 0, f"Hyperbolic orbit (energy={energy:.3f}), CW not applicable"
    return -MU_EARTH / (2.0 * energy)


def eccentricity_from_state(r_km: np.ndarray, v_km_s: np.ndarray) -> float:
    """Compute eccentricity from state vector.

    Args:
        r_km: Position vector [km].
        v_km_s: Velocity vector [km/s].

    Returns:
        Orbital eccentricity (dimensionless).
    """
    r = float(np.linalg.norm(r_km))
    # Specific angular momentum
    h = np.cross(r_km, v_km_s)
    # Eccentricity vector
    e_vec = (np.cross(v_km_s, h) / MU_EARTH) - (r_km / r)
    return float(np.linalg.norm(e_vec))
