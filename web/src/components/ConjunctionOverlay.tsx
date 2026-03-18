// Conjunction overlay is integrated into Globe.tsx using dynamic polylines.
// This keeps the rendering in a single animation loop for performance.
//
// Conjunction lines are drawn as Cesium entities with CallbackProperty
// positions that follow the propagated satellite positions in real-time.
// Colors: Pc > 1e-4 = red, > 1e-6 = orange, else yellow.
export {};
