# Status — SatGuard

## Fase Corrente
v1.0.0 — Stable Release. mypy clean, ruff clean, 254 test verdi.

## Ultimo Subtask Completato (v1.0.0)
- Fixed 8 mypy errors + 15 ruff errors
- Bump versione 1.0.0, classifier Beta
- CHANGELOG + README completi
- 254 tests passing, 1 skipped, 0 regressions

## Prossimo Subtask
- Da decidere con utente (Rust core, space weather, ML prediction)

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
- CW equations: valid for e < 0.05, burn-to-TCA < 1 orbital period
- Maneuver planning: tradespace (dv × time) → min-fuel that meets Pc threshold
- Historical replay: re-propagates archived TLEs → timeline of recomputed miss/Pc

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
| History Store | `src/satguard/history/store.py` | OK (v0.6 — +TLE fields) |
| Pc Evolution | `src/satguard/history/evolution.py` | OK (v0.2) |
| Historical Replay | `src/satguard/history/replay.py` | OK (v0.6) |
| CW Equations | `src/satguard/maneuver/cw.py` | OK (v0.6) |
| Maneuver Planner | `src/satguard/maneuver/planner.py` | OK (v0.6) |
| Alert Rules | `src/satguard/alert/rules.py` | OK (v0.2) |
| Webhook | `src/satguard/alert/webhook.py` | OK (v0.2) |
| CLI | `src/satguard/cli/main.py` | OK (v0.6 — +maneuver, +replay) |
| Vectorized Screen | `src/satguard/screen/vectorized.py` | OK (v0.5.1) |
| API App | `src/satguard/api/app.py` | OK (v0.6 — +POST maneuver, +GET replay) |
| API Cache | `src/satguard/api/cache.py` | OK (v0.3) |
| Globe 3D | `web/src/components/Globe.tsx` | OK (v0.4) |
| ObjectInspector | `web/src/components/ObjectInspector.tsx` | OK (v0.4) |
| FilterPanel | `web/src/components/FilterPanel.tsx` | OK (v0.4) |
| TimeControls | `web/src/components/TimeControls.tsx` | OK (v0.4) |
| ConjunctionBrowser | `web/src/components/ConjunctionBrowser.tsx` | OK (v0.4) |
| Siblings util | `web/src/utils/siblings.ts` | OK (v0.4) |
| Heatmap util | `web/src/utils/heatmap.ts` | OK (v0.4) |

## Test Coverage per Livello
| Livello | File | # Test |
|---------|------|--------|
| L1 Unit | test_tle_parser, test_propagation, test_screening, test_covariance, test_collision_prob, test_cdm, test_celestrak, test_spacetrack, test_covariance_realism, test_history, test_alert, test_api, test_maneuver, test_replay | ~158 |
| L2 Domain | sparsi (# SOURCE:) — Curtis Ch.7, NASA CARA, Alfano 2005 | ~18 |
| L3 Property | test_property.py + test_maneuver.py (CW) | 13 |
| L4 Snapshot | tests/snapshots/golden_smoke.txt | 1 (approvato) |
| L5 Validation | test_validation.py | 12 |

## M4 Verification
| Script | Method A | Method B | Result |
|--------|----------|----------|--------|
| `verify/cw_comparison.py` | CW analytical | Hill numerical (solve_ivp) | 7/7 PASS, <0.001% error |

## Log Sessioni
- 2026-03-13 (sessione 1): F0+F1 completate. Setup + ricerca dipendenze.
- 2026-03-13 (sessione 2): F3 MVP (12 subtask) + F4 Verifica (L3/L4/L5). 118 test verdi.
- 2026-03-13 (sessione 3): F5 Deploy & Publish. README, LICENSE, CHANGELOG, CI GitHub Actions.
- 2026-03-18 (sessione 4): v0.2 completa. 8 subtask, 43 nuovi test (161 totali). Cov assessment, history, alerts, CLI watch/history/alert-test.
- 2026-03-18 (sessione 5): v0.3 Globe 3D. FastAPI backend (3 endpoints), React+CesiumJS frontend (PointPrimitiveCollection 30K+, satellite.js client-side propagation, click-to-inspect, conjunction overlay, filters, time controls). 16 nuovi test (177 totali). CLI `serve` command.
- 2026-03-19 (sessione 6): v0.4 Globe Enhanced. 4 frontend features (siblings, conjunction 3D arcs, heatmap mode, time slider) + ConjunctionBrowser panel + backend rewrite (all-on-all SatrecArray vectorized screening, sibling/co-orbiting filters). 50 real unique conjunctions found. 177 test invariati.
- 2026-03-19 (sessione 7): v0.4.1. Background pre-compute + cache TTL 1h + fix heatmap (fromUrl async). Verifica browser completa di tutte le feature. 199 test.
- 2026-03-19 (sessione 8): v0.5.1. Extracted vectorized SatrecArray screening into shared module (screen/vectorized.py). fleet/batch.py and api/app.py both delegate to it. 225 test.
- 2026-03-19 (sessione 9): v0.6.0. Maneuver planning (CW linearized) + historical replay. 8 new files, 29 new tests (254 totali). M4 verification: CW vs Hill 7/7 PASS.
- 2026-03-19 (sessione 10): v1.0.0 release. Fix 8 mypy + 15 ruff errors. CHANGELOG/README completi. Bump 1.0.0.
