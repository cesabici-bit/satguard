// SatelliteLayer is integrated directly into Globe.tsx for performance.
// The PointPrimitiveCollection + animation loop lives in Globe.tsx.
// This file exists as a documented placeholder.
//
// Architecture decision: keeping propagation + rendering in a single component
// avoids React re-render overhead on 30K+ points per frame.
export {};
