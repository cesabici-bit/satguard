# Changelog

All notable changes to SatGuard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-19

### Changed

- First stable release
- Development Status: Alpha → Beta
- Fixed all mypy (8) and ruff (15) errors across codebase
- Comprehensive README and CHANGELOG covering all features v0.1–v0.6
- 254 tests passing, mypy clean, ruff clean

## [0.6.0] - 2026-03-19

### Added

- **CW equations**: Clohessy-Wiltshire linearized relative motion (`maneuver/cw.py`) — mean_motion, orbital_period, cw_displacement, sma_from_position, eccentricity_from_state
- **Maneuver planner**: Tradespace search (dv × time grid) → minimum-fuel recommendation meeting Pc threshold (`maneuver/planner.py`)
- **Historical replay**: Re-propagate archived TLEs to compute timeline of recomputed miss distance and Pc (`history/replay.py`)
- **PcSnapshot TLE fields**: Backward-compatible JSON extension storing TLE lines for replay
- **CLI `satguard maneuver`**: Plan avoidance maneuver for a conjunction pair
- **CLI `satguard replay`**: Replay historical conjunction from archived TLEs
- **API `POST /api/maneuver`**: Maneuver planning endpoint
- **API `GET /api/replay/{a}/{b}`**: Historical replay endpoint
- **CLI `--record` TLE archiving**: `screen`/`watch` now archive TLE lines in PcSnapshot
- **M4 verification**: CW analytical vs Hill numerical integration — 7/7 PASS, <0.001% error (`verify/cw_comparison.py`)

### Changed

- Bumped version to 0.6.0
- Total tests: 254 passed (from 225)

## [0.5.1] - 2026-03-19

### Changed

- **Vectorized screening extraction**: Shared `screen/vectorized.py` module used by both `fleet/batch.py` and `api/app.py`
- Fleet screening performance: hours → 29 seconds via SatrecArray vectorization
- Total tests: 225 (unchanged)

## [0.5.0] - 2026-03-19

### Added

- **Fleet batch screening**: Screen entire constellation from `fleet.yaml` config file
- **FleetConfig parser**: YAML-based constellation definition with per-object thresholds
- **PDF report generation**: Conjunction summary with risk matrix (`report/pdf.py`, fpdf2)
- **CLI `satguard fleet`**: Batch screen a constellation
- **CLI `satguard report`**: Generate PDF report from screening results

### Changed

- Bumped version to 0.5.0
- Added `fpdf2` and `PyYAML` dependencies
- Total tests: 225 passed (from 199)

## [0.4.1] - 2026-03-19

### Fixed

- **Heatmap DeveloperError**: Migrated to `SingleTileImageryProvider.fromUrl()` async API (Cesium 1.139 breaking change)
- 5 bugs found and fixed in v0.4 audit (start_epoch, heatmap color, Pc validation, version, perf)

### Added

- **18 audit tests**: `test_v04_audit.py` covering conjunction sanity, siblings logic, orbit classification, background pre-compute

### Changed

- Background pre-compute for conjunctions on API startup (lifespan event)
- Cache TTL increased to 1 hour for conjunctions
- Total tests: 199 passed (from 177)

## [0.4.0] - 2026-03-19

### Added

- **Siblings detection**: Filter co-orbiting objects (same `intl_designator` prefix) from conjunction results
- **Conjunction 3D arcs**: Glowing polylines between at-risk pairs in globe view
- **Heatmap mode**: Density overlay showing conjunction hotspots on the globe
- **Time slider**: Scrub through simulation time with playback controls
- **ConjunctionBrowser panel**: Browse, sort, and filter all conjunctions in sidebar
- **All-on-all vectorized screening**: SatrecArray-based screening producing real unique conjunctions
- **Co-orbiting velocity filter**: Filter out pairs with relative velocity < 0.5 km/s

### Changed

- Bumped version to 0.4.0
- Total tests: 177 (unchanged, audit added in v0.4.1)

## [0.3.0] - 2026-03-18

### Added

- **Globe 3D**: Interactive CesiumJS globe with 30K+ satellites rendered in real-time via PointPrimitiveCollection + satellite.js client-side SGP4 propagation
- **FastAPI backend**: Three REST endpoints — `GET /api/catalog` (active catalog with orbit classification, 1h TTL cache), `GET /api/conjunctions` (top 50 pre-computed, 10min cache), `GET /api/objects/{id}` (orbital elements + derived params)
- **Click-to-inspect with fly-to**: Click any satellite dot or search by name/NORAD ID → smooth camera transition + detail panel with identification, orbital elements, derived parameters
- **Collision risk panel**: ObjectInspector shows all conjunction risks for selected object with Pc, miss distance, relative velocity, TCA, and clickable links to partner objects
- **Orbit type filters**: Checkbox toggles for LEO/MEO/GEO/OTHER with neon color coding (green/magenta/gold/cyan)
- **Time controls**: Play/pause, speed multiplier (1x/10x/60x/600x), simulation clock display, reset-to-now
- **Conjunction overlay**: Glowing polylines between at-risk pairs, colored by Pc severity (red/orange/yellow)
- **Auto-rotate camera**: Slow globe rotation that pauses on user interaction
- **CLI `satguard serve`**: Single command to start API server (`satguard serve --port 8000`)
- **Dark globe theme**: CARTO Dark Matter basemap for maximum satellite dot visibility
- **16 new API tests**: FastAPI TestClient with mocked catalog data

### Changed

- Bumped version to 0.3.0
- Added `fastapi` and `uvicorn[standard]` to dependencies
- Total tests: 177 passed (from 161)

## [0.2.0] - 2026-03-18

### Added

- **Covariance realism assessment**: `assess_covariance()` evaluates matrix quality (eigenvalue ratio, condition number, PD check) with REALISTIC/SUSPECT/DEFAULT flags. `scale_covariance()` for sensitivity analysis
- **Pc history tracking**: JSON-based persistence (`~/.satguard/history/`) stores Pc snapshots per conjunction pair with deduplication and chronological ordering
- **Pc evolution analysis**: `pc_trend()` detects RISING/FALLING/STABLE trends; `time_to_threshold()` estimates threshold crossing via linear extrapolation
- **Alert system**: TOML-based config (`~/.satguard/config.toml`) with `should_alert()` logic (threshold, cooldown, new/rising detection) and async webhook dispatcher (Slack/Discord/Teams compatible)
- **CLI `watch`**: Screen + record + alert in one command (`satguard watch --norad-id 25544`)
- **CLI `history`**: Show Pc evolution with optional matplotlib plot (`satguard history --norad-ids 25544,41335 --plot`)
- **CLI `alert-test`**: Test webhook delivery (`satguard alert-test --config path`)
- **CLI `screen` enhancements**: `--record` flag to save results, `--assess-covariance` flag to show matrix quality

### Changed

- Bumped version to 0.2.0
- Total tests: 161 passed (from 118)

## [0.1.0] - 2026-03-13

### Added

- **TLE Parser**: Two-Line Element format parsing with checksum validation
- **CelesTrak ingest**: Fetch TLEs by NORAD ID or full catalog (active, stations, etc.)
- **Space-Track ingest**: Authenticated access to Space-Track.org catalog
- **SGP4 propagation**: Batch orbit propagation with configurable time step
- **Conjunction screening**: KDTree-based O(N log N) spatial indexing
- **Collision probability**: Foster (2D integral), Chan (series expansion), Alfano (max Pc bounds)
- **Covariance handling**: Default LEO/MEO/GEO models, 3D→2D encounter plane projection
- **CDM writer**: CCSDS Conjunction Data Message output (KVN format)
- **CLI**: `satguard screen --norad-id XXXXX --days N` command
- **Python API**: Full programmatic access via `satguard` package
- **Validation**: 118 tests across 5 levels (L1-L5), including cross-validation vs Chan 2008 and NASA CARA
