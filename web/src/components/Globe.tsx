/**
 * Globe.tsx — CesiumJS 3D globe with 30K+ satellite points.
 *
 * v0.3.1 fixes:
 * - Disabled enableLighting (was causing blinding sun glare)
 * - Removed bloom post-processing (was blurring dots and washing out colors)
 * - Increased point sizes and full-alpha saturated colors
 * - Added flyToObject() — smooth camera transition on click/search
 *
 * Sources:
 * - PointPrimitiveCollection: https://cesium.com/blog/2016/03/02/performance-tips-for-points/
 * - scaleByDistance: same source (1.25M points from 33 to 60fps)
 * - Camera flyTo: https://cesium.com/learn/cesiumjs-learn/cesiumjs-camera/
 * - FXAA: https://cesium.com/learn/cesiumjs/ref-doc/PostProcessStageLibrary.html
 */

import { useRef, useEffect, useImperativeHandle, forwardRef } from "react";
import * as Cesium from "cesium";
import {
  Viewer as CesiumViewer,
  Cartesian2,
  Cartesian3,
  Color,
  NearFarScalar,
  OpenStreetMapImageryProvider,
  PointPrimitiveCollection,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  CallbackProperty,
  defined,
} from "cesium";
import type { CatalogEntry, Conjunction, FilterState, TimeState } from "../types";
import {
  twoline2satrec,
  propagate,
  eciToGeodetic,
  gstime,
} from "satellite.js";

// --- Visual constants ---

/** Neon colors — maximum brightness, high saturation, full alpha.
 *  Each type must be instantly distinguishable on a dark globe.
 *
 *  LEO  = bright green  (most common — needs to stand out from the mass)
 *  MEO  = hot magenta   (few objects — vivid contrast vs green)
 *  GEO  = electric gold (ring at equator — warm vs cool palette)
 *  OTHER = cyan          (misc — cool tone, distinct from all above)
 */
const TYPE_COLORS: Record<string, Color> = {
  LEO: new Color(0.15, 1.0, 0.4, 1.0),   // Neon green
  MEO: new Color(1.0, 0.2, 0.8, 1.0),    // Hot magenta
  GEO: new Color(1.0, 0.85, 0.0, 1.0),   // Electric gold
  OTHER: new Color(0.0, 0.9, 1.0, 1.0),  // Cyan
};

/** Point sizes tuned per density:
 *  - LEO: 3.5px — thousands of objects, keep small to avoid overlap
 *  - MEO: 5px   — ~50 objects (GPS, etc), can be larger
 *  - GEO: 7px   — ~500 objects, spread along equator (no overlap)
 *  - OTHER: 3px  — sparse, keep moderate
 */
const TYPE_SIZES: Record<string, number> = {
  LEO: 3.5,
  MEO: 5,
  GEO: 7,
  OTHER: 3,
};

const SELECTED_SIZE = 14;
const SELECTED_COLOR = new Color(1.0, 1.0, 1.0, 1.0);

/** Scale: zoomed in = bigger, zoomed out = slightly smaller (not tiny) */
const SCALE_BY_DISTANCE = new NearFarScalar(5.0e5, 2.5, 2.0e7, 0.7);
/** Keep dots visible even from far — minimum alpha 0.5 */
const TRANSLUCENCY_BY_DISTANCE = new NearFarScalar(5.0e5, 1.0, 3.0e7, 0.5);

const AUTO_ROTATE_SPEED = 0.0003;
const AUTO_ROTATE_RESUME_DELAY = 10000;

function conjunctionColor(pc: number | null): Color {
  if (pc === null) return new Color(1.0, 0.85, 0.3, 0.5);
  if (pc > 1e-4) return new Color(1.0, 0.1, 0.1, 0.9);
  if (pc > 1e-6) return new Color(1.0, 0.5, 0.05, 0.7);
  return new Color(1.0, 0.85, 0.3, 0.5);
}

// --- Public handle for parent to trigger flyTo ---

export interface GlobeHandle {
  flyToObject: (noradId: number) => void;
}

interface Props {
  catalog: CatalogEntry[];
  conjunctions: Conjunction[];
  filters: FilterState;
  timeState: TimeState;
  selectedId: number | null;
  onSelectObject: (noradId: number) => void;
}

const Globe = forwardRef<GlobeHandle, Props>(function Globe(
  { catalog, conjunctions, filters, timeState, selectedId, onSelectObject },
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<CesiumViewer | null>(null);
  const pointsRef = useRef<PointPrimitiveCollection | null>(null);
  const satrecsRef = useRef<ReturnType<typeof twoline2satrec>[]>([]);
  const catalogRef = useRef<CatalogEntry[]>([]);
  const animFrameRef = useRef<number>(0);
  const simTimeRef = useRef<Date>(new Date());
  const lastRealTimeRef = useRef<number>(Date.now());
  const lastInteractionRef = useRef<number>(0);
  const selectedIndexRef = useRef<number>(-1);
  const prevSelectedSizeRef = useRef<number>(3);
  const prevSelectedColorRef = useRef<Color>(Color.WHITE);

  // --- flyToObject: find point index, fly camera there ---
  const flyToObject = (noradId: number) => {
    const viewer = viewerRef.current;
    const points = pointsRef.current;
    const entries = catalogRef.current;
    if (!viewer || !points || entries.length === 0) return;

    const idx = entries.findIndex((e) => e.norad_id === noradId);
    if (idx === -1) return;

    const point = points.get(idx);
    if (!point || !point.show) return;

    // Fly camera to satellite position
    // Offset = altitude + 500km to frame the object nicely
    const pos = point.position;
    if (!pos || Cartesian3.equals(pos, Cartesian3.ZERO)) return;

    lastInteractionRef.current = Date.now(); // pause auto-rotate

    // Compute a viewpoint offset from the satellite position
    const carto = Cesium.Cartographic.fromCartesian(pos);
    const viewDest = Cartesian3.fromRadians(
      carto.longitude,
      carto.latitude - 0.05, // slightly south for perspective
      carto.height + 2_000_000 // 2000km above satellite
    );

    viewer.camera.flyTo({
      destination: viewDest,
      duration: 1.8,
    });
  };

  // Expose flyToObject to parent via ref
  useImperativeHandle(ref, () => ({ flyToObject }), []);

  // --- Highlight selected point ---
  useEffect(() => {
    const points = pointsRef.current;
    const entries = catalogRef.current;
    if (!points || entries.length === 0) return;

    // Restore previous selected point
    if (selectedIndexRef.current >= 0 && selectedIndexRef.current < entries.length) {
      const prev = points.get(selectedIndexRef.current);
      if (prev) {
        prev.pixelSize = prevSelectedSizeRef.current;
        prev.color = prevSelectedColorRef.current;
      }
    }

    if (selectedId === null) {
      selectedIndexRef.current = -1;
      return;
    }

    const idx = entries.findIndex((e) => e.norad_id === selectedId);
    if (idx === -1) {
      selectedIndexRef.current = -1;
      return;
    }

    const point = points.get(idx);
    if (point) {
      prevSelectedSizeRef.current = point.pixelSize;
      prevSelectedColorRef.current = point.color;
      point.pixelSize = SELECTED_SIZE;
      point.color = SELECTED_COLOR;
    }
    selectedIndexRef.current = idx;
  }, [selectedId]);

  // Initialize Cesium viewer once
  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;

    const viewer = new CesiumViewer(containerRef.current, {
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      animation: false,
      timeline: false,
      fullscreenButton: false,
      vrButton: false,
      selectionIndicator: false,
      infoBox: false,
      requestRenderMode: false,
      contextOptions: { webgl: { alpha: false } },
    } as any);

    // --- CARTO Dark Matter (no labels) ---
    viewer.imageryLayers.removeAll();
    viewer.imageryLayers.addImageryProvider(
      new OpenStreetMapImageryProvider({
        url: "https://basemaps.cartocdn.com/dark_nolabels/",
      })
    );

    const scene = viewer.scene;
    const globe = scene.globe;

    globe.enableLighting = false;
    globe.showGroundAtmosphere = false;

    if (scene.skyAtmosphere) {
      scene.skyAtmosphere.show = false;
    }

    scene.backgroundColor = Color.BLACK;
    globe.depthTestAgainstTerrain = false;

    // --- NO bloom (was blurring everything) ---
    scene.postProcessStages.bloom.enabled = false;

    // --- FXAA for clean edges ---
    scene.postProcessStages.fxaa.enabled = true;

    // --- Initial camera position ---
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(10, 20, 25_000_000),
    });

    viewerRef.current = viewer;

    // --- Auto-rotate ---
    const markInteraction = () => { lastInteractionRef.current = Date.now(); };
    const canvas = viewer.scene.canvas;
    canvas.addEventListener("pointerdown", markInteraction);
    canvas.addEventListener("wheel", markInteraction);

    viewer.clock.onTick.addEventListener(() => {
      if (Date.now() - lastInteractionRef.current > AUTO_ROTATE_RESUME_DELAY) {
        viewer.scene.camera.rotateRight(AUTO_ROTATE_SPEED);
      }
    });

    // --- Click handler ---
    const handler = new ScreenSpaceEventHandler(canvas);
    handler.setInputAction((movement: { position: Cartesian2 }) => {
      const picked = viewer.scene.pick(movement.position);
      if (defined(picked) && picked.id !== undefined) {
        const noradId = picked.id as number;
        onSelectObject(noradId);
        setTimeout(() => flyToObject(noradId), 50);
      }
    }, ScreenSpaceEventType.LEFT_CLICK);

    return () => {
      canvas.removeEventListener("pointerdown", markInteraction);
      canvas.removeEventListener("wheel", markInteraction);
      handler.destroy();
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy();
      }
      viewerRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Build satrecs and point primitives when catalog changes
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || catalog.length === 0) return;

    if (pointsRef.current) {
      viewer.scene.primitives.remove(pointsRef.current);
    }

    const points = new PointPrimitiveCollection();
    const satrecs: ReturnType<typeof twoline2satrec>[] = [];
    const validCatalog: CatalogEntry[] = [];

    for (const entry of catalog) {
      try {
        const satrec = twoline2satrec(entry.line1, entry.line2);
        if (satrec.error !== 0) continue;

        const color = TYPE_COLORS[entry.object_type] ?? TYPE_COLORS.OTHER;
        const pixelSize = TYPE_SIZES[entry.object_type] ?? 3;

        points.add({
          position: Cartesian3.ZERO,
          pixelSize,
          color,
          show: false,
          id: entry.norad_id,
          scaleByDistance: SCALE_BY_DISTANCE,
          translucencyByDistance: TRANSLUCENCY_BY_DISTANCE,
        });
        satrecs.push(satrec);
        validCatalog.push(entry);
      } catch {
        // Skip invalid TLEs
      }
    }

    viewer.scene.primitives.add(points);
    pointsRef.current = points;
    satrecsRef.current = satrecs;
    catalogRef.current = validCatalog;

    simTimeRef.current = new Date();
    lastRealTimeRef.current = Date.now();
  }, [catalog]);

  // Animation loop — propagate positions
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !pointsRef.current) return;

    let running = true;

    const animate = () => {
      if (!running || !pointsRef.current) return;

      const points = pointsRef.current;
      const satrecs = satrecsRef.current;
      const entries = catalogRef.current;

      const now = Date.now();
      const dt = (now - lastRealTimeRef.current) / 1000;
      lastRealTimeRef.current = now;

      if (timeState.playing) {
        simTimeRef.current = new Date(
          simTimeRef.current.getTime() + dt * timeState.speedMultiplier * 1000
        );
      }

      const simDate = simTimeRef.current;
      const gmst = gstime(simDate);
      const searchLower = filters.searchText.toLowerCase();

      for (let i = 0; i < satrecs.length; i++) {
        const point = points.get(i);
        const entry = entries[i];

        const typeVisible =
          (entry.object_type === "LEO" && filters.showLEO) ||
          (entry.object_type === "MEO" && filters.showMEO) ||
          (entry.object_type === "GEO" && filters.showGEO) ||
          (entry.object_type === "OTHER" && filters.showOTHER);

        const nameMatch =
          searchLower === "" ||
          entry.name.toLowerCase().includes(searchLower) ||
          entry.norad_id.toString().includes(searchLower);

        if (!typeVisible || !nameMatch) {
          point.show = false;
          continue;
        }

        const posVel = propagate(satrecs[i], simDate);
        if (
          typeof posVel.position === "boolean" ||
          posVel.position === undefined ||
          !posVel.position
        ) {
          point.show = false;
          continue;
        }

        const eci = posVel.position;
        const geo = eciToGeodetic(eci, gmst);

        point.position = Cartesian3.fromRadians(
          geo.longitude,
          geo.latitude,
          geo.height * 1000
        );
        point.show = true;
      }

      timeState.simulationTime = simDate;
      animFrameRef.current = requestAnimationFrame(animate);
    };

    animFrameRef.current = requestAnimationFrame(animate);

    return () => {
      running = false;
      cancelAnimationFrame(animFrameRef.current);
    };
  }, [catalog, filters, timeState.playing, timeState.speedMultiplier]); // eslint-disable-line react-hooks/exhaustive-deps

  // Draw conjunction lines
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    viewer.entities.removeAll();
    if (conjunctions.length === 0) return;

    const idToIndex = new Map<number, number>();
    catalogRef.current.forEach((entry, i) => {
      idToIndex.set(entry.norad_id, i);
    });

    for (const conj of conjunctions) {
      const i1 = idToIndex.get(conj.norad_id_primary);
      const i2 = idToIndex.get(conj.norad_id_secondary);
      if (i1 === undefined || i2 === undefined) continue;
      if (!pointsRef.current) continue;

      const color = conjunctionColor(conj.pc);
      viewer.entities.add({
        polyline: {
          positions: new CallbackProperty(() => {
            const pt1 = pointsRef.current?.get(i1!);
            const pt2 = pointsRef.current?.get(i2!);
            if (!pt1?.show || !pt2?.show) return [];
            return [pt1.position, pt2.position];
          }, false),
          width: conj.pc && conj.pc > 1e-4 ? 3 : 1.5,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.25,
            taperPower: 0.5,
            color,
          }),
        },
      });
    }
  }, [conjunctions, catalog]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", position: "absolute", top: 0, left: 0 }}
    />
  );
});

export default Globe;
