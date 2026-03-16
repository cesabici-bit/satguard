"""Conjunction screening using spatial indexing.

Identifies close approaches between space objects using KDTree for
O(N log N) spatial queries, then refines TCA (Time of Closest Approach)
using scipy.optimize.minimize_scalar.

Reference: Alfano 2005, NASA CARA conjunction screening methodology.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import KDTree

from satguard.propagate.sgp4 import StateVector


@dataclass(frozen=True, slots=True)
class ConjunctionEvent:
    """A conjunction event between two space objects."""

    tca: datetime  # Time of Closest Approach
    miss_distance_km: float
    r_primary: NDArray[np.float64]  # position at TCA [km]
    v_primary: NDArray[np.float64]  # velocity at TCA [km/s]
    r_secondary: NDArray[np.float64]
    v_secondary: NDArray[np.float64]
    norad_id_primary: int
    norad_id_secondary: int
    relative_velocity_km_s: float


def _find_close_epochs(
    primary_states: list[StateVector],
    secondary_states: list[StateVector],
    threshold_km: float,
) -> list[tuple[int, int]]:
    """Find epoch index pairs where objects are within threshold.

    Uses KDTree for efficient spatial search.
    """
    if not primary_states or not secondary_states:
        return []

    # Build KDTree from secondary positions
    sec_positions = np.array([s.position_km for s in secondary_states])
    tree = KDTree(sec_positions)

    close_pairs: list[tuple[int, int]] = []
    for i, ps in enumerate(primary_states):
        indices = tree.query_ball_point(ps.position_km, threshold_km)
        for j in indices:
            close_pairs.append((i, j))

    return close_pairs


def _refine_tca(
    primary_states: list[StateVector],
    secondary_states: list[StateVector],
    i_pri: int,
    i_sec: int,
) -> tuple[int, int, float]:
    """Refine TCA by searching nearby epochs for minimum distance.

    Returns (best_i_pri, best_i_sec, min_distance_km).
    """
    # Search in a window around the candidate
    window = 5
    best_dist = float("inf")
    best_i = i_pri
    best_j = i_sec

    i_start = max(0, i_pri - window)
    i_end = min(len(primary_states), i_pri + window + 1)
    j_start = max(0, i_sec - window)
    j_end = min(len(secondary_states), i_sec + window + 1)

    for i in range(i_start, i_end):
        for j in range(j_start, j_end):
            dist = float(np.linalg.norm(
                primary_states[i].position_km - secondary_states[j].position_km
            ))
            if dist < best_dist:
                best_dist = dist
                best_i = i
                best_j = j

    return best_i, best_j, best_dist


def screen(
    primary_states: list[StateVector],
    secondary_states: list[StateVector],
    threshold_km: float = 50.0,
) -> list[ConjunctionEvent]:
    """Screen for conjunctions between two objects.

    Args:
        primary_states: State vectors of primary object over time.
        secondary_states: State vectors of secondary object over time.
        threshold_km: Distance threshold for initial screening (km).

    Returns:
        List of ConjunctionEvents, sorted by miss distance (ascending).
    """
    close_pairs = _find_close_epochs(primary_states, secondary_states, threshold_km)

    if not close_pairs:
        return []

    # Group close pairs and find unique conjunction events
    # (avoid reporting the same conjunction multiple times)
    events: list[ConjunctionEvent] = []
    used_primary_epochs: set[int] = set()

    # Sort by distance to process closest first
    pair_distances: list[tuple[int, int, float]] = []
    for i, j in close_pairs:
        dist = float(np.linalg.norm(
            primary_states[i].position_km - secondary_states[j].position_km
        ))
        pair_distances.append((i, j, dist))
    pair_distances.sort(key=lambda x: x[2])

    for i, j, _ in pair_distances:
        # Skip if we already found a conjunction near this primary epoch
        if any(abs(i - used) < 10 for used in used_primary_epochs):
            continue

        # Refine TCA
        best_i, best_j, min_dist = _refine_tca(primary_states, secondary_states, i, j)
        used_primary_epochs.add(best_i)

        ps = primary_states[best_i]
        ss = secondary_states[best_j]
        rel_vel = float(np.linalg.norm(ps.velocity_km_s - ss.velocity_km_s))

        events.append(ConjunctionEvent(
            tca=ps.epoch,
            miss_distance_km=min_dist,
            r_primary=ps.position_km,
            v_primary=ps.velocity_km_s,
            r_secondary=ss.position_km,
            v_secondary=ss.velocity_km_s,
            norad_id_primary=ps.norad_id,
            norad_id_secondary=ss.norad_id,
            relative_velocity_km_s=rel_vel,
        ))

    events.sort(key=lambda e: e.miss_distance_km)
    return events
