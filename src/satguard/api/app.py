"""SatGuard FastAPI application.

Endpoints:
    GET /api/catalog        — Active satellite catalog (TLE strings + metadata)
    GET /api/conjunctions   — Top 50 conjunctions (all-on-all vectorized screening)
    GET /api/objects/{id}   — Object detail by NORAD ID
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from satguard.api.cache import cache

logger = logging.getLogger("satguard.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Pre-compute conjunctions in background at server startup."""
    task = asyncio.create_task(_precompute_conjunctions())
    yield
    task.cancel()


async def _precompute_conjunctions() -> None:
    """Background task: pre-compute conjunctions so the first request is instant."""
    try:
        logger.info("Background pre-compute: starting conjunction screening...")
        await _compute_conjunctions()
        logger.info("Background pre-compute: conjunctions ready.")
    except Exception:
        logger.exception("Background pre-compute failed — first request will compute on demand.")


app = FastAPI(title="SatGuard API", version="0.4.1", lifespan=lifespan)

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Constants
CATALOG_TTL = 3600  # 1 hour
CONJUNCTIONS_TTL = 3600  # 1 hour
EARTH_RADIUS_KM = 6371.0
MU_EARTH = 398600.4418  # km^3/s^2


def classify_orbit(mean_motion: float) -> str:
    """Classify orbit type from mean motion (rev/day).

    LEO: mean_motion > 11.25 (~2000 km alt)
    MEO: 1.8 < mean_motion < 2.2
    GEO: 0.9 < mean_motion < 1.1 (~35786 km alt)
    OTHER: everything else
    """
    if mean_motion > 11.25:
        return "LEO"
    elif 1.8 <= mean_motion <= 2.2:
        return "MEO"
    elif 0.9 <= mean_motion <= 1.1:
        return "GEO"
    return "OTHER"


def orbital_params_from_tle(tle: Any) -> dict[str, float]:
    """Compute derived orbital parameters from TLE elements.

    Returns period (min), apogee (km), perigee (km) above Earth surface.
    """
    n = tle.mean_motion  # rev/day
    e = tle.eccentricity

    # Period in minutes
    period_min = 1440.0 / n if n > 0 else 0.0

    # Semi-major axis from mean motion (Kepler's 3rd law)
    # n (rad/s) = 2*pi*n_rev_day / 86400
    n_rad_s = 2.0 * math.pi * n / 86400.0
    a_km = (MU_EARTH / (n_rad_s**2)) ** (1.0 / 3.0) if n_rad_s > 0 else 0.0

    # Apogee and perigee altitude (above Earth surface)
    apogee_km = a_km * (1.0 + e) - EARTH_RADIUS_KM
    perigee_km = a_km * (1.0 - e) - EARTH_RADIUS_KM

    return {
        "period_min": round(period_min, 2),
        "semi_major_axis_km": round(a_km, 2),
        "apogee_alt_km": round(apogee_km, 2),
        "perigee_alt_km": round(perigee_km, 2),
    }


async def _get_catalog() -> list[dict[str, Any]]:
    """Fetch and cache the active catalog."""
    cached = cache.get("catalog")
    if cached is not None:
        return cached

    async with cache.lock("catalog"):
        # Double-check after acquiring lock
        cached = cache.get("catalog")
        if cached is not None:
            return cached

        from satguard.catalog.celestrak import fetch_catalog

        catalog = await fetch_catalog("active")
        entries = []
        for tle in catalog:
            params = orbital_params_from_tle(tle)
            entries.append({
                "norad_id": tle.norad_id,
                "name": tle.name,
                "line1": tle.line1,
                "line2": tle.line2,
                "object_type": classify_orbit(tle.mean_motion),
                "inclination_deg": round(tle.inclination, 4),
                "eccentricity": round(tle.eccentricity, 7),
                "raan_deg": round(tle.raan, 4),
                "arg_perigee_deg": round(tle.arg_perigee, 4),
                "mean_anomaly_deg": round(tle.mean_anomaly, 4),
                "mean_motion_rev_day": round(tle.mean_motion, 8),
                "bstar": tle.bstar,
                "epoch": tle.epoch_datetime.isoformat(),
                "intl_designator": tle.intl_designator,
                **params,
            })
        cache.set("catalog", entries, CATALOG_TTL)
        return entries


async def _get_catalog_by_id() -> dict[int, dict[str, Any]]:
    """Get catalog indexed by NORAD ID."""
    cached = cache.get("catalog_by_id")
    if cached is not None:
        return cached

    entries = await _get_catalog()
    by_id = {e["norad_id"]: e for e in entries}
    cache.set("catalog_by_id", by_id, CATALOG_TTL)
    return by_id


@app.get("/api/catalog")
async def get_catalog() -> list[dict[str, Any]]:
    """Return active satellite catalog with TLE strings and orbit classification."""
    return await _get_catalog()


async def _compute_conjunctions() -> list[dict[str, Any]]:
    """Compute top 50 conjunctions via all-on-all vectorized screening.

    Approach:
        1. Propagate ALL catalog objects using sgp4 SatrecArray (vectorized C)
           at fine time steps (120s over 3 days = 2160 steps)
        2. At each time step, KDTree finds all pairs within threshold
        3. Filter: same-launch siblings + co-orbiting (rel_vel < 0.5 km/s)
        4. Deduplicate by pair, keep closest approach
        5. Compute Pc for top 50

    Performance: SatrecArray propagates all ~10K objects at all 2160 epochs
    in a single vectorized C call (~2-5 seconds), then KDTree per epoch.
    Total: ~30-60 seconds.

    Results are cached for 1 hour.
    """
    cached = cache.get("conjunctions")
    if cached is not None:
        return cached

    async with cache.lock("conjunctions"):
        cached = cache.get("conjunctions")
        if cached is not None:
            return cached

        from datetime import datetime, timedelta, timezone

        import numpy as np
        from scipy.spatial import KDTree as KDTreeScipy
        from sgp4.api import Satrec, SatrecArray, WGS72

        from satguard.assess.foster import foster_pc
        from satguard.catalog.celestrak import fetch_catalog
        from satguard.covariance.realism import default_covariance, project_to_encounter_plane
        from satguard.propagate.sgp4 import _jd_from_datetime

        catalog = await fetch_catalog("active")
        tles = catalog.tles
        if not tles:
            cache.set("conjunctions", [], CONJUNCTIONS_TTL)
            return []

        # Build launch-group index for sibling filtering
        launch_prefix: dict[int, str] = {}
        norad_ids: list[int] = []
        mean_motions: list[float] = []
        satrecs: list[Satrec] = []
        valid_tles = []

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
            cache.set("conjunctions", [], CONJUNCTIONS_TTL)
            return []

        logger.info("Propagating %d objects with SatrecArray...", n_sats)

        # Build epoch array: 3 days from NOW, 120s steps
        # Must start from current time, not TLE epoch (which can be days old)
        start_epoch = datetime.now(timezone.utc)
        step_sec = 120.0
        n_steps = int(3 * 86400 / step_sec) + 1

        jd_arr = np.empty(n_steps)
        fr_arr = np.empty(n_steps)
        epoch_dts = []
        for i in range(n_steps):
            t = start_epoch + timedelta(seconds=i * step_sec)
            jd, fr = _jd_from_datetime(t)
            jd_arr[i] = jd
            fr_arr[i] = fr
            epoch_dts.append(t)

        # Vectorized propagation: all sats × all epochs in one C call
        sat_array = SatrecArray(satrecs)
        errors, positions, velocities = sat_array.sgp4(jd_arr, fr_arr)
        # positions shape: (n_sats, n_steps, 3)  in km
        # velocities shape: (n_sats, n_steps, 3) in km/s

        logger.info("Propagation done. Screening %d steps...", n_steps)

        # Build validity mask: True where propagation succeeded
        valid_mask = (errors == 0)  # shape: (n_sats, n_steps)

        # Screen at each time step using KDTree
        threshold_km = 25.0
        norad_arr = np.array(norad_ids)

        # Collect best per pair: (min_id, max_id) → (dist, step_idx, idx_a, idx_b)
        pair_best: dict[tuple[int, int], tuple[float, int, int, int]] = {}

        for step in range(n_steps):
            # Get valid satellites at this step
            step_valid = valid_mask[:, step]
            n_valid = int(np.sum(step_valid))
            if n_valid < 2:
                continue

            valid_indices = np.where(step_valid)[0]
            pos_step = positions[valid_indices, step, :]  # (n_valid, 3)

            # Check for NaN positions (sgp4 can return NaN even with error=0)
            finite_mask = np.all(np.isfinite(pos_step), axis=1)
            if not np.all(finite_mask):
                valid_indices = valid_indices[finite_mask]
                pos_step = pos_step[finite_mask]
                if len(valid_indices) < 2:
                    continue

            tree = KDTreeScipy(pos_step)
            raw_pairs = tree.query_pairs(threshold_km)

            for li, ri in raw_pairs:
                gi = valid_indices[li]  # global index into satrecs/norad_ids
                gj = valid_indices[ri]

                nid_a = norad_ids[gi]
                nid_b = norad_ids[gj]

                # Skip same-launch siblings
                lp_a = launch_prefix.get(nid_a, "")
                lp_b = launch_prefix.get(nid_b, "")
                if lp_a and lp_b and lp_a == lp_b:
                    continue

                dist = float(np.linalg.norm(pos_step[li] - pos_step[ri]))
                pair_key = (min(nid_a, nid_b), max(nid_a, nid_b))

                if pair_key not in pair_best or dist < pair_best[pair_key][0]:
                    pair_best[pair_key] = (dist, step, int(gi), int(gj))

        logger.info("Found %d unique candidate pairs", len(pair_best))

        # Filter and refine top candidates
        candidates = sorted(pair_best.values(), key=lambda x: x[0])[:200]

        results = []
        for dist, step, gi, gj in candidates:
            # Refine TCA: search ±10 steps (±20 min) at this resolution
            best_dist = dist
            best_step = step
            window = 10
            s_start = max(0, step - window)
            s_end = min(n_steps, step + window + 1)

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

            # Get state vectors at refined TCA
            r_a = positions[gi, best_step]
            r_b = positions[gj, best_step]
            v_a = velocities[gi, best_step]
            v_b = velocities[gj, best_step]
            rel_vel = float(np.linalg.norm(v_a - v_b))

            # Filter co-orbiting objects
            if rel_vel < 0.5 or best_dist < 0.01:
                continue

            nid_a = norad_ids[gi]
            nid_b = norad_ids[gj]
            tca = epoch_dts[best_step]

            # Sanity checks on physical plausibility
            assert best_dist > 0, f"miss_distance must be positive, got {best_dist}"
            assert rel_vel < 20.0, f"rel_vel {rel_vel} km/s exceeds LEO max (~15 km/s)"

            # Compute Pc
            pc = float("nan")
            try:
                orbit_a = classify_orbit(mean_motions[gi])
                orbit_b = classify_orbit(mean_motions[gj])
                cov_p = default_covariance(orbit_a)
                cov_s = default_covariance(orbit_b)
                cov_2d = project_to_encounter_plane(
                    cov_p, cov_s, r_a, v_a, r_b, v_b,
                )
                pc = foster_pc(best_dist, cov_2d, hard_body_radius=0.02)
                # Pc is a probability: must be in [0, 1]
                if not (0.0 <= pc <= 1.0):
                    logger.warning("Pc=%e out of [0,1] range for %d vs %d", pc, nid_a, nid_b)
                    pc = float("nan")
            except Exception:
                logger.debug("Pc computation failed for %d vs %d", nid_a, nid_b, exc_info=True)

            results.append({
                "norad_id_primary": nid_a,
                "norad_id_secondary": nid_b,
                "tca": tca.isoformat(),
                "miss_distance_km": round(best_dist, 4),
                "relative_velocity_km_s": round(rel_vel, 3),
                "pc": pc if not math.isnan(pc) else None,
            })

            if len(results) >= 50:
                break

        results.sort(key=lambda r: r["miss_distance_km"])
        logger.info("Found %d conjunctions after filtering", len(results))
        cache.set("conjunctions", results, CONJUNCTIONS_TTL)
        return results


@app.get("/api/conjunctions")
async def get_conjunctions() -> list[dict[str, Any]]:
    """Return top 50 conjunctions. Pre-computed at startup, cached 1 hour."""
    return await _compute_conjunctions()


@app.get("/api/objects/{norad_id}")
async def get_object_detail(norad_id: int) -> dict[str, Any]:
    """Return detailed info for a single object by NORAD ID.

    All orbital elements are pre-computed when the catalog is fetched,
    so this endpoint just returns the cached entry (no TLE re-parsing).
    """
    by_id = await _get_catalog_by_id()
    entry = by_id.get(norad_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Object {norad_id} not found")

    # Return all fields except raw TLE lines (those are in /api/catalog)
    return {k: v for k, v in entry.items() if k not in ("line1", "line2")}


def mount_static(dist_dir: str | Path | None = None) -> None:
    """Mount the built frontend as static files (production mode)."""
    if dist_dir is None:
        dist_dir = Path(__file__).parent.parent.parent.parent / "web" / "dist"
    dist_dir = Path(dist_dir)
    if dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="static")
