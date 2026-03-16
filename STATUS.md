# Status — SatGuard

## Fase Corrente
F5 Deploy & Publish — Completata.

## Ultimo Subtask Completato
- README.md con installazione, uso, API, CLI reference, output esempio, validation summary
- LICENSE (MIT)
- CHANGELOG.md (v0.1.0)
- .github/workflows/ci.yml (Python 3.12 + 3.13, mypy + ruff + pytest)
- check-all verificato: 118 passed, 1 skipped, mypy 0, ruff 0

## Prossimo Subtask
Pronto per pubblicazione su GitHub. Attendere OK utente per push.

## Blockers
Nessuno

## Note Tecniche
- TLE checksum: sum(digits) + count('-'), mod 10
- sgp4 usa WGS72 di default (raccomandato per TLE)
- Covarianza empirica NASA CARA (1 km LEO) — TLE non ha covarianza reale
- Pc cross-validation: Foster vs Chan entro 5% (isotropico), entro 10% (anisotropico)
- Chan diverge quando HBR >> sigma (non regime operativo)
- NASA CARA Omitron case: match entro 20% (proiezione 3D->2D)
- Precessione nodale: RAAN cambia ~5 deg/giorno per ISS (J2). Screening deve essere periodico
- Windows: encoding cp1252, evitare caratteri Unicode non-ASCII in print()

## Moduli Implementati
| Modulo | File | Status |
|--------|------|--------|
| TLE Parser | `src/satguard/catalog/tle.py` | OK |
| CelesTrak | `src/satguard/catalog/celestrak.py` | OK |
| Space-Track | `src/satguard/catalog/spacetrack.py` | OK |
| SGP4 Propagation | `src/satguard/propagate/sgp4.py` | OK |
| Screening | `src/satguard/screen/screener.py` | OK |
| Covariance | `src/satguard/covariance/realism.py` | OK |
| Foster Pc | `src/satguard/assess/foster.py` | OK |
| Chan Pc | `src/satguard/assess/chan.py` | OK |
| Alfano Pc | `src/satguard/assess/alfano.py` | OK |
| CDM Writer | `src/satguard/cdm/writer.py` | OK |
| CLI | `src/satguard/cli/main.py` | OK |

## Test Coverage per Livello
| Livello | File | # Test |
|---------|------|--------|
| L1 Unit | test_tle_parser, test_propagation, test_screening, test_covariance, test_collision_prob, test_cdm, test_celestrak, test_spacetrack | 95 |
| L2 Domain | sparsi (# SOURCE:) | ~15 |
| L3 Property | test_property.py | 11 |
| L4 Snapshot | tests/snapshots/golden_smoke.txt | 1 (approvato) |
| L5 Validation | test_validation.py | 12 |

## Log Sessioni
- 2026-03-13 (sessione 1): F0+F1 completate. Setup + ricerca dipendenze.
- 2026-03-13 (sessione 2): F3 MVP (12 subtask) + F4 Verifica (L3/L4/L5). 118 test verdi.
- 2026-03-13 (sessione 3): F5 Deploy & Publish. README, LICENSE, CHANGELOG, CI GitHub Actions.
