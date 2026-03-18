/** A satellite from the catalog API */
export interface CatalogEntry {
  norad_id: number;
  name: string;
  line1: string;
  line2: string;
  object_type: "LEO" | "MEO" | "GEO" | "OTHER";
}

/** A conjunction event from the API */
export interface Conjunction {
  norad_id_primary: number;
  norad_id_secondary: number;
  tca: string; // ISO datetime
  miss_distance_km: number;
  relative_velocity_km_s: number;
  pc: number | null;
}

/** Detailed object info from /api/objects/{id} */
export interface ObjectDetail {
  norad_id: number;
  name: string;
  object_type: string;
  inclination_deg: number;
  eccentricity: number;
  raan_deg: number;
  arg_perigee_deg: number;
  mean_anomaly_deg: number;
  mean_motion_rev_day: number;
  bstar: number;
  epoch: string;
  intl_designator: string;
  period_min: number;
  semi_major_axis_km: number;
  apogee_alt_km: number;
  perigee_alt_km: number;
}

/** Filter state */
export interface FilterState {
  showLEO: boolean;
  showMEO: boolean;
  showGEO: boolean;
  showOTHER: boolean;
  searchText: string;
}

/** Time control state */
export interface TimeState {
  playing: boolean;
  speedMultiplier: number;
  simulationTime: Date;
}
