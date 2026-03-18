/**
 * TimeControls — play/pause, speed multiplier, simulation clock.
 *
 * Minimal bar design inspired by KeepTrack.space time controls.
 */

import { useEffect, useState } from "react";
import type { TimeState } from "../types";

interface Props {
  timeState: TimeState;
  onChange: (t: TimeState) => void;
}

const SPEEDS = [1, 10, 60, 600];

export default function TimeControls({ timeState, onChange }: Props) {
  const [displayTime, setDisplayTime] = useState(new Date());

  useEffect(() => {
    const interval = setInterval(() => {
      setDisplayTime(timeState.simulationTime);
    }, 200);
    return () => clearInterval(interval);
  }, [timeState]);

  const btnBase: React.CSSProperties = {
    background: "rgba(255, 255, 255, 0.04)",
    border: "1px solid rgba(94, 207, 255, 0.12)",
    color: "rgba(200, 214, 229, 0.6)",
    borderRadius: 6,
    padding: "5px 12px",
    cursor: "pointer",
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 0.5,
    transition: "all 0.2s",
  };

  const btnActive: React.CSSProperties = {
    ...btnBase,
    background: "rgba(94, 207, 255, 0.12)",
    borderColor: "rgba(94, 207, 255, 0.35)",
    color: "#5ecfff",
    boxShadow: "0 0 8px rgba(94, 207, 255, 0.15)",
  };

  return (
    <div className="glass-panel" style={{
      position: "absolute",
      bottom: 44,
      left: "50%",
      transform: "translateX(-50%)",
      padding: "8px 14px",
      zIndex: 200,
      display: "flex",
      alignItems: "center",
      gap: 8,
    }}>
      {/* Play/Pause */}
      <button
        style={timeState.playing ? btnActive : btnBase}
        onClick={() => onChange({ ...timeState, playing: !timeState.playing })}
        title={timeState.playing ? "Pause" : "Play"}
      >
        {timeState.playing ? "\u23F8" : "\u25B6"}
      </button>

      {/* Separator */}
      <span style={{
        width: 1,
        height: 18,
        background: "rgba(255,255,255,0.08)",
      }} />

      {/* Speed buttons */}
      {SPEEDS.map((s) => (
        <button
          key={s}
          style={timeState.speedMultiplier === s ? btnActive : btnBase}
          onClick={() => onChange({ ...timeState, speedMultiplier: s })}
        >
          {s}x
        </button>
      ))}

      {/* Separator */}
      <span style={{
        width: 1,
        height: 18,
        background: "rgba(255,255,255,0.08)",
      }} />

      {/* Clock display */}
      <span style={{
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        fontSize: 11,
        color: "#5ecfff",
        minWidth: 175,
        letterSpacing: 0.5,
        textShadow: "0 0 10px rgba(94, 207, 255, 0.25)",
      }}>
        {displayTime.toISOString().replace("T", "  ").slice(0, 21)} UTC
      </span>

      {/* NOW button */}
      <button
        style={btnBase}
        onClick={() =>
          onChange({
            ...timeState,
            simulationTime: new Date(),
            playing: true,
            speedMultiplier: 1,
          })
        }
        title="Reset to current time"
      >
        NOW
      </button>
    </div>
  );
}
