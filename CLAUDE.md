# CLAUDE.md — SatGuard

## Progetto
**SatGuard** — Open-source conjunction assessment pipeline + 3D orbital visualization

## Obiettivo
Pipeline Python end-to-end: TLE ingest → orbit propagation → conjunction screening → collision probability → CDM output + globe 3D interattivo con tutti gli oggetti in orbita (CesiumJS).

## Stack Tecnico

| Componente | Tecnologia | Versione | Motivo |
|-----------|-----------|---------|--------|
| Core library | Python | 3.12+ | Ecosistema scientifico, target audience |
| Propagazione | sgp4 | latest | Implementazione ufficiale C++ compilata |
| Calcolo numerico | NumPy + SciPy | latest | Standard scientifico |
| Spatial indexing | scipy.spatial.KDTree | - | Screening O(N log N) |
| Visualizzazione 2D | Matplotlib | latest | Plot orbite, Pc evolution |
| Globe 3D | CesiumJS | latest | Standard geospaziale, usato da NASA/ESA |
| Web frontend | React + Resium | latest | Binding React per CesiumJS |
| API backend | FastAPI | latest | Serve dati al globe |
| Test PBT | Hypothesis | 6.151.9 | Property-based testing |
| Test runner | pytest | latest | Standard Python |
| Linter | ruff | latest | Fast Python linter |
| Types | mypy | latest | Static type checking |

> IMPORTANT: ogni dipendenza DEVE avere entry verificata in `verified-deps.toml`

## Architettura

```
satguard/
├── CLAUDE.md
├── verified-deps.toml
├── KNOWN_ISSUES.md
├── STATUS.md
├── Makefile
├── pyproject.toml
├── src/
│   └── satguard/
│       ├── __init__.py
│       ├── catalog/          # Ingest TLE/CDM da Space-Track, CelesTrak
│       │   ├── __init__.py
│       │   ├── spacetrack.py
│       │   ├── celestrak.py
│       │   └── tle.py        # TLE parser
│       ├── propagate/        # SGP4 + propagazione numerica
│       │   ├── __init__.py
│       │   └── sgp4.py
│       ├── screen/           # Conjunction screening con spatial indexing
│       │   ├── __init__.py
│       │   └── screener.py
│       ├── assess/           # Collision probability (Foster, Chan, Alfano, MC)
│       │   ├── __init__.py
│       │   ├── foster.py
│       │   ├── chan.py
│       │   ├── alfano.py
│       │   └── monte_carlo.py
│       ├── cdm/              # CDM generation (CCSDS format)
│       │   ├── __init__.py
│       │   └── writer.py
│       ├── covariance/       # Covariance realism assessment
│       │   ├── __init__.py
│       │   └── realism.py
│       └── cli/              # CLI entrypoint
│           ├── __init__.py
│           └── main.py
├── tests/
│   ├── test_tle_parser.py
│   ├── test_propagation.py
│   ├── test_screening.py
│   ├── test_collision_prob.py
│   ├── test_cdm.py
│   └── test_smoke.py         # Smoke test E2E (M3)
├── verify/                   # M4: Two-tool verification
│   └── orekit_comparison.py  # Confronto con Orekit (se disponibile)
└── web/                      # Globe 3D (v0.3+)
    ├── package.json
    └── src/
        ├── App.tsx
        ├── Globe.tsx
        ├── ObjectInspector.tsx
        └── ConjunctionView.tsx
```

## MVP Scope

### IN (MVP)
- [ ] TLE parser (Two-Line Element format)
- [ ] Ingest da CelesTrak (no login required)
- [ ] Ingest da Space-Track.org (con credenziali)
- [ ] Propagazione SGP4 (libreria sgp4)
- [ ] Conjunction screening con KDTree
- [ ] Collision probability: Foster, Chan, Alfano
- [ ] Monte Carlo validation
- [ ] CDM output (CCSDS KVN format)
- [ ] CLI: `satguard screen --norad-id XXXXX --days 7`
- [ ] API Python: `sg.Catalog`, `sg.screen()`, `sg.CollisionProb`

### OUT (post-MVP)
- Globe 3D CesiumJS (v0.3)
- Constellation management + fleet.yaml (v0.5)
- Maneuver planning (v0.6)
- Pc evolution tracking (v0.2)
- Alert webhook/email (v0.2)
- Covariance realism assessment (v0.2)
- Report PDF (v0.5)
- Historical replay (v0.6)
- Core Rust (quando necessario)
- Integrazione space weather
- ML-based prediction

## Roadmap

| Versione | Cosa | Valore |
|----------|------|--------|
| **v0.1 (MVP)** | Library: ingest + SGP4 + screen + Pc (3 metodi) + CDM | Conjunction assessment in Python |
| **v0.2** | CLI + alert + covariance assessment + Pc evolution | Automazione monitoraggio |
| **v0.3** | **Globe 3D (CesiumJS)**: 30K+ oggetti, click to inspect, filtri | **Momento virale** |
| **v0.4** | Globe: conjunction view 3D, heatmap, time slider, siblings | Didattica e wow |
| **v0.5** | Constellation batch + fleet.yaml + report PDF + compliance | Valore operativo |
| **v0.6** | Maneuver planning + historical replay | Tool completo |

## Oracoli di Dominio

| Livello | Fonte | Uso |
|---------|-------|-----|
| L2 | Vallado "Fundamentals of Astrodynamics" 5th Ed | Verifica propagazione orbitale |
| L2 | Alfano 2005 — valori tabulati Pc | Verifica collision probability |
| L2 | NASA CARA Tools (MATLAB) | Cross-check algoritmi |
| L5 | CelesTrak SOCRATES | Confronto screening con riferimento operativo |
| L5 | CDM storici Space-Track | Confronto Pc calcolati vs ufficiali |
| L5 | Collisione Iridium 33 vs Cosmos 2251 (2009-02-10) | Validazione end-to-end |

## Meccanismi Anti-Allucinazione (M1-M4)

### M1: Dependency Lock
- File: `verified-deps.toml`
- Regola: NESSUNA dipendenza nel codice senza entry verificata via web search

### M2: External Oracle Test Pattern
- Ogni test file DEVE avere almeno 1 test con `# SOURCE:` da oracolo esterno
- Oracoli: Vallado (propagazione), Alfano (Pc), SOCRATES (screening)

### M3: Smoke Before Unit
- Smoke test: ingest TLE reale → propaga → screen → calcola Pc → output leggibile
- Questo produce il golden snapshot (L4)

### M4: Two-Tool Verification
- Directory `verify/` con confronto vs Orekit o NASA CARA MATLAB output
- CI confronta i risultati

## Comandi

```bash
# Setup
pip install -e ".[dev]"

# Test
pytest tests/ -v

# Check completo
make check-all

# Smoke test
make smoke

# CLI
satguard screen --norad-id 25544 --days 7
```

## Checkpoint Utente Obbligatori
- [ ] Scope MVP approvato
- [ ] Smoke test output verificato (screening ISS reale)
- [ ] Golden snapshot L4 approvato
- [ ] Valori Pc confrontati con Alfano 2005 paper
- [ ] Globe 3D first render verificato
- [ ] Prima del release
