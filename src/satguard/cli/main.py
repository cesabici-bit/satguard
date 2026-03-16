"""SatGuard CLI entrypoint.

Usage: satguard screen --norad-id 25544 --days 7
"""

from __future__ import annotations

import asyncio
import sys

import click

from satguard.assess.foster import foster_pc
from satguard.catalog.celestrak import fetch_tle_by_norad
from satguard.cdm.writer import write_cdm
from satguard.covariance.realism import default_covariance, project_to_encounter_plane
from satguard.propagate.sgp4 import propagate_batch
from satguard.screen.screener import screen as screen_conjunctions


@click.group()
@click.version_option(package_name="satguard")
def cli() -> None:
    """SatGuard — Conjunction assessment pipeline."""


@cli.command()
@click.option("--norad-id", required=True, type=int, help="NORAD catalog number of primary object")
@click.option("--days", default=3, type=float, help="Screening window in days (default: 3)")
@click.option("--threshold", default=50.0, type=float, help="Threshold km (default: 50)")
@click.option("--step", default=60.0, type=float, help="Propagation step in seconds (default: 60)")
@click.option("--output-cdm", is_flag=True, help="Output CDM for each conjunction")
def screen(
    norad_id: int,
    days: float,
    threshold: float,
    step: float,
    output_cdm: bool,
) -> None:
    """Screen for conjunctions against active catalog."""
    asyncio.run(_screen_async(norad_id, days, threshold, step, output_cdm))


async def _screen_async(
    norad_id: int,
    days: float,
    threshold: float,
    step: float,
    output_cdm: bool,
) -> None:
    """Async implementation of screening command."""
    click.echo("SatGuard Conjunction Screening")
    click.echo(f"{'=' * 40}")
    click.echo(f"Primary object:   NORAD {norad_id}")
    click.echo(f"Window:           {days:.1f} days")
    click.echo(f"Threshold:        {threshold:.1f} km")
    click.echo(f"Step:             {step:.0f} s")
    click.echo()

    # Fetch primary TLE
    click.echo("Fetching primary TLE from CelesTrak...")
    try:
        primary_tle = await fetch_tle_by_norad(norad_id)
    except Exception as e:
        click.echo(f"ERROR: Failed to fetch TLE for NORAD {norad_id}: {e}", err=True)
        sys.exit(1)

    click.echo(f"  Object: {primary_tle.name}")
    click.echo(f"  Epoch:  {primary_tle.epoch_datetime.isoformat()}")
    click.echo()

    # Propagate primary
    click.echo("Propagating primary orbit...")
    primary_states = propagate_batch(primary_tle, days=days, step_seconds=step)
    click.echo(f"  Generated {len(primary_states)} state vectors")
    click.echo()

    # For MVP, screen against a sample of active objects
    click.echo("Fetching active catalog from CelesTrak...")
    from satguard.catalog.celestrak import fetch_catalog

    try:
        catalog = await fetch_catalog("active")
        click.echo(f"  Catalog: {len(catalog)} objects")
    except Exception as e:
        click.echo(f"WARNING: Could not fetch catalog: {e}", err=True)
        click.echo("  Falling back to primary-only mode (no screening targets)")
        click.echo()
        click.echo("No conjunctions to report (no secondary objects).")
        return

    click.echo()
    click.echo("Screening...")

    all_events = []
    for tle in catalog:
        if tle.norad_id == norad_id:
            continue  # Skip self
        try:
            start_epoch = primary_tle.epoch_datetime
            sec_states = propagate_batch(
                tle, days=days, step_seconds=step, start=start_epoch,
            )
            events = screen_conjunctions(primary_states, sec_states, threshold_km=threshold)
            all_events.extend(events)
        except Exception:
            continue  # Skip objects that fail to propagate

    all_events.sort(key=lambda e: e.miss_distance_km)

    click.echo(f"\nResults: {len(all_events)} conjunction(s) found")
    click.echo(f"{'=' * 60}")

    if not all_events:
        click.echo("No conjunctions within screening threshold.")
        return

    for i, event in enumerate(all_events[:20]):  # Show top 20
        cov_p = default_covariance("LEO")
        cov_s = default_covariance("LEO")
        try:
            cov_2d = project_to_encounter_plane(
                cov_p, cov_s,
                event.r_primary, event.v_primary,
                event.r_secondary, event.v_secondary,
            )
            pc = foster_pc(event.miss_distance_km, cov_2d, hard_body_radius=0.02)
        except Exception:
            pc = float("nan")

        click.echo(
            f"\n  [{i+1}] NORAD {event.norad_id_primary} vs {event.norad_id_secondary}"
        )
        click.echo(f"      TCA:           {event.tca.isoformat()}")
        click.echo(f"      Miss distance: {event.miss_distance_km:.3f} km")
        click.echo(f"      Rel. velocity: {event.relative_velocity_km_s:.3f} km/s")
        click.echo(f"      Pc (Foster):   {pc:.2e}")

        if output_cdm:
            cdm = write_cdm(event, pc)
            click.echo(f"\n      --- CDM ---\n{cdm}")
