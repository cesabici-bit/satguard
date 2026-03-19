"""Batch conjunction screening for fleet objects.

Screens each fleet object against the full active catalog,
deduplicates by pair, and computes collision probability.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass

from satguard.assess.foster import foster_pc
from satguard.catalog.celestrak import Catalog, fetch_catalog, fetch_tle_by_norad
from satguard.catalog.tle import TLE
from satguard.covariance.realism import default_covariance, project_to_encounter_plane
from satguard.fleet.parser import FleetConfig
from satguard.propagate.sgp4 import propagate_batch
from satguard.screen.screener import ConjunctionEvent, screen

logger = logging.getLogger("satguard.fleet")


@dataclass(frozen=True, slots=True)
class ScoredConjunction:
    """A conjunction event with computed collision probability."""

    event: ConjunctionEvent
    pc: float
    """Collision probability (Foster 1992)."""


async def screen_fleet(
    fleet: FleetConfig,
    catalog: Catalog | None = None,
    on_progress: None | object = None,
) -> list[ScoredConjunction]:
    """Screen all fleet objects against the active catalog.

    For each fleet object:
        1. Fetch TLE (or use catalog entry)
        2. Propagate over screening window
        3. Screen against all catalog objects
        4. Compute Pc for each conjunction

    Results are deduplicated by pair (keep minimum miss distance),
    filtered by fleet thresholds, and sorted by Pc descending.

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

    fleet_set = set(fleet.objects)
    threshold_km = fleet.thresholds.miss_km
    days = fleet.thresholds.days
    step_seconds = 60.0

    # Collect all conjunctions across fleet objects
    pair_best: dict[tuple[int, int], ScoredConjunction] = {}

    for norad_id in fleet.objects:
        logger.info("Screening fleet object NORAD %d...", norad_id)

        # Get primary TLE
        primary_tle = _find_tle_in_catalog(catalog, norad_id)
        if primary_tle is None:
            try:
                primary_tle = await fetch_tle_by_norad(norad_id)
            except Exception:
                logger.warning("Could not fetch TLE for NORAD %d, skipping", norad_id)
                continue

        primary_states = propagate_batch(
            primary_tle, days=float(days), step_seconds=step_seconds,
        )
        if not primary_states:
            logger.warning("No states for NORAD %d, skipping", norad_id)
            continue

        start_epoch = primary_tle.epoch_datetime

        # Screen against each catalog object
        for tle in catalog:
            if tle.norad_id == norad_id:
                continue
            # Skip fleet-vs-fleet (will be screened from the other side)
            if tle.norad_id in fleet_set and tle.norad_id < norad_id:
                continue

            try:
                sec_states = propagate_batch(
                    tle, days=float(days), step_seconds=step_seconds,
                    start=start_epoch,
                )
                events = screen(primary_states, sec_states, threshold_km=threshold_km)
            except Exception:
                continue

            for event in events:
                scored = _score_event(event)
                if scored is None:
                    continue

                # Filter by Pc threshold
                if scored.pc < fleet.thresholds.pc:
                    continue

                # Deduplicate: keep the conjunction with highest Pc for each pair
                pair_key = _pair_key(event.norad_id_primary, event.norad_id_secondary)
                existing = pair_best.get(pair_key)
                if existing is None or scored.pc > existing.pc:
                    pair_best[pair_key] = scored

    results = sorted(pair_best.values(), key=lambda s: s.pc, reverse=True)
    logger.info("Fleet screening complete: %d conjunctions", len(results))
    return results


def _find_tle_in_catalog(catalog: Catalog, norad_id: int) -> TLE | None:
    """Look up a NORAD ID in the catalog."""
    with contextlib.suppress(Exception):
        return catalog.get_by_norad(norad_id)
    return None


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
