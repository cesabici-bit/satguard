# Known Issues — SatGuard

> Questo file persiste tra sessioni. Claude lo legge a inizio sessione per evitare errori ricorrenti.
> Aggiungere OGNI errore significativo con analisi causa radice.

## Formato Entry

```
### EC-NNN: Titolo breve
- **Data**: YYYY-MM-DD
- **Sintomo**: cosa si osserva
- **Causa**: perche' e' successo
- **Fix**: cosa e' stato fatto
- **Prevenzione**: come evitarlo in futuro
- **Status**: OPEN | FIXED | WORKAROUND
```

## Issues

### EC-001: Conjunctions endpoint returned 50 identical ISS ZARYA vs UNITY events
- **Data**: 2026-03-19
- **Sintomo**: 50 congiunzioni, tutte la stessa coppia ISS(ZARYA) vs ISS(UNITY)
- **Causa**: Screening single-primary (solo ISS) senza filtro siblings. ISS ha molte parti co-orbitanti con diversi intl_designator ma stessa posizione
- **Fix**: Riscritto endpoint con all-on-all SatrecArray + filtro intl_designator[:5] + filtro co-orbiting (vrel < 0.5 km/s)
- **Prevenzione**: Sempre filtrare siblings E co-orbiting. Sempre verificare diversità nei risultati (# coppie uniche). Aggiungere test L2 con sanity check
- **Status**: FIXED

### EC-002: Snapshot-based all-on-all screening found only co-orbiting objects
- **Data**: 2026-03-19
- **Sintomo**: 50 congiunzioni a 0.00 km miss distance, tutte oggetti co-locati con ISS
- **Causa**: A 2h intervalli, oggetti su orbite incrociate (vrel ~10 km/s) si mancano tra snapshot. Solo oggetti co-orbitanti (vrel ~0) restano entro threshold per ore
- **Fix**: Passato a time-stepping fine (120s) con SatrecArray vettorizzato + KDTree per epoch
- **Prevenzione**: Mai usare snapshot sparsi per screening LEO. Usare time-stepping ≤ 120s
- **Status**: FIXED

### EC-003: v0.4 frontend features shipped without automated tests
- **Data**: 2026-03-19
- **Sintomo**: 177 test passano ma nessuno copre codice v0.4 (siblings, heatmap, arcs, time slider, ConjunctionBrowser, nuovo endpoint)
- **Causa**: Focus su velocità implementazione, bypass di M2 (oracle tests) e M3 (smoke first)
- **Fix**: 18 test aggiunti in test_v04_audit.py (L1+L2). 5 bug fixati (start_epoch, heatmap color, Pc validation, version, perf). 195 test totali.
- **Prevenzione**: Regola R1 (test-before-declare), R2 (oracle-or-explain), R3 (declare-skip-explicitly). Vedere memory/feedback_enforce_mechanisms.md
- **Status**: FIXED (2026-03-20)

### EC-004: Heatmap DeveloperError — SingleTileImageryProvider constructor deprecated
- **Data**: 2026-03-19
- **Sintomo**: `DeveloperError` in console quando si attiva la heatmap; overlay non renderizzato
- **Causa**: Cesium 1.139 ha deprecato il costruttore sincrono di `SingleTileImageryProvider`. Richiede `SingleTileImageryProvider.fromUrl()` (async static method)
- **Fix**: Convertito callback `canvas.toBlob` in `async`, usato `await Cesium.SingleTileImageryProvider.fromUrl(url, { rectangle })` con cleanup in caso di errore
- **Prevenzione**: Verificare le breaking changes di Cesium prima di usare API deprecate. Controllare visivamente le feature prima di dichiararle complete
- **Status**: FIXED
