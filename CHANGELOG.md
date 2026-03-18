# Changelog

All notable changes to SatGuard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
