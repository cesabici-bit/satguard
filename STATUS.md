# Status — SatGuard

## Fase Corrente
v0.4 — Globe Enhanced — Implementata.

## Ultimo Subtask Completato (v0.4)
- S0: Esteso types (CatalogEntry.intl_designator, FilterState.showHeatmap)
- S1: Sibling index utility (buildSiblingIndex, getSiblings)
- S2: Sibling highlighting nel Globe (celeste, size 8)
- S3: Siblings list in ObjectInspector (max 20, cliccabili)
- S4: Conjunction 3D arc view (polyline ±10min TCA, miss distance label)
- S5: Heatmap continua gaussiana (canvas 1024x512, SingleTileImageryProvider)
- S6: Time slider (±24h, tick labels, pausa su drag)
- ConjunctionBrowser: pannello collapsibile con tutte le congiunzioni ordinate per rischio
- Backend: all-on-all screening con SatrecArray vettorizzato (~2min, cached 10min)
- Filtri: siblings (intl_designator[:5]) + co-orbiting (vrel < 0.5 km/s)
- Loading indicator: "Calculating conjunctions..." con tempo
- check-all: 177 passed, 1 skipped
- Frontend: TypeScript clean, Vite build OK

## Prossimo Subtask
- Pre-calcolo congiunzioni all'avvio server (background task)
- Aumentare TTL cache congiunzioni a 1h
- v0.5: Constellation batch + fleet.yaml + report PDF

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
| API App | `src/satguard/api/app.py` | OK (v0.4) — all-on-all SatrecArray |
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
