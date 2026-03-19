# Status — SatGuard

## Fase Corrente
v0.5.1 — Vectorized fleet screening — Implementata, test verdi.

## Ultimo Subtask Completato (v0.5.1)
- S0: Nuovo modulo `screen/vectorized.py` — SatrecArray + KDTree logica estratta da app.py
- S1: Riscritto `fleet/batch.py` — screen_fleet() ora usa vectorized_screen() con primary_ids filter
- S2: Riscritto `api/app.py:_compute_conjunctions()` — delega a vectorized_screen(), ~200 LOC rimossi
- S3: 225 passed, 1 skipped — 0 regressioni. ruff clean, mypy clean.
- Performance: fleet screening ora propaga TUTTO il catalogo in 1 chiamata C (SatrecArray) anziché loop Python per ~14K oggetti

## Prossimo Subtask
- v0.6: Maneuver planning + historical replay

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
| Vectorized Screen | `src/satguard/screen/vectorized.py` | OK (v0.5.1) — shared SatrecArray+KDTree |
| API App | `src/satguard/api/app.py` | OK (v0.5.1) — delegates to vectorized |
| API Cache | `src/satguard/api/cache.py` | OK (v0.3) |
| Globe 3D | `web/src/components/Globe.tsx` | OK (v0.4) — siblings, arcs, heatmap |
| ObjectInspector | `web/src/components/ObjectInspector.tsx` | OK (v0.4) — siblings, View 3D |
| FilterPanel | `web/src/components/FilterPanel.tsx` | OK (v0.4) — heatmap toggle |
| TimeControls | `web/src/components/TimeControls.tsx` | OK (v0.4) — time slider |
| ConjunctionBrowser | `web/src/components/ConjunctionBrowser.tsx` | OK (v0.4) |
| Siblings util | `web/src/utils/siblings.ts` | OK (v0.4) |
| Heatmap util | `web/src/utils/heatmap.ts` | OK (v0.4) — gaussian canvas |

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
- 2026-03-19 (sessione 6): v0.4 Globe Enhanced. 4 frontend features (siblings, conjunction 3D arcs, heatmap mode, time slider) + ConjunctionBrowser panel + backend rewrite (all-on-all SatrecArray vectorized screening, sibling/co-orbiting filters). 50 real unique conjunctions found. 177 test invariati.
- 2026-03-19 (sessione 7): v0.4.1. Background pre-compute + cache TTL 1h + fix heatmap (fromUrl async). Verifica browser completa di tutte le feature. 199 test.
- 2026-03-19 (sessione 8): v0.5.1. Extracted vectorized SatrecArray screening into shared module (screen/vectorized.py). fleet/batch.py and api/app.py both delegate to it. 225 test.
