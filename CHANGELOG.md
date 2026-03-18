# Changelog

All notable changes to SatGuard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
