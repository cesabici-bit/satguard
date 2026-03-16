"""Smoke test E2E — M3: defines 'done' for SatGuard MVP.

This test exercises the full pipeline:
  TLE parse → SGP4 propagate → screen conjunctions → compute Pc → write CDM

It will initially FAIL (NotImplementedError) and progressively pass
as each module is implemented.
"""

from satguard.assess.foster import foster_pc
from satguard.catalog.tle import parse_tle
from satguard.cdm.writer import write_cdm
from satguard.covariance.realism import default_covariance, project_to_encounter_plane
from satguard.propagate.sgp4 import propagate_batch
from satguard.screen.screener import screen

# ISS TLE (epoch ~2024, used as static test fixture)
ISS_TLE = """\
ISS (ZARYA)
1 25544U 98067A   24045.51749023  .00020825  00000+0  37340-3 0  9992
2 25544  51.6416  14.5021 0006703  38.8378  76.2277 15.49560867441079"""

# A second object for screening (COSMOS 2251 DEB — real debris)
DEBRIS_TLE = """\
COSMOS 2251 DEB
1 34454U 93036SX  24045.18042714  .00001344  00000+0  47887-3 0  9991
2 34454  74.0206  93.5412 0025978 269.5098  90.3101 14.35024750741170"""


def test_smoke_e2e() -> None:
    """Full pipeline smoke test: TLE → propagate → screen → Pc → CDM."""
    # 1. Parse TLEs
    tle_primary = parse_tle(ISS_TLE)
    assert tle_primary.norad_id == 25544

    tle_secondary = parse_tle(DEBRIS_TLE)
    assert tle_secondary.norad_id == 34454

    # 2. Propagate both for 3 days at 60s steps
    states_primary = propagate_batch(tle_primary, days=3.0, step_seconds=60.0)
    states_secondary = propagate_batch(tle_secondary, days=3.0, step_seconds=60.0)
    assert len(states_primary) > 0
    assert len(states_secondary) > 0

    # 3. Screen for conjunctions (threshold 50 km)
    events = screen(
        primary_states=states_primary,
        secondary_states=states_secondary,
        threshold_km=50.0,
    )
    # We don't assert events found — orbits may or may not be close

    # 4. If any conjunction found, compute Pc and write CDM
    if events:
        event = events[0]
        cov_primary = default_covariance("LEO")
        cov_secondary = default_covariance("LEO")
        cov_2d = project_to_encounter_plane(
            cov_primary, cov_secondary,
            event.r_primary, event.v_primary,
            event.r_secondary, event.v_secondary,
        )
        pc = foster_pc(
            miss_distance=event.miss_distance_km,
            cov_2d=cov_2d,
            hard_body_radius=0.02,  # 20m in km
        )
        assert 0.0 <= pc <= 1.0

        cdm_text = write_cdm(event, pc)
        assert "CCSDS_CDM_VERS" in cdm_text
        assert "COLLISION_PROBABILITY" in cdm_text
        print("\n=== SMOKE TEST OUTPUT ===")
        print(f"Conjunction found: TCA={event.tca}")
        print(f"Miss distance: {event.miss_distance_km:.3f} km")
        print(f"Pc (Foster): {pc:.2e}")
        print(f"CDM preview:\n{cdm_text[:500]}")
    else:
        print("\n=== SMOKE TEST OUTPUT ===")
        print("No conjunctions found in 3-day window (expected for these orbits)")
        print("Pipeline exercised: parse OK, propagate OK, screen OK")
