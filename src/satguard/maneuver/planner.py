"""Maneuver planner: tradespace search for collision avoidance maneuvers.

Given a conjunction event, searches a grid of (burn_time, delta_v) to find
the minimum Δv that reduces Pc below the threshold.

Reference:
  NASA CARA operational CAM delta-v range: 0.05–1.0 m/s (typical LEO).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from satguard.assess.foster import foster_pc
from satguard.covariance.realism import (
    default_covariance,
    eci_to_rtn,
    project_to_encounter_plane,
)
from satguard.maneuver.cw import (
    CWDisplacement,
    ManeuverBurn,
    cw_displacement,
    eccentricity_from_state,
    orbital_period,
    sma_from_position,
)
from satguard.screen.screener import ConjunctionEvent


@dataclass(frozen=True, slots=True)
class ManeuverOption:
    """A single point in the maneuver tradespace."""

    burn: ManeuverBurn
    displacement: CWDisplacement
    post_miss_km: float
    post_pc: float
    original_miss_km: float
    original_pc: float


@dataclass(frozen=True, slots=True)
class ManeuverRecommendation:
    """Result of maneuver planning for a conjunction event."""

    event: ConjunctionEvent
    original_pc: float
    threshold: float
    options: tuple[ManeuverOption, ...]
    recommended: ManeuverOption | None
    """Minimum-Δv option that meets the threshold, or None if none found."""

    action_required: bool
    """True if original Pc exceeds threshold."""


def _compute_post_maneuver_miss(
    event: ConjunctionEvent,
    displacement: CWDisplacement,
) -> float:
    """Compute the post-maneuver miss distance.

    Projects the CW displacement onto the encounter plane and adds it
    to the original miss vector.

    Args:
        event: Original conjunction event.
        displacement: CW displacement from the maneuver.

    Returns:
        Post-maneuver miss distance in km.
    """
    # Get RTN rotation for the primary object at TCA
    rot = eci_to_rtn(event.r_primary, event.v_primary)

    # CW displacement is in RTN frame: [radial, in-track, normal]
    d_rtn = np.array([displacement.dz_radial_km, displacement.dx_intrack_km, 0.0])

    # Convert to ECI
    d_eci = rot.T @ d_rtn

    # New miss vector = original miss + displacement
    original_miss = event.r_primary - event.r_secondary
    new_miss = original_miss + d_eci

    return float(np.linalg.norm(new_miss))


def _compute_pc(
    miss_km: float,
    event: ConjunctionEvent,
    hard_body_radius: float = 0.02,
) -> float:
    """Compute Pc for a given miss distance using default covariance."""
    cov_p = default_covariance("LEO")
    cov_s = default_covariance("LEO")
    cov_2d = project_to_encounter_plane(
        cov_p, cov_s,
        event.r_primary, event.v_primary,
        event.r_secondary, event.v_secondary,
    )
    return foster_pc(miss_km, cov_2d, hard_body_radius=hard_body_radius)


class ManeuverPlanner:
    """Tradespace search for collision avoidance maneuvers.

    Searches a grid of (burn_time, delta_v) combinations to find
    the minimum delta-v that reduces Pc below the threshold.

    Attributes:
        dv_range_ms: (min, max) delta-v search range in m/s.
        dv_steps: Number of delta-v grid points.
        time_steps: Number of burn-time grid points.
        hard_body_radius: Combined hard-body radius in km.
    """

    def __init__(
        self,
        dv_range_ms: tuple[float, float] = (0.01, 1.0),
        dv_steps: int = 20,
        time_steps: int = 20,
        hard_body_radius: float = 0.02,
    ) -> None:
        self.dv_range_ms = dv_range_ms
        self.dv_steps = dv_steps
        self.time_steps = time_steps
        self.hard_body_radius = hard_body_radius

    def plan(
        self,
        event: ConjunctionEvent,
        threshold_pc: float = 1e-4,
        lead_time_hours: float | None = None,
    ) -> ManeuverRecommendation:
        """Plan a collision avoidance maneuver.

        Args:
            event: The conjunction event to mitigate.
            threshold_pc: Maximum acceptable Pc after maneuver.
            lead_time_hours: Maximum lead time in hours. Defaults to half
                the orbital period.

        Returns:
            ManeuverRecommendation with tradespace and recommended option.
        """
        # Compute semi-major axis and validate CW applicability
        sma = sma_from_position(event.r_primary, event.v_primary)
        ecc = eccentricity_from_state(event.r_primary, event.v_primary)
        assert ecc < 0.05, (
            f"CW equations require near-circular orbit (e < 0.05), got e={ecc:.4f}. "
            "Use numerical propagation for eccentric orbits."
        )

        period_s = orbital_period(sma)

        # Default lead time: half orbital period (maximum CW displacement)
        if lead_time_hours is None:
            max_lead_s = period_s / 2.0
        else:
            max_lead_s = lead_time_hours * 3600.0
            assert max_lead_s <= period_s, (
                f"Lead time {lead_time_hours:.1f}h exceeds orbital period "
                f"{period_s/3600:.1f}h — CW accuracy degrades"
            )

        # Compute original Pc
        original_pc = _compute_pc(event.miss_distance_km, event, self.hard_body_radius)

        if original_pc <= threshold_pc:
            return ManeuverRecommendation(
                event=event,
                original_pc=original_pc,
                threshold=threshold_pc,
                options=(),
                recommended=None,
                action_required=False,
            )

        # Build tradespace grid
        dv_values = np.linspace(
            self.dv_range_ms[0], self.dv_range_ms[1], self.dv_steps,
        )
        # Minimum lead time: 10 minutes (operational constraint)
        min_lead_s = 600.0
        time_values = np.linspace(min_lead_s, max_lead_s, self.time_steps)

        options: list[ManeuverOption] = []
        for dv in dv_values:
            for tau in time_values:
                burn = ManeuverBurn(
                    delta_v_ms=float(dv),
                    time_before_tca_s=float(tau),
                )
                disp = cw_displacement(burn, sma)
                post_miss = _compute_post_maneuver_miss(event, disp)
                post_pc = _compute_pc(post_miss, event, self.hard_body_radius)
                options.append(ManeuverOption(
                    burn=burn,
                    displacement=disp,
                    post_miss_km=post_miss,
                    post_pc=post_pc,
                    original_miss_km=event.miss_distance_km,
                    original_pc=original_pc,
                ))

        # Sort by delta-v (ascending) to find minimum fuel solution
        options.sort(key=lambda o: o.burn.delta_v_ms)

        # Find minimum Δv that meets threshold
        recommended = None
        for opt in options:
            if opt.post_pc <= threshold_pc:
                recommended = opt
                break

        return ManeuverRecommendation(
            event=event,
            original_pc=original_pc,
            threshold=threshold_pc,
            options=tuple(options),
            recommended=recommended,
            action_required=True,
        )
