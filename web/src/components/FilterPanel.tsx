/**
 * FilterPanel — orbit type checkboxes + name search with Enter-to-fly.
 */

import type { FilterState } from "../types";

interface Props {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  onSearchSubmit: (query: string) => void;
}

const DOT_COLORS: Record<string, string> = {
  LEO: "#26ff66",
  MEO: "#ff33cc",
  GEO: "#ffd900",
  OTHER: "#00e5ff",
};

const LABELS: Record<string, string> = {
  LEO: "LEO  ·  Low Earth Orbit",
  MEO: "MEO  ·  Medium Earth",
  GEO: "GEO  ·  Geostationary",
  OTHER: "Other  ·  HEO / Misc",
};

export default function FilterPanel({ filters, onChange, onSearchSubmit }: Props) {
  const toggle = (key: keyof FilterState) => {
    onChange({ ...filters, [key]: !filters[key as keyof FilterState] });
  };

  return (
    <div className="glass-panel" style={{
      position: "absolute",
      top: 16,
      left: 16,
      padding: "14px 16px",
      zIndex: 200,
      minWidth: 210,
    }}>
      <div style={{
        fontSize: 10,
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: 2,
        color: "rgba(94, 207, 255, 0.7)",
        marginBottom: 10,
      }}>
        Orbit Filters
      </div>

      {(["LEO", "MEO", "GEO", "OTHER"] as const).map((type) => {
        const key = `show${type}` as keyof FilterState;
        const checked = filters[key] as boolean;
        const dotColor = DOT_COLORS[type];

        return (
          <label key={type} style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "5px 0",
            cursor: "pointer",
            opacity: checked ? 1 : 0.4,
            transition: "opacity 0.2s",
            fontSize: 12,
          }}>
            <input
              type="checkbox"
              checked={checked}
              onChange={() => toggle(key)}
              style={{ display: "none" }}
            />
            <span style={{
              width: 14,
              height: 14,
              borderRadius: 3,
              border: `1.5px solid ${checked ? dotColor : "rgba(255,255,255,0.15)"}`,
              background: checked ? `${dotColor}22` : "transparent",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "all 0.2s",
              flexShrink: 0,
            }}>
              {checked && (
                <span style={{
                  width: 6,
                  height: 6,
                  borderRadius: 1,
                  background: dotColor,
                  boxShadow: `0 0 6px ${dotColor}`,
                }} />
              )}
            </span>
            <span style={{ color: checked ? "#c8d6e5" : "#555" }}>
              {LABELS[type]}
            </span>
          </label>
        );
      })}

      {/* Heatmap toggle */}
      <label style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "5px 0",
        marginTop: 6,
        cursor: "pointer",
        opacity: filters.showHeatmap ? 1 : 0.4,
        transition: "opacity 0.2s",
        fontSize: 12,
        borderTop: "1px solid rgba(255,255,255,0.06)",
        paddingTop: 8,
      }}>
        <input
          type="checkbox"
          checked={filters.showHeatmap}
          onChange={() => onChange({ ...filters, showHeatmap: !filters.showHeatmap })}
          style={{ display: "none" }}
        />
        <span style={{
          width: 14,
          height: 14,
          borderRadius: 3,
          border: `1.5px solid ${filters.showHeatmap ? "#ff6633" : "rgba(255,255,255,0.15)"}`,
          background: filters.showHeatmap ? "#ff663322" : "transparent",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          transition: "all 0.2s",
          flexShrink: 0,
        }}>
          {filters.showHeatmap && (
            <span style={{
              width: 6,
              height: 6,
              borderRadius: 1,
              background: "#ff6633",
              boxShadow: "0 0 6px #ff6633",
            }} />
          )}
        </span>
        <span style={{ color: filters.showHeatmap ? "#c8d6e5" : "#555" }}>
          Heatmap  ·  Conjunction density
        </span>
      </label>

      <div style={{ position: "relative", marginTop: 10 }}>
        <input
          type="text"
          placeholder="Search + Enter to fly..."
          value={filters.searchText}
          onChange={(e) => onChange({ ...filters, searchText: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              onSearchSubmit(filters.searchText);
            }
          }}
          style={{
            width: "100%",
            padding: "8px 32px 8px 10px",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(94, 207, 255, 0.12)",
            borderRadius: 6,
            color: "#e0e8f0",
            fontSize: 12,
            outline: "none",
            boxSizing: "border-box",
            transition: "border-color 0.2s",
          }}
          onFocus={(e) => e.currentTarget.style.borderColor = "rgba(94, 207, 255, 0.4)"}
          onBlur={(e) => e.currentTarget.style.borderColor = "rgba(94, 207, 255, 0.12)"}
        />
        {/* Search icon / enter hint */}
        <span style={{
          position: "absolute",
          right: 8,
          top: "50%",
          transform: "translateY(-50%)",
          fontSize: 9,
          color: "rgba(94,207,255,0.35)",
          pointerEvents: "none",
          fontFamily: "monospace",
        }}>
          ↵
        </span>
      </div>
    </div>
  );
}
