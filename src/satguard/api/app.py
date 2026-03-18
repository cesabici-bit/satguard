"""SatGuard FastAPI application.

Endpoints:
    GET /api/catalog        — Active satellite catalog (TLE strings + metadata)
    GET /api/conjunctions   — Top 50 conjunctions for ISS (or first object)
    GET /api/objects/{id}   — Object detail by NORAD ID
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from satguard.api.cache import cache

app = FastAPI(title="SatGuard API", version="0.3.0")

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Constants
CATALOG_TTL = 3600  # 1 hour
CONJUNCTIONS_TTL = 600  # 10 minutes
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


@app.get("/api/conjunctions")
async def get_conjunctions() -> list[dict[str, Any]]:
    """Return top 50 conjunctions (pre-computed for ISS / first catalog object).

    Uses the existing SatGuard screening pipeline with default covariance.
    Results are cached for 10 minutes.
    """
    cached = cache.get("conjunctions")
    if cached is not None:
        return cached

    async with cache.lock("conjunctions"):
        cached = cache.get("conjunctions")
        if cached is not None:
            return cached

        import contextlib

        from satguard.assess.foster import foster_pc
        from satguard.catalog.celestrak import fetch_catalog, fetch_tle_by_norad
        from satguard.covariance.realism import default_covariance, project_to_encounter_plane
        from satguard.propagate.sgp4 import propagate_batch
        from satguard.screen.screener import screen

        # Try ISS first, fallback to first catalog object
        primary_norad = 25544
        try:
            primary_tle = await fetch_tle_by_norad(primary_norad)
        except Exception:
            catalog = await fetch_catalog("active")
            if not catalog.tles:
                cache.set("conjunctions", [], CONJUNCTIONS_TTL)
                return []
            primary_tle = catalog.tles[0]
            primary_norad = primary_tle.norad_id

        # Propagate primary 3 days, 120s steps (coarser for speed)
        primary_states = propagate_batch(primary_tle, days=3, step_seconds=120)

        # Screen against catalog subset (first 2000 for speed)
        catalog = await fetch_catalog("active")
        all_events = []
        for tle in list(catalog)[:2000]:
            if tle.norad_id == primary_norad:
                continue
            try:
                sec_states = propagate_batch(
                    tle, days=3, step_seconds=120,
                    start=primary_tle.epoch_datetime,
                )
                events = screen(primary_states, sec_states, threshold_km=50)
                all_events.extend(events)
            except Exception:
                continue

        all_events.sort(key=lambda e: e.miss_distance_km)

        results = []
        for event in all_events[:50]:
            pc = float("nan")
            with contextlib.suppress(Exception):
                cov_p = default_covariance("LEO")
                cov_s = default_covariance("LEO")
                cov_2d = project_to_encounter_plane(
                    cov_p, cov_s,
                    event.r_primary, event.v_primary,
                    event.r_secondary, event.v_secondary,
                )
                pc = foster_pc(event.miss_distance_km, cov_2d, hard_body_radius=0.02)

            results.append({
                "norad_id_primary": event.norad_id_primary,
                "norad_id_secondary": event.norad_id_secondary,
                "tca": event.tca.isoformat(),
                "miss_distance_km": round(event.miss_distance_km, 4),
                "relative_velocity_km_s": round(event.relative_velocity_km_s, 3),
                "pc": pc if not math.isnan(pc) else None,
            })

        cache.set("conjunctions", results, CONJUNCTIONS_TTL)
        return results


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
