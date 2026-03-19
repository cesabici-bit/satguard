"""Batch conjunction screening for fleet objects.

Screens fleet objects against the full active catalog using vectorized
SatrecArray propagation (v0.5.1). See screen.vectorized for the core
algorithm.
"""

from __future__ import annotations

import logging

from satguard.assess.foster import foster_pc
from satguard.catalog.celestrak import Catalog, fetch_catalog
from satguard.covariance.realism import default_covariance, project_to_encounter_plane
from satguard.fleet.parser import FleetConfig
from satguard.screen.screener import ConjunctionEvent
from satguard.screen.vectorized import ScoredConjunction, VectorizedConfig, vectorized_screen

logger = logging.getLogger("satguard.fleet")


async def screen_fleet(
    fleet: FleetConfig,
    catalog: Catalog | None = None,
    on_progress: None | object = None,
) -> list[ScoredConjunction]:
    """Screen all fleet objects against the active catalog.

    Uses vectorized SatrecArray propagation for the entire catalog at once,
    then filters to only conjunctions involving fleet objects.

    Args:
        fleet: Parsed fleet configuration.
        catalog: Pre-fetched catalog (fetched if None).
        on_progress: Unused, reserved for future callback.

    Returns:
        List of ScoredConjunction, sorted by Pc descending.
    """
    if catalog is None:
        logger.info("Fetching active catalog...")
        catalog = await fetch_catalog("active")
    logger.info("Catalog: %d objects", len(catalog))

    config = VectorizedConfig(
        threshold_km=fleet.thresholds.miss_km,
        step_seconds=120.0,
        days=float(fleet.thresholds.days),
        max_results=500,
        pc_threshold=fleet.thresholds.pc,
    )

    fleet_ids = set(fleet.objects)

    results = vectorized_screen(
        tles=catalog.tles,
        config=config,
        primary_ids=fleet_ids,
    )

    logger.info("Fleet screening complete: %d conjunctions", len(results))
    return results


def _pair_key(a: int, b: int) -> tuple[int, int]:
    """Canonical pair key (smaller ID first)."""
    return (min(a, b), max(a, b))


def _score_event(event: ConjunctionEvent) -> ScoredConjunction | None:
    """Compute Pc for a conjunction event. Returns None on failure."""
    try:
        cov_p = default_covariance("LEO")
        cov_s = default_covariance("LEO")
        cov_2d = project_to_encounter_plane(
            cov_p, cov_s,
            event.r_primary, event.v_primary,
            event.r_secondary, event.v_secondary,
        )
        pc = foster_pc(event.miss_distance_km, cov_2d, hard_body_radius=0.02)
        return ScoredConjunction(event=event, pc=pc)
    except Exception:
        return None
