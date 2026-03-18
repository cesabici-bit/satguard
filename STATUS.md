# Status — SatGuard

## Fase Corrente
v0.3 — Globe 3D (CesiumJS) — Implementata.

## Ultimo Subtask Completato
- S0: Setup progetto (FastAPI backend + React/Vite/Cesium frontend scaffolding)
- S1: FastAPI /api/catalog endpoint con cache TTL 1h, orbit classification
- S2: FastAPI /api/conjunctions + /api/objects/{id} endpoints
- S3: Globe 3D con 30K+ dots (PointPrimitiveCollection + satellite.js client-side propagation)
- S4: Click-to-inspect (ObjectInspector panel con dettagli orbitali)
- S5: Conjunction overlay (polyline colorate per Pc)
- S6: FilterPanel (LEO/MEO/GEO/OTHER checkboxes + search) + TimeControls (play/pause/speed)
- S7: CLI `satguard serve --port 8000` command
- check-all: 177 passed, 1 skipped, mypy 0 errors (28 files), ruff 0 errors
- Frontend: TypeScript clean, Vite build OK

## Prossimo Subtask
S8: Polish e release (bump version, CHANGELOG, README update, verifica manuale browser)

## Blockers
Nessuno

## Note Tecniche
- TLE checksum: sum(digits) + count('-'), mod 10
- sgp4 usa WGS72 di default (raccomandato per TLE)
- Covarianza empirica NASA CARA (1 km LEO) — TLE non ha covarianza reale
- Pc cross-validation: Foster vs Chan entro 5% (isotropico), entro 10% (anisotropico)
- History: JSON files in ~/.satguard/history/, one per conjunction pair per TCA date
- Alerts: webhook POST only, TOML config, cooldown-based dedup
- datetime: always UTC, ISO 8601 with Z suffix

## Moduli Implementati
| Modulo | File | Status |
|--------|------|--------|
| TLE Parser | `src/satguard/catalog/tle.py` | OK |
| CelesTrak | `src/satguard/catalog/celestrak.py` | OK |
| Space-Track | `src/satguard/catalog/spacetrack.py` | OK |
| SGP4 Propagation | `src/satguard/propagate/sgp4.py` | OK |
| Screening | `src/satguard/screen/screener.py` | OK |
| Covariance | `src/satguard/covariance/realism.py` | OK |
| Cov Assessment | `src/satguard/covariance/realism.py` | OK (v0.2) |
| Foster Pc | `src/satguard/assess/foster.py` | OK |
| Chan Pc | `src/satguard/assess/chan.py` | OK |
| Alfano Pc | `src/satguard/assess/alfano.py` | OK |
| CDM Writer | `src/satguard/cdm/writer.py` | OK |
| History Store | `src/satguard/history/store.py` | OK (v0.2) |
| Pc Evolution | `src/satguard/history/evolution.py` | OK (v0.2) |
| Alert Rules | `src/satguard/alert/rules.py` | OK (v0.2) |
| Webhook | `src/satguard/alert/webhook.py` | OK (v0.2) |
| CLI | `src/satguard/cli/main.py` | OK |
| API App | `src/satguard/api/app.py` | OK (v0.3) |
| API Cache | `src/satguard/api/cache.py` | OK (v0.3) |
| Globe 3D | `web/src/components/Globe.tsx` | OK (v0.3) |
| ObjectInspector | `web/src/components/ObjectInspector.tsx` | OK (v0.3) |
| FilterPanel | `web/src/components/FilterPanel.tsx` | OK (v0.3) |
| TimeControls | `web/src/components/TimeControls.tsx` | OK (v0.3) |

## Test Coverage per Livello
| Livello | File | # Test |
|---------|------|--------|
| L1 Unit | test_tle_parser, test_propagation, test_screening, test_covariance, test_collision_prob, test_cdm, test_celestrak, test_spacetrack, test_covariance_realism, test_history, test_alert, test_api | ~136 |
| L2 Domain | sparsi (# SOURCE:) | ~15 |
| L3 Property | test_property.py | 11 |
| L4 Snapshot | tests/snapshots/golden_smoke.txt | 1 (approvato) |
| L5 Validation | test_validation.py | 12 |

## Log Sessioni
- 2026-03-13 (sessione 1): F0+F1 completate. Setup + ricerca dipendenze.
- 2026-03-13 (sessione 2): F3 MVP (12 subtask) + F4 Verifica (L3/L4/L5). 118 test verdi.
- 2026-03-13 (sessione 3): F5 Deploy & Publish. README, LICENSE, CHANGELOG, CI GitHub Actions.
- 2026-03-18 (sessione 4): v0.2 completa. 8 subtask, 43 nuovi test (161 totali). Cov assessment, history, alerts, CLI watch/history/alert-test.
- 2026-03-18 (sessione 5): v0.3 Globe 3D. FastAPI backend (3 endpoints), React+CesiumJS frontend (PointPrimitiveCollection 30K+, satellite.js client-side propagation, click-to-inspect, conjunction overlay, filters, time controls). 16 nuovi test (177 totali). CLI `serve` command.
