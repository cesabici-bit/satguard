/**
 * ConjunctionBrowser — sortable list of all conjunctions for quick access.
 *
 * Eliminates the need to click satellite-by-satellite to find conjunction risks.
 * Sorted by collision probability (highest risk first).
 */

import { useMemo, useState } from "react";
import type { Conjunction, CatalogEntry } from "../types";

interface Props {
  conjunctions: Conjunction[];
  catalog: CatalogEntry[];
  onSelectObject: (noradId: number) => void;
  onViewConjunction3D: (conj: Conjunction) => void;
  activeConjunction: Conjunction | null;
}

export default function ConjunctionBrowser({
  conjunctions, catalog, onSelectObject, onViewConjunction3D, activeConjunction,
}: Props) {
  const [open, setOpen] = useState(false);

  // Build name lookup
  const nameMap = useMemo(() => {
    const m = new Map<number, string>();
    for (const e of catalog) m.set(e.norad_id, e.name);
    return m;
  }, [catalog]);

  // Sort by Pc descending (nulls last)
  const sorted = useMemo(() =>
    [...conjunctions].sort((a, b) => {
      const pa = a.pc ?? -Infinity;
      const pb = b.pc ?? -Infinity;
      return pb - pa;
    }),
    [conjunctions],
  );

  if (conjunctions.length === 0) return null;

  return (
    <div className="glass-panel" style={{
      position: "absolute",
      top: 290,
      left: 16,
      zIndex: 200,
      minWidth: 210,
      maxWidth: 320,
      maxHeight: open ? "calc(100vh - 340px)" : "auto",
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
    }}>
      {/* Toggle header */}
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          width: "100%",
          padding: "10px 14px",
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "rgba(94, 207, 255, 0.7)",
          fontSize: 10,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: 2,
        }}
      >
        <span>Conjunctions ({conjunctions.length})</span>
        <span style={{
          fontSize: 12,
          transform: open ? "rotate(180deg)" : "rotate(0)",
          transition: "transform 0.2s",
        }}>
          ▼
        </span>
      </button>

      {open && (
        <div style={{
          overflowY: "auto",
          padding: "0 10px 10px",
          flex: 1,
        }}>
          {sorted.map((conj, i) => {
            const pc = conj.pc;
            const isHighRisk = pc !== null && pc > 1e-4;
            const isMedRisk = pc !== null && pc > 1e-6;
            const riskColor = isHighRisk ? "#ff3333" : isMedRisk ? "#ff8800" : "#ffcc33";
            const riskLabel = isHighRisk ? "HIGH" : isMedRisk ? "MED" : "LOW";

            const name1 = nameMap.get(conj.norad_id_primary) ?? `#${conj.norad_id_primary}`;
            const name2 = nameMap.get(conj.norad_id_secondary) ?? `#${conj.norad_id_secondary}`;

            const isActive = activeConjunction === conj;

            return (
              <div
                key={i}
                style={{
                  background: isActive ? "rgba(94,207,255,0.08)" : `${riskColor}06`,
                  border: `1px solid ${isActive ? "rgba(94,207,255,0.3)" : `${riskColor}18`}`,
                  borderRadius: 6,
                  padding: "6px 8px",
                  marginBottom: 4,
                  fontSize: 10,
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
                onClick={() => {
                  onSelectObject(conj.norad_id_primary);
                  onViewConjunction3D(conj);
                }}
              >
                {/* Top row: risk + miss distance */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                  <span style={{
                    fontSize: 8,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    color: riskColor,
                    background: `${riskColor}18`,
                    padding: "1px 5px",
                    borderRadius: 2,
                  }}>
                    {riskLabel}
                  </span>
                  <span style={{ color: "rgba(200,214,229,0.5)", fontSize: 9 }}>
                    {conj.miss_distance_km.toFixed(1)} km · {pc !== null ? pc.toExponential(1) : "N/A"}
                  </span>
                </div>

                {/* Objects */}
                <div style={{ color: "#c8d6e5", lineHeight: 1.4 }}>
                  <span
                    style={{ color: "#5ecfff", cursor: "pointer" }}
                    onClick={(e) => { e.stopPropagation(); onSelectObject(conj.norad_id_primary); }}
                    title={`Fly to ${name1}`}
                  >
                    {truncate(name1, 18)}
                  </span>
                  <span style={{ color: "rgba(200,214,229,0.3)", margin: "0 4px" }}>vs</span>
                  <span
                    style={{ color: "#5ecfff", cursor: "pointer" }}
                    onClick={(e) => { e.stopPropagation(); onSelectObject(conj.norad_id_secondary); }}
                    title={`Fly to ${name2}`}
                  >
                    {truncate(name2, 18)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}
