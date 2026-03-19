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


app = FastAPI(title="SatGuard API", version="0.5.1", lifespan=lifespan)

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

    Delegates to ``screen.vectorized.vectorized_screen`` which handles
    SatrecArray propagation, KDTree screening, sibling/co-orbiting filtering,
    TCA refinement, and Pc computation.

    Results are cached for 1 hour.
    """
    cached = cache.get("conjunctions")
    if cached is not None:
        return cached

    async with cache.lock("conjunctions"):
        cached = cache.get("conjunctions")
        if cached is not None:
            return cached

        from satguard.catalog.celestrak import fetch_catalog
        from satguard.screen.vectorized import VectorizedConfig, vectorized_screen

        catalog = await fetch_catalog("active")
        tles = catalog.tles
        if not tles:
            cache.set("conjunctions", [], CONJUNCTIONS_TTL)
            return []

        config = VectorizedConfig(
            threshold_km=25.0,
            step_seconds=120.0,
            days=3.0,
            max_results=50,
        )

        scored = vectorized_screen(tles=tles, config=config)

        results = []
        for sc in scored:
            ev = sc.event
            results.append({
                "norad_id_primary": ev.norad_id_primary,
                "norad_id_secondary": ev.norad_id_secondary,
                "tca": ev.tca.isoformat(),
                "miss_distance_km": round(ev.miss_distance_km, 4),
                "relative_velocity_km_s": round(ev.relative_velocity_km_s, 3),
                "pc": sc.pc,
            })

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
