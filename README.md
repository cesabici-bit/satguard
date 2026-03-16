# SatGuard

Open-source conjunction assessment pipeline for space objects.

**TLE ingest → SGP4 propagation → conjunction screening → collision probability → CDM output**

SatGuard provides a complete Python toolkit for satellite conjunction assessment, implementing industry-standard algorithms (Foster, Chan, Alfano) with rigorous validation against published references (Vallado, Alfano 2005, NASA CARA).

## Features

- **TLE Parser** — Two-Line Element parsing with checksum validation
- **Catalog Ingest** — CelesTrak (no auth) and Space-Track.org (with credentials)
- **SGP4 Propagation** — High-fidelity orbit propagation via compiled sgp4 library
- **Conjunction Screening** — KDTree-based spatial indexing for O(N log N) screening
- **Collision Probability** — Three methods: Foster (2D integral), Chan (series expansion), Alfano (max Pc bounds)
- **Covariance Handling** — Default covariance models, 3D→2D encounter plane projection
- **CDM Output** — CCSDS Conjunction Data Message (KVN format)
- **CLI** — One-command screening: `satguard screen --norad-id 25544 --days 7`

## Installation

```bash
pip install satguard
```

Or for development:

```bash
git clone https://github.com/genius-lab/satguard.git
cd satguard
pip install -e ".[dev]"
```

Requires Python 3.12+.

## Quick Start

### CLI

Screen the ISS (NORAD 25544) for conjunctions over the next 3 days:

```bash
satguard screen --norad-id 25544 --days 3
```

With CDM output for each conjunction:

```bash
satguard screen --norad-id 25544 --days 7 --threshold 50 --output-cdm
```

### Python API

```python
from satguard import (
    parse_tle, propagate_batch, screen,
    foster_pc, default_covariance, write_cdm,
)
from satguard.covariance.realism import project_to_encounter_plane

# 1. Parse TLEs
tle_primary = parse_tle(tle_string_primary)
tle_secondary = parse_tle(tle_string_secondary)

# 2. Propagate orbits (3 days, 60s steps)
states_p = propagate_batch(tle_primary, days=3.0, step_seconds=60.0)
states_s = propagate_batch(tle_secondary, days=3.0, step_seconds=60.0)

# 3. Screen for conjunctions
events = screen(states_p, states_s, threshold_km=50.0)

# 4. Compute collision probability
if events:
    event = events[0]
    cov_2d = project_to_encounter_plane(
        default_covariance("LEO"), default_covariance("LEO"),
        event.r_primary, event.v_primary,
        event.r_secondary, event.v_secondary,
    )
    pc = foster_pc(event.miss_distance_km, cov_2d, hard_body_radius=0.02)
    print(f"Pc = {pc:.2e}")

    # 5. Generate CDM
    cdm = write_cdm(event, pc)
    print(cdm)
```

### CelesTrak Catalog

```python
import asyncio
from satguard import fetch_catalog, fetch_tle_by_norad

# Fetch a single object
tle = asyncio.run(fetch_tle_by_norad(25544))  # ISS
print(f"{tle.name} — inclination: {tle.inclination_deg:.1f}°")

# Fetch full active catalog
catalog = asyncio.run(fetch_catalog("active"))
print(f"{len(catalog)} active objects")
```

## CLI Reference

```
satguard screen [OPTIONS]

Options:
  --norad-id INTEGER  NORAD catalog number of primary object [required]
  --days FLOAT        Screening window in days (default: 3)
  --threshold FLOAT   Distance threshold in km (default: 50)
  --step FLOAT        Propagation step in seconds (default: 60)
  --output-cdm        Output CDM for each conjunction
  --help              Show this message and exit.
```

## Example Output

```
SatGuard Conjunction Screening
========================================
Primary object:   NORAD 25544
Window:           3.0 days
Threshold:        50.0 km
Step:             60 s

Fetching primary TLE from CelesTrak...
  Object: ISS (ZARYA)
  Epoch:  2024-02-14T12:25:11

Propagating primary orbit...
  Generated 4320 state vectors

Fetching active catalog from CelesTrak...
  Catalog: 8432 objects

Screening...

Results: 5 conjunction(s) found
============================================================

  [1] NORAD 25544 vs 41335
      TCA:           2024-02-15T08:12:33
      Miss distance: 12.847 km
      Rel. velocity: 14.221 km/s
      Pc (Foster):   2.31e-06
```

## Collision Probability Methods

| Method | Reference | Best For |
|--------|-----------|----------|
| **Foster** | Foster & Estes 1992 | Standard 2D Pc, isotropic covariance |
| **Chan** | Chan 2008, AIAA J. | Anisotropic covariance, series expansion |
| **Alfano** | Alfano 2005, AAS | Upper/lower bounds, quick screening |

## Validation

SatGuard is validated at 5 levels with 118 tests:

| Level | Description | Count |
|-------|-------------|-------|
| **L1** Unit | Core function behavior | 95 |
| **L2** Domain | Values from external sources (Vallado, Alfano, NASA CARA) | ~15 |
| **L3** Property | Hypothesis-based invariant testing | 11 |
| **L4** Snapshot | Golden output approved by human review | 1 |
| **L5** External | Cross-validation vs Chan 2008, NASA CARA, real CSMs | 12 |

Run all checks:

```bash
make check-all    # mypy + ruff + pytest + smoke test
pytest tests/ -v  # tests only
```

## Project Structure

```
satguard/
├── src/satguard/
│   ├── catalog/       # TLE parsing, CelesTrak & Space-Track ingest
│   ├── propagate/     # SGP4 orbit propagation
│   ├── screen/        # KDTree conjunction screening
│   ├── assess/        # Collision probability (Foster, Chan, Alfano)
│   ├── covariance/    # Covariance models & projection
│   ├── cdm/           # CCSDS CDM writer
│   └── cli/           # Click CLI
├── tests/             # 118 tests across 5 validation levels
└── verify/            # Two-tool cross-verification
```

## References

- Vallado, D.A. *Fundamentals of Astrodynamics and Applications*, 5th ed.
- Alfano, S. (2005). "A Numerical Implementation of Spherical Object Collision Probability." *AAS/AIAA*.
- Chan, F.K. (2008). *Spacecraft Collision Probability*. AIAA.
- Foster, J.L. & Estes, H.S. (1992). "A Parametric Analysis of Orbital Debris Collision Probability." NASA JSC-25898.
- CCSDS 508.0-B-1: Conjunction Data Message standard.

## License

MIT — see [LICENSE](LICENSE).
