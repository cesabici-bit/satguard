"""SGP4 propagation wrapper.

Wraps the sgp4 library to propagate TLE orbits and produce state vectors.
Reference: Vallado 5th Ed, Chapter 11 — SGP4 theory and implementation.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from numpy.typing import NDArray
from sgp4.api import WGS72, Satrec

from satguard.catalog.tle import TLE


@dataclass(frozen=True, slots=True)
class StateVector:
    """Satellite state vector in TEME frame."""

    epoch: datetime
    position_km: NDArray[np.float64]  # [x, y, z] km
    velocity_km_s: NDArray[np.float64]  # [vx, vy, vz] km/s
    norad_id: int

    @property
    def altitude_km(self) -> float:
        """Approximate altitude above Earth's surface (spherical Earth, Re=6378.137 km)."""
        return float(np.linalg.norm(self.position_km)) - 6378.137


def _tle_to_satrec(tle: TLE) -> Satrec:
    """Convert a parsed TLE to sgp4 Satrec object."""
    return Satrec.twoline2rv(tle.line1, tle.line2, WGS72)


def _jd_from_datetime(dt: datetime) -> tuple[float, float]:
    """Convert datetime to Julian date (jd, fr) pair for sgp4.

    Uses the standard astronomical formula.
    jd = integer part, fr = fractional part (for precision).
    """
    # Julian date algorithm from Meeus, "Astronomical Algorithms"
    y = dt.year
    m = dt.month
    d = dt.day
    if m <= 2:
        y -= 1
        m += 12
    A = y // 100
    B = 2 - A + A // 4
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + B - 1524.5
    fr = (dt.hour + dt.minute / 60.0 + dt.second / 3600.0 + dt.microsecond / 3.6e9) / 24.0
    return jd, fr


def propagate_single(tle: TLE, epoch: datetime) -> StateVector:
    """Propagate a TLE to a single epoch.

    Args:
        tle: Parsed TLE.
        epoch: Target datetime (UTC).

    Returns:
        StateVector in TEME frame.

    Raises:
        RuntimeError: If SGP4 returns an error code.
    """
    sat = _tle_to_satrec(tle)
    jd, fr = _jd_from_datetime(epoch)
    error, position, velocity = sat.sgp4(jd, fr)
    if error != 0:
        raise RuntimeError(f"SGP4 error code {error} for NORAD {tle.norad_id} at {epoch}")
    return StateVector(
        epoch=epoch,
        position_km=np.array(position, dtype=np.float64),
        velocity_km_s=np.array(velocity, dtype=np.float64),
        norad_id=tle.norad_id,
    )


def propagate_batch(
    tle: TLE,
    days: float = 3.0,
    step_seconds: float = 60.0,
    start: datetime | None = None,
) -> list[StateVector]:
    """Propagate a TLE over a time span at fixed steps.

    Args:
        tle: Parsed TLE.
        days: Duration of propagation window in days.
        step_seconds: Time step in seconds.
        start: Start datetime (defaults to TLE epoch).

    Returns:
        List of StateVectors.
    """
    if days > 7.0:
        warnings.warn(
            f"SGP4 accuracy degrades significantly beyond 3-7 days (requested {days}d). "
            "Results should be used with caution.",
            stacklevel=2,
        )

    if start is None:
        start = tle.epoch_datetime

    sat = _tle_to_satrec(tle)
    n_steps = int(days * 86400.0 / step_seconds) + 1
    states: list[StateVector] = []

    for i in range(n_steps):
        dt = start + timedelta(seconds=i * step_seconds)
        jd, fr = _jd_from_datetime(dt)
        error, position, velocity = sat.sgp4(jd, fr)
        if error != 0:
            continue  # Skip errored epochs rather than failing entire batch
        states.append(StateVector(
            epoch=dt,
            position_km=np.array(position, dtype=np.float64),
            velocity_km_s=np.array(velocity, dtype=np.float64),
            norad_id=tle.norad_id,
        ))

    return states
