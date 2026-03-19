"""Historical replay of conjunction evolution from archived TLE snapshots.

Re-propagates archived TLEs from each PcSnapshot to reconstruct how the
conjunction geometry evolved over time.

v0.6: Requires PcSnapshot with tle_line* fields populated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from satguard.assess.foster import foster_pc
from satguard.catalog.tle import parse_tle_lines
from satguard.covariance.realism import default_covariance, project_to_encounter_plane
from satguard.history.store import ConjunctionHistory, PcSnapshot
from satguard.propagate.sgp4 import propagate_single


@dataclass(frozen=True, slots=True)
class ReplayPoint:
    """Single point in a replayed conjunction timeline."""

    timestamp: datetime
    """When this assessment was taken."""

    tca: datetime
    """Time of closest approach at this snapshot."""

    miss_km: float
    """Recomputed miss distance [km]."""

    pc: float
    """Recomputed collision probability (Foster)."""

    tle_age_primary_h: float
    """Age of primary TLE at TCA [hours]."""

    tle_age_secondary_h: float
    """Age of secondary TLE at TCA [hours]."""

    stored_miss_km: float
    """Originally stored miss distance for comparison."""

    stored_pc: float
    """Originally stored Pc for comparison."""


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Complete replay of a conjunction's history."""

    norad_a: int
    norad_b: int
    timeline: tuple[ReplayPoint, ...]
    peak_pc: float
    """Maximum Pc across all replay points."""

    final_pc: float
    """Pc from the most recent replay point."""


def _snapshot_has_tles(snap: PcSnapshot) -> bool:
    """Check if a snapshot has all 4 TLE lines archived."""
    return all([
        snap.tle_line1_primary,
        snap.tle_line2_primary,
        snap.tle_line1_secondary,
        snap.tle_line2_secondary,
    ])


def replay_conjunction(
    history: ConjunctionHistory,
    hard_body_radius: float = 0.02,
) -> ReplayResult:
    """Replay a conjunction history by re-propagating archived TLEs.

    For each snapshot that has archived TLE lines:
    1. Parse the TLEs
    2. Propagate both objects to the stored TCA
    3. Compute miss distance and Pc

    Args:
        history: ConjunctionHistory with snapshots (some may lack TLE data).
        hard_body_radius: Combined hard-body radius [km].

    Returns:
        ReplayResult with timeline of recomputed values.
    """
    points: list[ReplayPoint] = []

    for snap in history.snapshots:
        if not _snapshot_has_tles(snap):
            continue

        try:
            # Parse archived TLEs
            tle_primary = parse_tle_lines(
                f"PRIMARY-{history.norad_id_a}",
                snap.tle_line1_primary,  # type: ignore[arg-type]
                snap.tle_line2_primary,  # type: ignore[arg-type]
            )
            tle_secondary = parse_tle_lines(
                f"SECONDARY-{history.norad_id_b}",
                snap.tle_line1_secondary,  # type: ignore[arg-type]
                snap.tle_line2_secondary,  # type: ignore[arg-type]
            )

            # Propagate both to TCA
            state_p = propagate_single(tle_primary, snap.tca)
            state_s = propagate_single(tle_secondary, snap.tca)

            # Compute miss distance
            miss_vec = state_p.position_km - state_s.position_km
            miss_km = float(np.linalg.norm(miss_vec))

            # Compute Pc
            cov_p = default_covariance("LEO")
            cov_s = default_covariance("LEO")
            cov_2d = project_to_encounter_plane(
                cov_p, cov_s,
                state_p.position_km, state_p.velocity_km_s,
                state_s.position_km, state_s.velocity_km_s,
            )
            pc = foster_pc(miss_km, cov_2d, hard_body_radius=hard_body_radius)

            # TLE ages
            age_p_h = (snap.tca - tle_primary.epoch_datetime).total_seconds() / 3600.0
            age_s_h = (snap.tca - tle_secondary.epoch_datetime).total_seconds() / 3600.0

            points.append(ReplayPoint(
                timestamp=snap.timestamp,
                tca=snap.tca,
                miss_km=miss_km,
                pc=pc,
                tle_age_primary_h=age_p_h,
                tle_age_secondary_h=age_s_h,
                stored_miss_km=snap.miss_distance_km,
                stored_pc=snap.pc_foster,
            ))
        except Exception:
            # Skip snapshots that fail to replay (TLE propagation errors, etc.)
            continue

    peak_pc = max((p.pc for p in points), default=0.0)
    final_pc = points[-1].pc if points else 0.0

    return ReplayResult(
        norad_a=history.norad_id_a,
        norad_b=history.norad_id_b,
        timeline=tuple(points),
        peak_pc=peak_pc,
        final_pc=final_pc,
    )
