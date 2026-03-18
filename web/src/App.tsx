import { useCallback, useEffect, useRef, useState } from "react";
import type { CatalogEntry, Conjunction, FilterState, TimeState } from "./types";
import Globe from "./components/Globe";
import type { GlobeHandle } from "./components/Globe";
import ObjectInspector from "./components/ObjectInspector";
import FilterPanel from "./components/FilterPanel";
import TimeControls from "./components/TimeControls";
import "cesium/Build/Cesium/Widgets/widgets.css";
import "./App.css";

export default function App() {
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [conjunctions, setConjunctions] = useState<Conjunction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const globeRef = useRef<GlobeHandle>(null);

  const [filters, setFilters] = useState<FilterState>({
    showLEO: true,
    showMEO: true,
    showGEO: true,
    showOTHER: true,
    searchText: "",
  });

  const [timeState, setTimeState] = useState<TimeState>({
    playing: true,
    speedMultiplier: 1,
    simulationTime: new Date(),
  });

  // Fetch catalog on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch("/api/catalog");
        if (!resp.ok) throw new Error(`Catalog fetch failed: ${resp.status}`);
        const data: CatalogEntry[] = await resp.json();
        if (!cancelled) { setCatalog(data); setLoading(false); }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load catalog");
          setLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Fetch conjunctions (non-blocking)
  useEffect(() => {
    if (catalog.length === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch("/api/conjunctions");
        if (!resp.ok) return;
        const data: Conjunction[] = await resp.json();
        if (!cancelled) setConjunctions(data);
      } catch { /* optional */ }
    })();
    return () => { cancelled = true; };
  }, [catalog]);

  // Select + fly to object
  const selectAndFlyTo = useCallback((noradId: number) => {
    setSelectedId(noradId);
    // Small delay to let the point be highlighted first
    setTimeout(() => globeRef.current?.flyToObject(noradId), 100);
  }, []);

  // Search submit: find object by name/ID and fly to it
  const handleSearchSubmit = useCallback((query: string) => {
    const q = query.trim().toLowerCase();
    if (!q) return;

    // Try exact NORAD ID first
    const numId = parseInt(q, 10);
    if (!isNaN(numId)) {
      const found = catalog.find((e) => e.norad_id === numId);
      if (found) { selectAndFlyTo(found.norad_id); return; }
    }

    // Then search by name
    const found = catalog.find((e) => e.name.toLowerCase().includes(q));
    if (found) { selectAndFlyTo(found.norad_id); }
  }, [catalog, selectAndFlyTo]);

  if (loading) {
    return (
      <div className="loading-overlay">
        <div className="spinner" />
        <span className="loading-text">Loading satellite catalog...</span>
        <span className="subtitle">Fetching real-time TLE data from CelesTrak</span>
      </div>
    );
  }

  return (
    <div className="app">
      {error && <div className="error-banner">{error}</div>}

      <Globe
        ref={globeRef}
        catalog={catalog}
        conjunctions={conjunctions}
        filters={filters}
        timeState={timeState}
        selectedId={selectedId}
        onSelectObject={selectAndFlyTo}
      />

      {/* Branding */}
      <div className="branding">
        <h1>SatGuard</h1>
        <p className="tagline">Conjunction Assessment Pipeline</p>
      </div>

      <FilterPanel
        filters={filters}
        onChange={setFilters}
        onSearchSubmit={handleSearchSubmit}
      />

      <TimeControls timeState={timeState} onChange={setTimeState} />

      {selectedId !== null && (
        <ObjectInspector
          noradId={selectedId}
          conjunctions={conjunctions}
          onClose={() => setSelectedId(null)}
          onSelectObject={selectAndFlyTo}
        />
      )}

      {/* Legend */}
      <div className="legend">
        <div className="legend-item">
          <span className="legend-dot" style={{ background: "#26ff66", color: "#26ff66" }} />
          LEO
        </div>
        <div className="legend-item">
          <span className="legend-dot" style={{ background: "#ff33cc", color: "#ff33cc" }} />
          MEO
        </div>
        <div className="legend-item">
          <span className="legend-dot" style={{ background: "#ffd900", color: "#ffd900" }} />
          GEO
        </div>
        <div className="legend-item">
          <span className="legend-dot" style={{ background: "#00e5ff", color: "#00e5ff" }} />
          Other
        </div>
      </div>

      {/* Status bar */}
      <div className="status-bar glass-panel">
        {catalog.length.toLocaleString()} objects tracked
        {conjunctions.length > 0 && ` · ${conjunctions.length} conjunctions`}
      </div>
    </div>
  );
}
