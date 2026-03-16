# Changelog

All notable changes to SatGuard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
