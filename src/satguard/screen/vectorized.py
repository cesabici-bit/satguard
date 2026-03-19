"""Vectorized conjunction screening using SatrecArray + KDTree.

Propagates ALL catalog objects at once via sgp4's SatrecArray (C-level
vectorized), then uses KDTree at each time step to find close pairs.
This is orders of magnitude faster than sequential pairwise screening.

Used by both ``fleet.batch`` (fleet-vs-catalog) and ``api.app`` (all-on-all).

Reference:
    - EC-002 in KNOWN_ISSUES.md: fine time-stepping (≤120s) is required for
      LEO screening; sparse snapshots miss high-speed crossings.
    - EC-001: sibling + co-orbiting filtering is mandatory.
"""

from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import KDTree as KDTreeScipy
from sgp4.api import WGS72, Satrec, SatrecArray

from satguard.assess.foster import foster_pc
from satguard.catalog.tle import TLE
from satguard.covariance.realism import default_covariance, project_to_encounter_plane
from satguard.propagate.sgp4 import _jd_from_datetime
from satguard.screen.screener import ConjunctionEvent

logger = logging.getLogger("satguard.screen.vectorized")


@dataclass(frozen=True, slots=True)
class VectorizedConfig:
    """Configuration for vectorized screening."""

    threshold_km: float = 25.0
    step_seconds: float = 120.0
    days: float = 3.0
    max_results: int = 50
    min_relative_velocity: float = 0.5
    """Filter co-orbiting objects (km/s)."""
    min_miss_distance: float = 0.01
    """Filter co-located objects (km)."""
    tca_refine_window: int = 10
    """Half-window (in steps) for TCA refinement."""
    pc_threshold: float = 0.0
    """Minimum Pc to include in results."""


def _classify_orbit(mean_motion: float) -> str:
    """Classify orbit type from mean motion (rev/day)."""
    if mean_motion > 11.25:
        return "LEO"
    elif 1.8 <= mean_motion <= 2.2:
        return "MEO"
    elif 0.9 <= mean_motion <= 1.1:
        return "GEO"
    return "OTHER"


@dataclass(frozen=True, slots=True)
class ScoredConjunction:
    """A conjunction event with collision probability."""

    event: ConjunctionEvent
    pc: float
    """Collision probability (Foster 1992)."""


def vectorized_screen(
    tles: list[TLE],
    config: VectorizedConfig | None = None,
    primary_ids: set[int] | None = None,
) -> list[ScoredConjunction]:
    """Vectorized all-on-all (or fleet-vs-all) conjunction screening.

    Args:
        tles: Full catalog TLE list.
        config: Screening parameters (uses defaults if None).
        primary_ids: If provided, only return conjunctions where at least
            one object is in this set. If None, return all conjunctions
            (all-on-all mode).

    Returns:
        List of ScoredConjunction sorted by Pc descending.
    """
    if config is None:
        config = VectorizedConfig()

    # --- Pre-filter by orbital altitude (fleet mode only) ---
    # If primary_ids given, only propagate objects whose apogee/perigee bands
    # overlap with the fleet objects' bands (± threshold margin).
    # This can reduce 14K objects to ~2-4K, cutting propagation time by ~75%.
    if primary_ids is not None:
        tles = _altitude_prefilter(tles, primary_ids, config.threshold_km)

    # --- Build SatrecArray from TLEs ---
    satrecs: list[Satrec] = []
    valid_tles: list[TLE] = []
    norad_ids: list[int] = []
    mean_motions: list[float] = []
    launch_prefix: dict[int, str] = {}

    for tle in tles:
        try:
            sat = Satrec.twoline2rv(tle.line1, tle.line2, WGS72)
            if sat.error != 0:
                continue
            satrecs.append(sat)
            valid_tles.append(tle)
            norad_ids.append(tle.norad_id)
            mean_motions.append(tle.mean_motion)
            launch_prefix[tle.norad_id] = (
                tle.intl_designator[:5] if tle.intl_designator else ""
            )
        except Exception:
            continue

    n_sats = len(satrecs)
    if n_sats < 2:
        return []

    logger.info("Propagating %d objects with SatrecArray...", n_sats)

    # --- Build epoch array ---
    start_epoch = datetime.now(UTC)
    n_steps = int(config.days * 86400 / config.step_seconds) + 1

    jd_arr = np.empty(n_steps)
    fr_arr = np.empty(n_steps)
    epoch_dts: list[datetime] = []
    for i in range(n_steps):
        t = start_epoch + timedelta(seconds=i * config.step_seconds)
        jd, fr = _jd_from_datetime(t)
        jd_arr[i] = jd
        fr_arr[i] = fr
        epoch_dts.append(t)

    # --- Vectorized propagation ---
    _t0 = _time.perf_counter()
    sat_array = SatrecArray(satrecs)
    errors, positions, velocities = sat_array.sgp4(jd_arr, fr_arr)
    # positions: (n_sats, n_steps, 3) km
    # velocities: (n_sats, n_steps, 3) km/s
    _t_prop = _time.perf_counter() - _t0

    valid_mask = errors == 0  # (n_sats, n_steps)

    logger.info("Propagation done (%.1fs). Screening %d steps...", _t_prop, n_steps)

    # Build primary index set (global indices into satrecs) for fleet filtering
    primary_idx_set: set[int] | None = None
    if primary_ids is not None:
        primary_idx_set = {
            i for i, nid in enumerate(norad_ids) if nid in primary_ids
        }

    # --- Screening per time step ---
    pair_best: dict[tuple[int, int], tuple[float, int, int, int]] = {}

    if primary_idx_set is not None:
        # Fleet mode: fully vectorized across ALL steps, NO KDTree, NO step loop.
        # For each fleet object, compute distance to all catalog objects at all
        # steps in one NumPy broadcast, then find minimum per catalog object.
        primary_list = sorted(primary_idx_set)

        for gi in primary_list:
            # fleet_pos: (n_steps, 3), all_pos: (n_sats, n_steps, 3)
            fleet_pos = positions[gi, :, :]  # (n_steps, 3)

            # Validity: both fleet object and catalog object must have error=0
            fleet_valid = errors[gi, :] == 0  # (n_steps,)
            both_valid = valid_mask & fleet_valid[np.newaxis, :]  # (n_sats, n_steps)

            # Distance: broadcast (n_sats, n_steps, 3)
            diffs = positions - fleet_pos[np.newaxis, :, :]
            dists = np.linalg.norm(diffs, axis=2)  # (n_sats, n_steps)

            # Mask invalid steps with inf so they're never the minimum
            dists[~both_valid] = np.inf
            # Mask non-finite positions
            non_finite = ~np.all(np.isfinite(positions), axis=2)  # (n_sats, n_steps)
            fleet_non_finite = ~np.all(np.isfinite(fleet_pos), axis=1)  # (n_steps,)
            dists[non_finite] = np.inf
            dists[:, fleet_non_finite] = np.inf
            # Mask self
            dists[gi, :] = np.inf

            # Find minimum distance per catalog object across all steps
            min_step_per_obj = np.argmin(dists, axis=1)  # (n_sats,)
            min_dist_per_obj = dists[np.arange(n_sats), min_step_per_obj]  # (n_sats,)

            # Filter by threshold
            close_idxs = np.where(min_dist_per_obj < config.threshold_km)[0]

            for gj in close_idxs:
                gj = int(gj)
                nid_a = norad_ids[gi]
                nid_b = norad_ids[gj]

                # Skip same-launch siblings
                lp_a = launch_prefix.get(nid_a, "")
                lp_b = launch_prefix.get(nid_b, "")
                if lp_a and lp_b and lp_a == lp_b:
                    continue

                dist = float(min_dist_per_obj[gj])
                step = int(min_step_per_obj[gj])
                pair_key = (min(nid_a, nid_b), max(nid_a, nid_b))
                if pair_key not in pair_best or dist < pair_best[pair_key][0]:
                    pair_best[pair_key] = (dist, step, gi, gj)
    else:
        # All-on-all mode: KDTree query_pairs → O(N log N) amortized per step
        for step in range(n_steps):
            step_valid = valid_mask[:, step]
            n_valid = int(np.sum(step_valid))
            if n_valid < 2:
                continue

            valid_indices = np.where(step_valid)[0]
            pos_step = positions[valid_indices, step, :]

            # Filter NaN
            finite_mask = np.all(np.isfinite(pos_step), axis=1)
            if not np.all(finite_mask):
                valid_indices = valid_indices[finite_mask]
                pos_step = pos_step[finite_mask]
                if len(valid_indices) < 2:
                    continue

            tree = KDTreeScipy(pos_step)
            raw_pairs = tree.query_pairs(config.threshold_km)

            for li, ri in raw_pairs:
                gi = int(valid_indices[li])
                gj = int(valid_indices[ri])
                _record_pair(
                    gi, gj, li, ri, pos_step, norad_ids,
                    launch_prefix, pair_best, step,
                )

    _t_screen = _time.perf_counter() - _t0 - _t_prop
    logger.info(
        "Found %d unique candidate pairs (screen: %.1fs)",
        len(pair_best), _t_screen,
    )

    # --- Refine TCA and compute Pc for top candidates ---
    candidates: list[tuple[float, int, int, int]] = sorted(
        pair_best.values(), key=lambda x: x[0],
    )[: config.max_results * 4]

    results: list[ScoredConjunction] = []

    for dist, step, gi, gj in candidates:
        best_dist = dist
        best_step = step
        s_start = max(0, step - config.tca_refine_window)
        s_end = min(n_steps, step + config.tca_refine_window + 1)

        for s in range(s_start, s_end):
            if errors[gi, s] != 0 or errors[gj, s] != 0:
                continue
            p_a = positions[gi, s]
            p_b = positions[gj, s]
            if not (np.all(np.isfinite(p_a)) and np.all(np.isfinite(p_b))):
                continue
            d = float(np.linalg.norm(p_a - p_b))
            if d < best_dist:
                best_dist = d
                best_step = s

        # State vectors at refined TCA
        r_a = positions[gi, best_step]
        r_b = positions[gj, best_step]
        v_a = velocities[gi, best_step]
        v_b = velocities[gj, best_step]
        rel_vel = float(np.linalg.norm(v_a - v_b))

        # Filter co-orbiting / co-located
        if rel_vel < config.min_relative_velocity or best_dist < config.min_miss_distance:
            continue

        nid_a = norad_ids[gi]
        nid_b = norad_ids[gj]
        tca = epoch_dts[best_step]

        # Compute Pc
        pc = _compute_pc(
            r_a, v_a, r_b, v_b, best_dist,
            mean_motions[gi], mean_motions[gj],
        )
        if pc is None:
            continue

        if pc < config.pc_threshold:
            continue

        event = ConjunctionEvent(
            tca=tca,
            miss_distance_km=best_dist,
            r_primary=np.array(r_a, dtype=np.float64),
            v_primary=np.array(v_a, dtype=np.float64),
            r_secondary=np.array(r_b, dtype=np.float64),
            v_secondary=np.array(v_b, dtype=np.float64),
            norad_id_primary=nid_a,
            norad_id_secondary=nid_b,
            relative_velocity_km_s=rel_vel,
        )
        results.append(ScoredConjunction(event=event, pc=pc))

        if len(results) >= config.max_results:
            break

    results.sort(key=lambda s: s.pc, reverse=True)
    logger.info("Vectorized screening complete: %d conjunctions", len(results))
    return results


_EARTH_RADIUS_KM = 6378.137
_MU_EARTH = 398600.4418  # km^3/s^2


def _altitude_prefilter(
    tles: list[TLE],
    primary_ids: set[int],
    threshold_km: float,
) -> list[TLE]:
    """Pre-filter catalog to objects whose altitude bands overlap fleet objects.

    Uses TLE mean motion + eccentricity to compute apogee/perigee altitude.
    Keeps any object whose [perigee, apogee] band overlaps with any fleet
    object's band expanded by a generous margin (threshold + 200 km for
    SGP4 drift tolerance).

    Always includes fleet objects themselves.
    """
    import math

    margin_km = threshold_km + 200.0  # extra margin for SGP4 propagation drift

    # Compute altitude band for each TLE
    def _alt_band(tle: TLE) -> tuple[float, float]:
        n = tle.mean_motion  # rev/day
        e = tle.eccentricity
        if n <= 0:
            return (0.0, 100_000.0)
        n_rad_s = 2.0 * math.pi * n / 86400.0
        a_km = (_MU_EARTH / (n_rad_s**2)) ** (1.0 / 3.0)
        perigee = a_km * (1.0 - e) - _EARTH_RADIUS_KM
        apogee = a_km * (1.0 + e) - _EARTH_RADIUS_KM
        return (perigee, apogee)

    # Find fleet altitude range
    fleet_min = float("inf")
    fleet_max = float("-inf")
    for tle in tles:
        if tle.norad_id in primary_ids:
            peri, apo = _alt_band(tle)
            fleet_min = min(fleet_min, peri)
            fleet_max = max(fleet_max, apo)

    if fleet_min == float("inf"):
        return tles  # fleet objects not found, skip filter

    # Expand band by margin
    band_lo = fleet_min - margin_km
    band_hi = fleet_max + margin_km

    # Keep objects whose altitude bands overlap
    filtered = []
    for tle in tles:
        if tle.norad_id in primary_ids:
            filtered.append(tle)
            continue
        peri, apo = _alt_band(tle)
        # Overlap check: [peri, apo] ∩ [band_lo, band_hi] ≠ ∅
        if apo >= band_lo and peri <= band_hi:
            filtered.append(tle)

    logger.info(
        "Altitude pre-filter: %d → %d objects (fleet band: %.0f–%.0f km ± %.0f km margin)",
        len(tles), len(filtered), fleet_min, fleet_max, margin_km,
    )
    return filtered


def _record_pair(
    gi: int,
    gj: int,
    li: int,
    rj: int,
    pos_step: NDArray[np.float64],
    norad_ids: list[int],
    launch_prefix: dict[int, str],
    pair_best: dict[tuple[int, int], tuple[float, int, int, int]],
    step: int,
) -> None:
    """Record a candidate pair if it passes sibling filter and is closest so far."""
    nid_a = norad_ids[gi]
    nid_b = norad_ids[gj]

    # Skip same-launch siblings
    lp_a = launch_prefix.get(nid_a, "")
    lp_b = launch_prefix.get(nid_b, "")
    if lp_a and lp_b and lp_a == lp_b:
        return

    dist = float(np.linalg.norm(pos_step[li] - pos_step[rj]))
    pair_key = (min(nid_a, nid_b), max(nid_a, nid_b))

    if pair_key not in pair_best or dist < pair_best[pair_key][0]:
        pair_best[pair_key] = (dist, step, gi, gj)


def _compute_pc(
    r_a: NDArray[np.float64],
    v_a: NDArray[np.float64],
    r_b: NDArray[np.float64],
    v_b: NDArray[np.float64],
    miss_distance_km: float,
    mm_a: float,
    mm_b: float,
) -> float | None:
    """Compute collision probability. Returns None on failure."""
    try:
        orbit_a = _classify_orbit(mm_a)
        orbit_b = _classify_orbit(mm_b)
        cov_p = default_covariance(orbit_a)
        cov_s = default_covariance(orbit_b)
        cov_2d = project_to_encounter_plane(cov_p, cov_s, r_a, v_a, r_b, v_b)
        pc = foster_pc(miss_distance_km, cov_2d, hard_body_radius=0.02)
        if not (0.0 <= pc <= 1.0):
            logger.warning("Pc=%e out of [0,1] for miss=%.3f km", pc, miss_distance_km)
            return None
        return pc
    except Exception:
        return None
