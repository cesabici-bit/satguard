"""SatGuard CLI entrypoint.

Usage:
    satguard screen --norad-id 25544 --days 7
    satguard watch --norad-id 25544 --days 3 --config ~/.satguard/config.toml
    satguard history --norad-ids 25544,41335
    satguard alert-test --config ~/.satguard/config.toml
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

from satguard.assess.chan import chan_pc
from satguard.assess.foster import foster_pc
from satguard.catalog.celestrak import fetch_tle_by_norad
from satguard.cdm.writer import write_cdm
from satguard.covariance.realism import (
    assess_covariance,
    default_covariance,
    project_to_encounter_plane,
)
from satguard.propagate.sgp4 import propagate_batch
from satguard.screen.screener import screen as screen_conjunctions


@click.group()
@click.version_option(package_name="satguard")
def cli() -> None:
    """SatGuard — Conjunction assessment pipeline."""


# ---------------------------------------------------------------------------
# screen (v0.1 — enhanced with --record and --assess-covariance in v0.2)
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--norad-id", required=True, type=int, help="NORAD catalog number of primary object")
@click.option("--days", default=3, type=float, help="Screening window in days (default: 3)")
@click.option("--threshold", default=50.0, type=float, help="Threshold km (default: 50)")
@click.option("--step", default=60.0, type=float, help="Propagation step in seconds (default: 60)")
@click.option("--output-cdm", is_flag=True, help="Output CDM for each conjunction")
@click.option("--record", is_flag=True, help="Record results to Pc history (v0.2)")
@click.option(
    "--assess-covariance", "assess_cov", is_flag=True, help="Show covariance quality",
)
@click.option("--history-dir", type=click.Path(), default=None, help="History directory")
def screen(
    norad_id: int,
    days: float,
    threshold: float,
    step: float,
    output_cdm: bool,
    record: bool,
    assess_cov: bool,
    history_dir: str | None,
) -> None:
    """Screen for conjunctions against active catalog."""
    asyncio.run(
        _screen_async(norad_id, days, threshold, step, output_cdm, record, assess_cov, history_dir)
    )


async def _screen_async(
    norad_id: int,
    days: float,
    threshold: float,
    step: float,
    output_cdm: bool,
    record: bool,
    assess_cov: bool,
    history_dir: str | None,
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

    # Optional: set up history store
    store = None
    if record:
        from satguard.history.store import HistoryStore
        hdir = Path(history_dir) if history_dir else None
        store = HistoryStore(base_dir=hdir)

    for i, event in enumerate(all_events[:20]):  # Show top 20
        cov_p = default_covariance("LEO")
        cov_s = default_covariance("LEO")
        try:
            cov_2d = project_to_encounter_plane(
                cov_p, cov_s,
                event.r_primary, event.v_primary,
                event.r_secondary, event.v_secondary,
            )
            pc = foster_pc(
                event.miss_distance_km, cov_2d, hard_body_radius=0.02,
            )
            pc_c: float | None = None
            with contextlib.suppress(Exception):
                pc_c = chan_pc(
                    event.miss_distance_km, cov_2d, hard_body_radius=0.02,
                )
        except Exception:
            pc = float("nan")
            pc_c = None

        click.echo(
            f"\n  [{i+1}] NORAD {event.norad_id_primary}"
            f" vs {event.norad_id_secondary}"
        )
        click.echo(f"      TCA:           {event.tca.isoformat()}")
        click.echo(f"      Miss distance: {event.miss_distance_km:.3f} km")
        click.echo(f"      Rel. velocity: {event.relative_velocity_km_s:.3f} km/s")
        click.echo(f"      Pc (Foster):   {pc:.2e}")

        if assess_cov:
            assessment = assess_covariance(cov_p)
            click.echo(f"      Covariance:    {assessment.realism_flag} "
                        f"(eig_ratio={assessment.eigenvalue_ratio:.1f}, "
                        f"sigma_max={assessment.position_sigma_max_km:.2f} km)")

        if output_cdm:
            cdm = write_cdm(event, pc)
            click.echo(f"\n      --- CDM ---\n{cdm}")

        # Record to history
        if store and not math.isnan(pc):
            from satguard.history.store import PcSnapshot
            snap = PcSnapshot(
                timestamp=datetime.now(UTC),
                tca=event.tca,
                miss_distance_km=event.miss_distance_km,
                pc_foster=pc,
                pc_chan=pc_c,
                tle_epoch_primary=primary_tle.epoch_datetime,
                tle_epoch_secondary=primary_tle.epoch_datetime,
                covariance_source="default_LEO",
            )
            store.record(snap, event.norad_id_primary, event.norad_id_secondary)

    if store:
        click.echo(f"\n  Results recorded to {store.base_dir}")


# ---------------------------------------------------------------------------
# watch (v0.2) — screen + record + alert
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--norad-id", required=True, type=int, help="NORAD catalog number")
@click.option("--days", default=3, type=float, help="Screening window in days")
@click.option("--threshold", default=50.0, type=float, help="Threshold km")
@click.option("--step", default=60.0, type=float, help="Propagation step seconds")
@click.option("--config", "config_path", type=click.Path(), default=None, help="Config TOML path")
@click.option("--history-dir", type=click.Path(), default=None, help="History directory")
def watch(
    norad_id: int,
    days: float,
    threshold: float,
    step: float,
    config_path: str | None,
    history_dir: str | None,
) -> None:
    """Screen, record Pc history, and send alerts if configured."""
    asyncio.run(_watch_async(norad_id, days, threshold, step, config_path, history_dir))


async def _watch_async(
    norad_id: int,
    days: float,
    threshold: float,
    step: float,
    config_path: str | None,
    history_dir: str | None,
) -> None:
    from satguard.alert.rules import AlertConfig, load_config, should_alert
    from satguard.alert.webhook import send_alert
    from satguard.catalog.celestrak import fetch_catalog
    from satguard.history.store import HistoryStore, PcSnapshot

    # Load alert config (optional)
    alert_config: AlertConfig | None = None
    if config_path:
        try:
            alert_config = load_config(Path(config_path))
            click.echo(f"Alert config loaded: threshold={alert_config.pc_threshold:.1e}")
        except Exception as e:
            click.echo(f"WARNING: Could not load config: {e}", err=True)
    else:
        # Try default location
        try:
            alert_config = load_config()
            click.echo(
                f"Alert config loaded from default: "
                f"threshold={alert_config.pc_threshold:.1e}"
            )
        except FileNotFoundError:
            click.echo("No alert config found. Alerts disabled.")

    hdir = Path(history_dir) if history_dir else None
    store = HistoryStore(base_dir=hdir)

    click.echo(f"\nSatGuard Watch — NORAD {norad_id}")
    click.echo(f"{'=' * 40}")

    # Fetch and propagate
    try:
        primary_tle = await fetch_tle_by_norad(norad_id)
    except Exception as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    click.echo(f"Primary: {primary_tle.name} (epoch {primary_tle.epoch_datetime.isoformat()})")
    primary_states = propagate_batch(primary_tle, days=days, step_seconds=step)

    try:
        catalog = await fetch_catalog("active")
    except Exception as e:
        click.echo(f"ERROR: Could not fetch catalog: {e}", err=True)
        sys.exit(1)

    click.echo(f"Screening {len(catalog)} objects...")

    all_events = []
    for tle in catalog:
        if tle.norad_id == norad_id:
            continue
        try:
            sec_states = propagate_batch(
                tle, days=days, step_seconds=step, start=primary_tle.epoch_datetime,
            )
            events = screen_conjunctions(primary_states, sec_states, threshold_km=threshold)
            all_events.extend(events)
        except Exception:
            continue

    all_events.sort(key=lambda e: e.miss_distance_km)
    click.echo(f"Found {len(all_events)} conjunction(s)\n")

    alerts_sent = 0
    for event in all_events[:20]:
        cov_p = default_covariance("LEO")
        cov_s = default_covariance("LEO")
        try:
            cov_2d = project_to_encounter_plane(
                cov_p, cov_s,
                event.r_primary, event.v_primary,
                event.r_secondary, event.v_secondary,
            )
            pc = foster_pc(
                event.miss_distance_km, cov_2d, hard_body_radius=0.02,
            )
            pc_c: float | None = None
            with contextlib.suppress(Exception):
                pc_c = chan_pc(
                    event.miss_distance_km, cov_2d, hard_body_radius=0.02,
                )
        except Exception:
            continue

        # Record snapshot
        snap = PcSnapshot(
            timestamp=datetime.now(UTC),
            tca=event.tca,
            miss_distance_km=event.miss_distance_km,
            pc_foster=pc,
            pc_chan=pc_c,
            tle_epoch_primary=primary_tle.epoch_datetime,
            tle_epoch_secondary=primary_tle.epoch_datetime,
            covariance_source="default_LEO",
        )
        store.record(snap, event.norad_id_primary, event.norad_id_secondary)

        nid_p = event.norad_id_primary
        nid_s = event.norad_id_secondary
        click.echo(
            f"  NORAD {nid_p} vs {nid_s}: "
            f"miss={event.miss_distance_km:.3f} km, Pc={pc:.2e}"
        )

        # Alert check
        if alert_config:
            history = store.load(nid_p, nid_s, event.tca)
            if should_alert(alert_config, history, pc):
                ok = await send_alert(alert_config, event, pc, history)
                if ok:
                    click.echo(f"    ALERT SENT: {nid_p} vs {nid_s}")
                    alerts_sent += 1
                else:
                    click.echo(f"    ALERT FAILED: {nid_p} vs {nid_s}")

    click.echo(f"\nRecorded to {store.base_dir}")
    if alert_config:
        click.echo(f"Alerts sent: {alerts_sent}")


# ---------------------------------------------------------------------------
# history (v0.2)
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--norad-ids", required=True, type=str, help="NORAD IDs (e.g., 25544,41335)",
)
@click.option("--history-dir", type=click.Path(), default=None, help="History directory")
@click.option("--plot", is_flag=True, help="Save Pc evolution plot as PNG")
def history(norad_ids: str, history_dir: str | None, plot: bool) -> None:
    """Show Pc evolution for a conjunction pair."""
    parts = norad_ids.split(",")
    if len(parts) != 2:
        click.echo("ERROR: --norad-ids must be two comma-separated integers", err=True)
        sys.exit(1)

    try:
        id_a, id_b = int(parts[0].strip()), int(parts[1].strip())
    except ValueError:
        click.echo("ERROR: NORAD IDs must be integers", err=True)
        sys.exit(1)

    from satguard.history.evolution import pc_trend
    from satguard.history.store import HistoryStore

    hdir = Path(history_dir) if history_dir else None
    store = HistoryStore(base_dir=hdir)

    # Find all history files for this pair
    a, b = min(id_a, id_b), max(id_a, id_b)
    conjs = store.list_conjunctions()
    matching = [(na, nb, d) for na, nb, d in conjs if na == a and nb == b]

    if not matching:
        click.echo(f"No history found for NORAD {a} vs {b}")
        return

    for na, nb, date_str in matching:
        from datetime import datetime as dt
        tca_date = dt.strptime(date_str, "%Y%m%d").replace(tzinfo=UTC)
        hist = store.load(na, nb, tca_date)
        if hist is None:
            continue

        trend = pc_trend(hist)
        click.echo(f"\nConjunction: NORAD {na} vs {nb} (TCA ~{date_str})")
        click.echo(f"  Snapshots:  {trend.snapshots_count}")
        click.echo(f"  Latest Pc:  {trend.latest_pc:.2e}")
        click.echo(f"  Trend:      {trend.direction.value}")
        click.echo(f"  Delta Pc:   {trend.delta_pc:+.2e}")

        if trend.snapshots_count > 1:
            click.echo("\n  Time             | Miss (km)  | Pc (Foster)")
            click.echo(f"  {'-' * 50}")
            for snap in hist.snapshots:
                click.echo(
                    f"  {snap.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                    f"{snap.miss_distance_km:>9.3f}  | {snap.pc_foster:.2e}"
                )

        if plot and trend.snapshots_count > 1:
            _plot_evolution(hist, a, b, date_str)


def _plot_evolution(hist, norad_a: int, norad_b: int, date_str: str) -> None:  # type: ignore[no-untyped-def]
    """Save a matplotlib plot of Pc evolution."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        click.echo("  WARNING: matplotlib not available, skipping plot")
        return

    times = [s.timestamp for s in hist.snapshots]
    pcs = [s.pc_foster for s in hist.snapshots]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.semilogy(times, pcs, "o-", color="tab:red", linewidth=2, markersize=6)
    ax.set_xlabel("Assessment Time (UTC)")
    ax.set_ylabel("Collision Probability (Pc)")
    ax.set_title(f"SatGuard — Pc Evolution: NORAD {norad_a} vs {norad_b}")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    fname = f"pc_evolution_{norad_a}_{norad_b}_{date_str}.png"
    fig.savefig(fname, dpi=150)
    plt.close(fig)
    click.echo(f"  Plot saved: {fname}")


# ---------------------------------------------------------------------------
# alert-test (v0.2)
# ---------------------------------------------------------------------------


@cli.command("alert-test")
@click.option("--config", "config_path", type=click.Path(), default=None, help="Config TOML path")
def alert_test(config_path: str | None) -> None:
    """Send a test alert to verify webhook configuration."""
    asyncio.run(_alert_test_async(config_path))


async def _alert_test_async(config_path: str | None) -> None:
    import numpy as np

    from satguard.alert.rules import load_config
    from satguard.alert.webhook import send_alert
    from satguard.screen.screener import ConjunctionEvent

    path = Path(config_path) if config_path else None
    try:
        config = load_config(path)
    except Exception as e:
        click.echo(f"ERROR: Could not load config: {e}", err=True)
        sys.exit(1)

    click.echo(f"Sending test alert to: {config.webhook_url}")

    # Create a synthetic test event
    test_event = ConjunctionEvent(
        tca=datetime.now(UTC),
        miss_distance_km=0.1,
        r_primary=np.array([7000.0, 0.0, 0.0]),
        v_primary=np.array([0.0, 7.5, 0.0]),
        r_secondary=np.array([7000.1, 0.0, 0.0]),
        v_secondary=np.array([0.0, -7.5, 0.0]),
        norad_id_primary=99999,
        norad_id_secondary=99998,
        relative_velocity_km_s=15.0,
    )

    ok = await send_alert(config, test_event, pc=9.99e-1)
    if ok:
        click.echo("Test alert delivered successfully!")
    else:
        click.echo("Test alert FAILED. Check your webhook URL and network.", err=True)
        sys.exit(1)
