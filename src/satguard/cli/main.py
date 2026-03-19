"""SatGuard CLI entrypoint.

Usage:
    satguard screen --norad-id 25544 --days 7
    satguard watch --norad-id 25544 --days 3 --config ~/.satguard/config.toml
    satguard history --norad-ids 25544,41335
    satguard alert-test --config ~/.satguard/config.toml
    satguard fleet screen --fleet fleet.yaml --output report.pdf
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

        # Record to history (v0.6: include TLE lines for replay)
        if store and not math.isnan(pc):
            from satguard.history.store import PcSnapshot

            # Find secondary TLE for archival
            sec_tle = None
            for tle in catalog:
                if tle.norad_id == event.norad_id_secondary:
                    sec_tle = tle
                    break

            snap = PcSnapshot(
                timestamp=datetime.now(UTC),
                tca=event.tca,
                miss_distance_km=event.miss_distance_km,
                pc_foster=pc,
                pc_chan=pc_c,
                tle_epoch_primary=primary_tle.epoch_datetime,
                tle_epoch_secondary=sec_tle.epoch_datetime if sec_tle else primary_tle.epoch_datetime,
                covariance_source="default_LEO",
                tle_line1_primary=primary_tle.line1,
                tle_line2_primary=primary_tle.line2,
                tle_line1_secondary=sec_tle.line1 if sec_tle else None,
                tle_line2_secondary=sec_tle.line2 if sec_tle else None,
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

        # Record snapshot (v0.6: include TLE lines for replay)
        sec_tle = None
        for tle in catalog:
            if tle.norad_id == event.norad_id_secondary:
                sec_tle = tle
                break

        snap = PcSnapshot(
            timestamp=datetime.now(UTC),
            tca=event.tca,
            miss_distance_km=event.miss_distance_km,
            pc_foster=pc,
            pc_chan=pc_c,
            tle_epoch_primary=primary_tle.epoch_datetime,
            tle_epoch_secondary=sec_tle.epoch_datetime if sec_tle else primary_tle.epoch_datetime,
            covariance_source="default_LEO",
            tle_line1_primary=primary_tle.line1,
            tle_line2_primary=primary_tle.line2,
            tle_line1_secondary=sec_tle.line1 if sec_tle else None,
            tle_line2_secondary=sec_tle.line2 if sec_tle else None,
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


@cli.command()
@click.option("--port", default=8000, type=int, help="Port to serve on (default: 8000)")
@click.option("--host", default="127.0.0.1", type=str, help="Host to bind (default: 127.0.0.1)")
@click.option("--dev", is_flag=True, help="Run in dev mode (no static mount, auto-reload)")
def serve(port: int, host: str, dev: bool) -> None:
    """Start the SatGuard web server with 3D globe."""
    import uvicorn

    from satguard.api.app import app, mount_static

    if not dev:
        mount_static()
        click.echo(f"SatGuard Globe 3D — http://{host}:{port}")
    else:
        click.echo(f"SatGuard API (dev) — http://{host}:{port}")
        click.echo("Frontend: run 'cd web && npm run dev' separately")

    uvicorn.run(app, host=host, port=port)


# ---------------------------------------------------------------------------
# fleet (v0.5) — constellation batch screening + PDF report
# ---------------------------------------------------------------------------


@cli.group()
def fleet() -> None:
    """Fleet management: batch screening for constellations."""


@fleet.command("screen")
@click.option(
    "--fleet", "fleet_path", required=True,
    type=click.Path(exists=True), help="Fleet YAML file",
)
@click.option("--output", "output_path", type=click.Path(), default=None, help="Output PDF path")
@click.option("--no-pdf", is_flag=True, help="Console output only, no PDF")
def fleet_screen(fleet_path: str, output_path: str | None, no_pdf: bool) -> None:
    """Screen all fleet objects against active catalog."""
    asyncio.run(_fleet_screen_async(fleet_path, output_path, no_pdf))


async def _fleet_screen_async(
    fleet_path: str, output_path: str | None, no_pdf: bool,
) -> None:
    """Async implementation of fleet screening."""
    from satguard.fleet.batch import screen_fleet
    from satguard.fleet.parser import load_fleet
    from satguard.report.pdf import generate_report

    fleet_file = Path(fleet_path)
    try:
        fleet_config = load_fleet(fleet_file)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    click.echo("SatGuard Fleet Screening")
    click.echo(f"{'=' * 50}")
    click.echo(f"Fleet:      {fleet_config.name}")
    click.echo(f"Objects:    {len(fleet_config.objects)} satellites")
    click.echo(f"Window:     {fleet_config.thresholds.days} days")
    t = fleet_config.thresholds
    click.echo(f"Threshold:  {t.miss_km:.0f} km / Pc >= {t.pc:.1e}")
    click.echo()

    click.echo("Screening fleet against active catalog...")
    conjunctions = await screen_fleet(fleet_config)

    click.echo(f"\nResults: {len(conjunctions)} conjunction(s)")
    click.echo(f"{'=' * 70}")

    if not conjunctions:
        click.echo("No conjunctions above threshold. All clear.")
        return

    # Console table (top 10)
    click.echo(
        f"{'#':>3}  {'Primary':>8}  {'Secondary':>8}  "
        f"{'TCA':>20}  {'Miss(km)':>10}  {'Vrel(km/s)':>10}  {'Pc':>10}"
    )
    click.echo(f"{'─' * 78}")

    for i, sc in enumerate(conjunctions[:10]):
        e = sc.event
        click.echo(
            f"{i+1:>3}  {e.norad_id_primary:>8}  {e.norad_id_secondary:>8}  "
            f"{e.tca.strftime('%Y-%m-%d %H:%M:%S'):>20}  "
            f"{e.miss_distance_km:>10.3f}  "
            f"{e.relative_velocity_km_s:>10.2f}  "
            f"{sc.pc:>10.2e}"
        )

    if len(conjunctions) > 10:
        click.echo(f"\n  ... and {len(conjunctions) - 10} more (see PDF report)")

    # Generate PDF
    if not no_pdf:
        if output_path is None:
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M")
            output_path = f"satguard_report_{fleet_config.name}_{ts}.pdf"
        out = Path(output_path)
        generate_report(fleet_config, conjunctions, out)
        click.echo(f"\nPDF report saved: {out}")


# ---------------------------------------------------------------------------
# maneuver (v0.6) — collision avoidance maneuver planning
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--norad-id", required=True, type=int, help="Primary object NORAD ID")
@click.option("--secondary", required=True, type=int, help="Secondary object NORAD ID")
@click.option("--days", default=3, type=float, help="Screening window in days")
@click.option("--threshold", default=1e-4, type=float, help="Pc threshold (default: 1e-4)")
@click.option("--dv-max", default=1.0, type=float, help="Max delta-v in m/s (default: 1.0)")
def maneuver(
    norad_id: int,
    secondary: int,
    days: float,
    threshold: float,
    dv_max: float,
) -> None:
    """Plan collision avoidance maneuver for a conjunction."""
    asyncio.run(_maneuver_async(norad_id, secondary, days, threshold, dv_max))


async def _maneuver_async(
    norad_id: int,
    secondary_id: int,
    days: float,
    threshold: float,
    dv_max: float,
) -> None:
    from satguard.maneuver.planner import ManeuverPlanner

    click.echo("SatGuard Maneuver Planning")
    click.echo(f"{'=' * 50}")
    click.echo(f"Primary:    NORAD {norad_id}")
    click.echo(f"Secondary:  NORAD {secondary_id}")
    click.echo(f"Threshold:  Pc < {threshold:.1e}")
    click.echo(f"Max Δv:     {dv_max:.2f} m/s")
    click.echo()

    # Fetch TLEs
    click.echo("Fetching TLEs...")
    try:
        primary_tle = await fetch_tle_by_norad(norad_id)
        secondary_tle = await fetch_tle_by_norad(secondary_id)
    except Exception as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    click.echo(f"  Primary:   {primary_tle.name}")
    click.echo(f"  Secondary: {secondary_tle.name}")
    click.echo()

    # Screen for conjunctions
    click.echo("Screening for conjunctions...")
    primary_states = propagate_batch(primary_tle, days=days, step_seconds=60.0)
    sec_states = propagate_batch(
        secondary_tle, days=days, step_seconds=60.0, start=primary_tle.epoch_datetime,
    )
    events = screen_conjunctions(primary_states, sec_states, threshold_km=50.0)

    if not events:
        click.echo("No conjunctions found within screening window.")
        return

    click.echo(f"Found {len(events)} conjunction(s). Planning maneuver for closest...")
    event = events[0]  # Closest approach

    click.echo(f"\nConjunction:")
    click.echo(f"  TCA:       {event.tca.isoformat()}")
    click.echo(f"  Miss:      {event.miss_distance_km:.3f} km")
    click.echo(f"  Vrel:      {event.relative_velocity_km_s:.3f} km/s")

    # Plan maneuver
    planner = ManeuverPlanner(
        dv_range_ms=(0.01, dv_max),
        dv_steps=30,
        time_steps=30,
    )
    try:
        result = planner.plan(event, threshold_pc=threshold)
    except AssertionError as e:
        click.echo(f"\nERROR: {e}", err=True)
        sys.exit(1)

    click.echo(f"  Pc:        {result.original_pc:.2e}")
    click.echo()

    if not result.action_required:
        click.echo(f"NO ACTION REQUIRED — Pc ({result.original_pc:.2e}) < threshold ({threshold:.1e})")
        return

    click.echo(f"ACTION REQUIRED — Pc ({result.original_pc:.2e}) > threshold ({threshold:.1e})")

    if result.recommended:
        r = result.recommended
        click.echo(f"\nRECOMMENDED MANEUVER:")
        click.echo(f"  Δv:          {r.burn.delta_v_ms:.3f} m/s ({r.burn.direction})")
        click.echo(f"  Lead time:   {r.burn.time_before_tca_s/3600:.1f} hours before TCA")
        click.echo(f"  Displacement: {r.displacement.magnitude_km:.3f} km")
        click.echo(f"  Post-miss:   {r.post_miss_km:.3f} km (was {r.original_miss_km:.3f} km)")
        click.echo(f"  Post-Pc:     {r.post_pc:.2e} (was {r.original_pc:.2e})")
        reduction = r.original_pc / max(r.post_pc, 1e-30)
        click.echo(f"  Reduction:   {reduction:.0f}×")
    else:
        click.echo(f"\nWARNING: No maneuver found within Δv ≤ {dv_max:.2f} m/s "
                    f"that reduces Pc below {threshold:.1e}.")
        click.echo("Consider increasing --dv-max or adjusting the threshold.")

    # Show tradespace summary (top 5 options by increasing Δv)
    below = [o for o in result.options if o.post_pc <= threshold]
    if below:
        click.echo(f"\nTradespace: {len(below)} option(s) meet threshold")
        click.echo(f"{'Δv(m/s)':>10} {'Lead(h)':>10} {'Post-miss(km)':>14} {'Post-Pc':>12}")
        click.echo(f"{'─' * 50}")
        for opt in below[:5]:
            click.echo(
                f"{opt.burn.delta_v_ms:>10.3f} "
                f"{opt.burn.time_before_tca_s/3600:>10.1f} "
                f"{opt.post_miss_km:>14.3f} "
                f"{opt.post_pc:>12.2e}"
            )


# ---------------------------------------------------------------------------
# replay (v0.6) — historical replay of conjunction evolution
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--norad-ids", required=True, type=str, help="NORAD IDs (e.g., 25544,41335)",
)
@click.option("--history-dir", type=click.Path(), default=None, help="History directory")
@click.option("--plot", is_flag=True, help="Save replay plot as PNG")
def replay(norad_ids: str, history_dir: str | None, plot: bool) -> None:
    """Replay historical conjunction evolution from archived TLEs."""
    parts = norad_ids.split(",")
    if len(parts) != 2:
        click.echo("ERROR: --norad-ids must be two comma-separated integers", err=True)
        sys.exit(1)

    try:
        id_a, id_b = int(parts[0].strip()), int(parts[1].strip())
    except ValueError:
        click.echo("ERROR: NORAD IDs must be integers", err=True)
        sys.exit(1)

    from satguard.history.replay import replay_conjunction
    from satguard.history.store import HistoryStore

    hdir = Path(history_dir) if history_dir else None
    store = HistoryStore(base_dir=hdir)

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

        result = replay_conjunction(hist)

        click.echo(f"\nReplay: NORAD {na} vs {nb} (TCA ~{date_str})")
        click.echo(f"  Snapshots with TLEs: {len(result.timeline)}/{len(hist.snapshots)}")

        if not result.timeline:
            click.echo("  No snapshots have archived TLE data for replay.")
            continue

        click.echo(f"  Peak Pc:  {result.peak_pc:.2e}")
        click.echo(f"  Final Pc: {result.final_pc:.2e}")

        click.echo("\n  Time             | Miss(km) | Pc       | Stored Miss | Stored Pc | TLE Age P(h) | TLE Age S(h)")
        click.echo(f"  {'-' * 95}")
        for pt in result.timeline:
            click.echo(
                f"  {pt.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                f"{pt.miss_km:>8.3f} | {pt.pc:.2e} | "
                f"{pt.stored_miss_km:>11.3f} | {pt.stored_pc:.2e} | "
                f"{pt.tle_age_primary_h:>12.1f} | {pt.tle_age_secondary_h:>12.1f}"
            )

        if plot and len(result.timeline) > 1:
            _plot_replay(result, na, nb, date_str)


def _plot_replay(result, norad_a: int, norad_b: int, date_str: str) -> None:  # type: ignore[no-untyped-def]
    """Save a replay comparison plot."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        click.echo("  WARNING: matplotlib not available, skipping plot")
        return

    times = [pt.timestamp for pt in result.timeline]
    pcs_replay = [pt.pc for pt in result.timeline]
    pcs_stored = [pt.stored_pc for pt in result.timeline]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # Pc comparison
    ax1.semilogy(times, pcs_replay, "o-", color="tab:blue", label="Replayed Pc", linewidth=2)
    ax1.semilogy(times, pcs_stored, "s--", color="tab:orange", label="Stored Pc", linewidth=1)
    ax1.set_ylabel("Collision Probability")
    ax1.set_title(f"SatGuard Replay — NORAD {norad_a} vs {norad_b}")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Miss distance comparison
    miss_replay = [pt.miss_km for pt in result.timeline]
    miss_stored = [pt.stored_miss_km for pt in result.timeline]
    ax2.plot(times, miss_replay, "o-", color="tab:blue", label="Replayed Miss", linewidth=2)
    ax2.plot(times, miss_stored, "s--", color="tab:orange", label="Stored Miss", linewidth=1)
    ax2.set_ylabel("Miss Distance (km)")
    ax2.set_xlabel("Assessment Time (UTC)")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()

    fname = f"replay_{norad_a}_{norad_b}_{date_str}.png"
    fig.savefig(fname, dpi=150)
    plt.close(fig)
    click.echo(f"  Plot saved: {fname}")


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
