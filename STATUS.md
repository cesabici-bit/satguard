# Status — SatGuard

## Fase Corrente
v0.2 — Automazione Monitoraggio — Completata.

## Ultimo Subtask Completato
- S1: Covariance Assessment (assess_covariance, scale_covariance, CovarianceAssessment)
- S2: History Store (PcSnapshot, ConjunctionHistory, HistoryStore — JSON persistence)
- S3: Pc Evolution Analysis (PcTrend, pc_trend, time_to_threshold)
- S4: Alert Rules (AlertConfig, load_config, should_alert — TOML config)
- S5: Webhook Dispatcher (send_alert — async httpx POST, 5s timeout, fire-and-forget)
- S6: CLI Commands (watch, history, alert-test + screen --record/--assess-covariance)
- S7: Smoke Test v0.2 (full pipeline: screen -> record -> evolution -> alert)
- S8: Project files (CHANGELOG, STATUS, README, pyproject.toml v0.2.0)
- check-all: 161 passed, 1 skipped, mypy 0 errors (25 files), ruff 0 errors

## Prossimo Subtask
v0.3: Globe 3D (CesiumJS) — 30K+ oggetti su globo interattivo

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

## Test Coverage per Livello
| Livello | File | # Test |
|---------|------|--------|
| L1 Unit | test_tle_parser, test_propagation, test_screening, test_covariance, test_collision_prob, test_cdm, test_celestrak, test_spacetrack, test_covariance_realism, test_history, test_alert | ~120 |
| L2 Domain | sparsi (# SOURCE:) | ~15 |
| L3 Property | test_property.py | 11 |
| L4 Snapshot | tests/snapshots/golden_smoke.txt | 1 (approvato) |
| L5 Validation | test_validation.py | 12 |

## Log Sessioni
- 2026-03-13 (sessione 1): F0+F1 completate. Setup + ricerca dipendenze.
- 2026-03-13 (sessione 2): F3 MVP (12 subtask) + F4 Verifica (L3/L4/L5). 118 test verdi.
- 2026-03-13 (sessione 3): F5 Deploy & Publish. README, LICENSE, CHANGELOG, CI GitHub Actions.
- 2026-03-18 (sessione 4): v0.2 completa. 8 subtask, 43 nuovi test (161 totali). Cov assessment, history, alerts, CLI watch/history/alert-test.
