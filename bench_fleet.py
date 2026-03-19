"""Benchmark: vectorized fleet screening with real catalog.

Fetches the active catalog from CelesTrak, then runs screen_fleet()
with a small fleet (ISS + 2 Starlink sats) to measure wall-clock time.
"""

import asyncio
import time


async def main() -> None:
    from satguard.catalog.celestrak import fetch_catalog
    from satguard.fleet.parser import FleetConfig, FleetThresholds
    from satguard.fleet.batch import screen_fleet

    # 1. Fetch catalog
    print("Fetching active catalog from CelesTrak...")
    t0 = time.perf_counter()
    catalog = await fetch_catalog("active")
    t_fetch = time.perf_counter() - t0
    print(f"  Catalog: {len(catalog)} objects ({t_fetch:.1f}s)")

    # 2. Define fleet (same as typical usage)
    fleet = FleetConfig(
        name="Benchmark",
        objects=[25544, 48274, 55550],  # ISS, Starlink-3087, Starlink-5383
        thresholds=FleetThresholds(
            pc=0,
            miss_km=25.0,
            days=3,
        ),
    )

    # 2b. Check fleet objects exist in catalog
    catalog_ids = {tle.norad_id for tle in catalog.tles}
    for nid in fleet.objects:
        found = nid in catalog_ids
        print(f"  Fleet NORAD {nid}: {'FOUND' if found else 'NOT FOUND'} in catalog")

    # 3. Run vectorized screening (with verbose logging)
    import logging
    logging.basicConfig(level=logging.INFO, format="  %(name)s: %(message)s")

    print(f"\nScreening fleet ({len(fleet.objects)} objects) vs catalog ({len(catalog)} objects)...")
    print(f"  Config: {fleet.thresholds.days} days, step=120s, threshold={fleet.thresholds.miss_km} km")
    t1 = time.perf_counter()
    results = await screen_fleet(fleet, catalog=catalog)
    t_screen = time.perf_counter() - t1

    # 4. Report
    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Catalog size:    {len(catalog)} objects")
    print(f"  Fleet objects:   {fleet.objects}")
    print(f"  Conjunctions:    {len(results)}")
    print(f"  Fetch time:      {t_fetch:.1f}s")
    print(f"  Screening time:  {t_screen:.1f}s")
    print(f"  Total:           {t_fetch + t_screen:.1f}s")
    print(f"{'='*60}")

    if results:
        print(f"\nTop 5 conjunctions:")
        for i, sc in enumerate(results[:5]):
            ev = sc.event
            print(
                f"  {i+1}. {ev.norad_id_primary} vs {ev.norad_id_secondary}"
                f"  miss={ev.miss_distance_km:.3f} km"
                f"  Pc={sc.pc:.2e}"
                f"  TCA={ev.tca:%Y-%m-%d %H:%M}"
            )


if __name__ == "__main__":
    asyncio.run(main())
