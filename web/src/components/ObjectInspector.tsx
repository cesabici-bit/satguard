/**
 * ObjectInspector — full data card for a selected satellite.
 *
 * Shows: identification, orbital elements, derived parameters,
 * conjunction risks with clickable links to partner objects.
 */

import { useEffect, useState } from "react";
import type { ObjectDetail, Conjunction, CatalogEntry } from "../types";

interface Props {
  noradId: number;
  conjunctions: Conjunction[];
  siblings: CatalogEntry[];
  onClose: () => void;
  onSelectObject: (noradId: number) => void;
  onViewConjunction3D: (conj: Conjunction | null) => void;
  activeConjunction: Conjunction | null;
}

export default function ObjectInspector({
  noradId, conjunctions, siblings, onClose, onSelectObject, onViewConjunction3D, activeConjunction,
}: Props) {
  const [detail, setDetail] = useState<ObjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/objects/${noradId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then((data: ObjectDetail) => {
        if (!cancelled) { setDetail(data); setLoading(false); }
      })
      .catch((err) => {
        if (!cancelled) { setError(err.message); setLoading(false); }
      });

    return () => { cancelled = true; };
  }, [noradId]);

  // Find conjunctions involving this object
  const risks = conjunctions.filter(
    (c) => c.norad_id_primary === noradId || c.norad_id_secondary === noradId
  );

  return (
    <div className="glass-panel" style={{
      position: "absolute",
      top: 16,
      right: 16,
      width: 320,
      maxHeight: "calc(100vh - 40px)",
      overflowY: "auto",
      padding: 0,
      zIndex: 300,
    }}>
      {/* Header */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        padding: "16px 16px 12px",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}>
        <div style={{ flex: 1 }}>
          <div style={{
            color: "#fff",
            fontWeight: 700,
            fontSize: 15,
            letterSpacing: 0.3,
            lineHeight: 1.3,
          }}>
            {detail?.name ?? `NORAD ${noradId}`}
          </div>
          {detail && (
            <div style={{
              display: "flex",
              gap: 8,
              marginTop: 5,
              alignItems: "center",
            }}>
              <TypeBadge type={detail.object_type} />
              <span style={{
                fontSize: 10,
                color: "rgba(200,214,229,0.5)",
                fontFamily: "monospace",
              }}>
                NORAD {detail.norad_id}
              </span>
            </div>
          )}
        </div>
        <button onClick={onClose} title="Close" style={{
          background: "rgba(255,255,255,0.06)",
          border: "none",
          color: "rgba(200,214,229,0.6)",
          fontSize: 14,
          cursor: "pointer",
          padding: "4px 8px",
          borderRadius: 4,
          lineHeight: 1,
          marginLeft: 8,
        }}>
          ×
        </button>
      </div>

      <div style={{ padding: "8px 16px 16px" }}>
        {loading && <LoadingDots />}
        {error && <div style={{ color: "#ff5555", fontSize: 12 }}>Error: {error}</div>}

        {detail && (
          <>
            <Section title="Identification">
              <Row label="Designator" value={detail.intl_designator} />
              <Row label="Epoch" value={formatEpoch(detail.epoch)} />
            </Section>

            <Section title="Orbit">
              <Row label="Inclination" value={`${detail.inclination_deg.toFixed(2)}°`} />
              <Row label="Eccentricity" value={detail.eccentricity.toFixed(6)} />
              <Row label="Period" value={`${detail.period_min.toFixed(1)} min`} />
              <Row label="Apogee" value={`${detail.apogee_alt_km.toFixed(0)} km`} />
              <Row label="Perigee" value={`${detail.perigee_alt_km.toFixed(0)} km`} />
            </Section>

            <Section title="Advanced">
              <Row label="RAAN" value={`${detail.raan_deg.toFixed(2)}°`} />
              <Row label="Arg. Perigee" value={`${detail.arg_perigee_deg.toFixed(2)}°`} />
              <Row label="Mean Motion" value={`${detail.mean_motion_rev_day.toFixed(4)} rev/d`} />
              <Row label="B* Drag" value={detail.bstar.toExponential(3)} />
              <Row label="Semi-major Axis" value={`${detail.semi_major_axis_km.toFixed(0)} km`} />
            </Section>
          </>
        )}

        {/* Launch Siblings section */}
        {siblings.length > 0 && (
          <Section title={`Launch Siblings (${siblings.length})`}>
            {siblings.slice(0, 20).map((sib) => (
              <button
                key={sib.norad_id}
                onClick={() => onSelectObject(sib.norad_id)}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  width: "100%",
                  background: "rgba(0,229,255,0.04)",
                  border: "1px solid rgba(0,229,255,0.1)",
                  borderRadius: 4,
                  padding: "4px 8px",
                  marginBottom: 3,
                  cursor: "pointer",
                  fontSize: 11,
                  color: "#c8d6e5",
                  textAlign: "left",
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1, marginRight: 8 }}>
                  {sib.name}
                </span>
                <span style={{ fontSize: 9, color: "rgba(200,214,229,0.4)", fontFamily: "monospace", flexShrink: 0 }}>
                  {sib.norad_id} · {sib.intl_designator?.slice(5) || "?"}
                </span>
              </button>
            ))}
            {siblings.length > 20 && (
              <div style={{ fontSize: 10, color: "rgba(200,214,229,0.35)", padding: "4px 0", textAlign: "center" }}>
                ...and {siblings.length - 20} others
              </div>
            )}
          </Section>
        )}

        {/* Conjunction risks section */}
        <Section title={`Collision Risks (${risks.length})`}>
          {risks.length === 0 ? (
            <div style={{ fontSize: 11, color: "rgba(200,214,229,0.35)", padding: "4px 0" }}>
              No known conjunction risks
            </div>
          ) : (
            risks.map((conj, i) => {
              const partnerId = conj.norad_id_primary === noradId
                ? conj.norad_id_secondary
                : conj.norad_id_primary;
              return (
                <ConjunctionCard
                  key={i}
                  conj={conj}
                  partnerId={partnerId}
                  onClickPartner={() => onSelectObject(partnerId)}
                  onView3D={() => onViewConjunction3D(
                    activeConjunction === conj ? null : conj
                  )}
                  isActive3D={activeConjunction === conj}
                />
              );
            })
          )}
        </Section>
      </div>
    </div>
  );
}

// --- Sub-components ---

function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    LEO: "#00e5ff",
    MEO: "#3399ff",
    GEO: "#ffbf33",
    OTHER: "#808099",
  };
  const c = colors[type] ?? colors.OTHER;
  return (
    <span style={{
      fontSize: 9,
      fontWeight: 700,
      letterSpacing: 1.5,
      textTransform: "uppercase",
      color: c,
      background: `${c}18`,
      padding: "2px 6px",
      borderRadius: 3,
      border: `1px solid ${c}33`,
    }}>
      {type}
    </span>
  );
}

function LoadingDots() {
  return (
    <div style={{ color: "rgba(200,214,229,0.4)", fontSize: 12, padding: "8px 0" }}>
      <span className="loading-text">Loading details...</span>
    </div>
  );
}

function ConjunctionCard({
  conj,
  partnerId,
  onClickPartner,
  onView3D,
  isActive3D,
}: {
  conj: Conjunction;
  partnerId: number;
  onClickPartner: () => void;
  onView3D: () => void;
  isActive3D: boolean;
}) {
  const pc = conj.pc;
  const isHighRisk = pc !== null && pc > 1e-4;
  const isMedRisk = pc !== null && pc > 1e-6;

  const riskColor = isHighRisk ? "#ff3333" : isMedRisk ? "#ff8800" : "#ffcc33";
  const riskLabel = isHighRisk ? "HIGH" : isMedRisk ? "MEDIUM" : "LOW";

  return (
    <div style={{
      background: `${riskColor}08`,
      border: `1px solid ${riskColor}22`,
      borderRadius: 6,
      padding: "8px 10px",
      marginBottom: 6,
      fontSize: 11,
    }}>
      {/* Risk badge + partner link */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <span style={{
          fontSize: 8,
          fontWeight: 700,
          letterSpacing: 1.5,
          color: riskColor,
          background: `${riskColor}18`,
          padding: "1px 5px",
          borderRadius: 2,
        }}>
          {riskLabel} RISK
        </span>
        <button
          onClick={onClickPartner}
          style={{
            background: "none",
            border: "none",
            color: "#5ecfff",
            fontSize: 11,
            cursor: "pointer",
            padding: 0,
            textDecoration: "underline",
            textUnderlineOffset: 2,
          }}
          title={`Fly to NORAD ${partnerId}`}
        >
          NORAD {partnerId} →
        </button>
      </div>

      {/* Details */}
      <div style={{ display: "flex", justifyContent: "space-between", color: "rgba(200,214,229,0.6)" }}>
        <span>Miss: {conj.miss_distance_km.toFixed(2)} km</span>
        <span>Vrel: {conj.relative_velocity_km_s.toFixed(1)} km/s</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", color: "rgba(200,214,229,0.6)", marginTop: 2 }}>
        <span>Pc: {pc !== null ? pc.toExponential(2) : "N/A"}</span>
        <span style={{ fontSize: 10 }}>TCA: {formatTCA(conj.tca)}</span>
      </div>
      <button
        onClick={onView3D}
        style={{
          marginTop: 5,
          width: "100%",
          padding: "3px 0",
          background: isActive3D ? "rgba(94,207,255,0.15)" : "rgba(255,255,255,0.04)",
          border: `1px solid ${isActive3D ? "rgba(94,207,255,0.4)" : "rgba(255,255,255,0.08)"}`,
          borderRadius: 4,
          color: isActive3D ? "#5ecfff" : "rgba(200,214,229,0.5)",
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: 1,
          cursor: "pointer",
          transition: "all 0.2s",
        }}
      >
        {isActive3D ? "HIDE 3D" : "VIEW 3D"}
      </button>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{
        fontSize: 9,
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: 2,
        color: "rgba(94, 207, 255, 0.5)",
        marginBottom: 5,
        paddingTop: 8,
        borderTop: "1px solid rgba(255,255,255,0.04)",
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{
      display: "flex",
      justifyContent: "space-between",
      padding: "2.5px 0",
      fontSize: 12,
    }}>
      <span style={{ color: "rgba(200, 214, 229, 0.45)" }}>{label}</span>
      <span style={{
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        fontSize: 11,
        color: "#c8d6e5",
      }}>
        {value}
      </span>
    </div>
  );
}

function formatEpoch(iso: string): string {
  try {
    return new Date(iso).toUTCString().replace(" GMT", " UTC").slice(5);
  } catch {
    return iso;
  }
}

function formatTCA(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${d.getUTCHours().toString().padStart(2, "0")}:${d.getUTCMinutes().toString().padStart(2, "0")}`;
  } catch {
    return iso;
  }
}
