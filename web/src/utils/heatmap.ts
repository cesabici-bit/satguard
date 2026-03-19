/**
 * heatmap.ts — Continuous gaussian-smoothed heatmap rendered to canvas.
 *
 * For each conjunction, propagate primary to TCA → get lat/lon.
 * Stamp gaussian kernels weighted by collision probability.
 * Render equirectangular canvas for use as SingleTileImageryProvider.
 */

import type { Conjunction } from "../types";
import { twoline2satrec, propagate, eciToGeodetic, gstime } from "satellite.js";

const CANVAS_W = 1024;
const CANVAS_H = 512;
const KERNEL_RADIUS_PX = 40; // ~14° at this resolution

/** Precompute gaussian kernel weights (quarter-circle, mirrored in stamping) */
function makeKernel(radius: number): Float32Array {
  const size = radius * 2 + 1;
  const kernel = new Float32Array(size * size);
  const sigma = radius / 2.5;
  const s2 = 2 * sigma * sigma;
  for (let dy = -radius; dy <= radius; dy++) {
    for (let dx = -radius; dx <= radius; dx++) {
      kernel[(dy + radius) * size + (dx + radius)] =
        Math.exp(-(dx * dx + dy * dy) / s2);
    }
  }
  return kernel;
}

/** Map normalized value [0,1] to RGBA (black → blue → cyan → yellow → red → white) */
function heatColor(t: number): [number, number, number, number] {
  // 5-stop gradient for scientific heatmap look
  if (t < 0.2) {
    const s = t / 0.2;
    return [0, 0, Math.round(s * 180), Math.round(s * 200)];
  }
  if (t < 0.4) {
    const s = (t - 0.2) / 0.2;
    return [0, Math.round(s * 220), 180 + Math.round(s * 75), 200 + Math.round(s * 30)];
  }
  if (t < 0.6) {
    const s = (t - 0.4) / 0.2;
    return [Math.round(s * 255), 220 + Math.round(s * 35), 255 - Math.round(s * 155), 230];
  }
  if (t < 0.8) {
    const s = (t - 0.6) / 0.2;
    return [255, 255 - Math.round(s * 155), 100 - Math.round(s * 100), 230 + Math.round(s * 15)];
  }
  const s = (t - 0.8) / 0.2;
  return [255, 100 - Math.round(s * 60), Math.round(s * 60), 245];
}

export interface ConjunctionPoint {
  x: number; // pixel x on canvas
  y: number; // pixel y on canvas
  weight: number; // based on Pc
}

/**
 * Compute conjunction sub-satellite points and weights.
 */
export function computeConjunctionPoints(
  conjunctions: Conjunction[],
  satrecByNorad: Map<number, ReturnType<typeof twoline2satrec>>,
): ConjunctionPoint[] {
  const points: ConjunctionPoint[] = [];

  for (const conj of conjunctions) {
    const satrec = satrecByNorad.get(conj.norad_id_primary);
    if (!satrec) continue;

    const tcaDate = new Date(conj.tca);
    const posVel = propagate(satrec, tcaDate);
    if (typeof posVel.position === "boolean" || !posVel.position) continue;

    const gmst = gstime(tcaDate);
    const geo = eciToGeodetic(posVel.position, gmst);

    const latDeg = (geo.latitude * 180) / Math.PI;
    const lonDeg = (geo.longitude * 180) / Math.PI;

    // Map to canvas pixels (equirectangular)
    const x = ((lonDeg + 180) / 360) * CANVAS_W;
    const y = ((90 - latDeg) / 180) * CANVAS_H;

    // Weight by Pc: higher Pc = larger splat. Use log scale.
    const pc = conj.pc ?? 1e-8;
    const weight = Math.max(0.3, Math.min(1.0, (Math.log10(pc) + 8) / 5));

    points.push({ x, y, weight });
  }

  return points;
}

/**
 * Render heatmap to a canvas and return its blob URL.
 * Returns null if no conjunction points.
 */
export function renderHeatmapCanvas(
  conjunctions: Conjunction[],
  satrecByNorad: Map<number, ReturnType<typeof twoline2satrec>>,
): HTMLCanvasElement | null {
  const points = computeConjunctionPoints(conjunctions, satrecByNorad);
  if (points.length === 0) return null;

  // Accumulator
  const acc = new Float32Array(CANVAS_W * CANVAS_H);
  const kernel = makeKernel(KERNEL_RADIUS_PX);
  const kSize = KERNEL_RADIUS_PX * 2 + 1;

  // Stamp each point
  for (const pt of points) {
    const cx = Math.round(pt.x);
    const cy = Math.round(pt.y);

    for (let dy = -KERNEL_RADIUS_PX; dy <= KERNEL_RADIUS_PX; dy++) {
      const py = cy + dy;
      if (py < 0 || py >= CANVAS_H) continue;

      for (let dx = -KERNEL_RADIUS_PX; dx <= KERNEL_RADIUS_PX; dx++) {
        // Wrap horizontally (equirectangular)
        let px = cx + dx;
        if (px < 0) px += CANVAS_W;
        if (px >= CANVAS_W) px -= CANVAS_W;

        const kVal = kernel[(dy + KERNEL_RADIUS_PX) * kSize + (dx + KERNEL_RADIUS_PX)];
        acc[py * CANVAS_W + px] += kVal * pt.weight;
      }
    }
  }

  // Find max for normalization
  let maxVal = 0;
  for (let i = 0; i < acc.length; i++) {
    if (acc[i] > maxVal) maxVal = acc[i];
  }
  if (maxVal === 0) return null;

  // Render to canvas
  const canvas = document.createElement("canvas");
  canvas.width = CANVAS_W;
  canvas.height = CANVAS_H;
  const ctx = canvas.getContext("2d")!;
  const imageData = ctx.createImageData(CANVAS_W, CANVAS_H);
  const data = imageData.data;

  for (let i = 0; i < acc.length; i++) {
    const t = acc[i] / maxVal;
    if (t < 0.05) {
      // Transparent for low values
      data[i * 4 + 3] = 0;
      continue;
    }
    const [r, g, b, a] = heatColor(t);
    data[i * 4] = r;
    data[i * 4 + 1] = g;
    data[i * 4 + 2] = b;
    data[i * 4 + 3] = a;
  }

  ctx.putImageData(imageData, 0, 0);
  return canvas;
}
