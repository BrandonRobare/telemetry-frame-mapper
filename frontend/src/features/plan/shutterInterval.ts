// ---------------------------------------------------------------------------
// Shutter-interval / overlap calculator — pure math for DJI mission planning.
//
// Formulas mirror backend/services/mission_planner.py::generate_lawnmower:
//   altitude_m          = altitude_ft * 0.3048
//   footprint_forward_m = 2 * altitude_m * tan(fov_v / 2)
//   photo_spacing_m     = footprint_forward_m * (1 - forward_overlap)
// plus the field-ops step the backend does not need:
//   shutter_interval_s  = photo_spacing_m / speed_m_s
//
// Camera FOV presets mirror
// backend/services/camera_calibration.py::default_camera_profiles().
// Keep both in sync when adding profiles.
// ---------------------------------------------------------------------------

export interface CameraPreset {
  name: string
  fovHorizontalDeg: number
  fovVerticalDeg: number
}

export const CAMERA_PRESETS: CameraPreset[] = [
  // Generic planner default — matches mission_planner.py fov_h/fov_v defaults.
  { name: 'Generic wide (planner default)', fovHorizontalDeg: 84.0, fovVerticalDeg: 64.0 },
  { name: 'DJI Mini 3/4 Pro wide camera', fovHorizontalDeg: 73.4, fovVerticalDeg: 52.2 },
  { name: 'DJI Air 2S wide camera', fovHorizontalDeg: 76.5, fovVerticalDeg: 55.3 },
  { name: 'DJI Mavic 3 wide camera', fovHorizontalDeg: 70.3, fovVerticalDeg: 55.8 },
]

const FT_TO_M = 0.3048

/** Typical minimum photo interval a DJI controller allows in timed-shot mode. */
export const DJI_MIN_INTERVAL_S = 2

export interface ShutterIntervalInput {
  /** Ground speed in m/s (> 0) */
  speedMs: number
  /** Flight altitude AGL in feet (> 0) */
  altitudeFt: number
  /** Target forward overlap, 0–99.x % */
  forwardOverlapPct: number
  /** Vertical (along-track) field of view in degrees, 0 < fov < 180 */
  fovVerticalDeg: number
}

export interface ShutterIntervalResult {
  /** Ground footprint length along the flight direction (m) */
  footprintForwardM: number
  /** Distance between consecutive photos (m) */
  photoSpacingM: number
  /** Recommended shutter interval (s) */
  shutterIntervalS: number
  /** True when the interval is faster than DJI_MIN_INTERVAL_S */
  belowDjiMinInterval: boolean
}

/** Returns null when any input is degenerate (non-finite or out of range). */
export function computeShutterInterval(
  input: ShutterIntervalInput,
): ShutterIntervalResult | null {
  const { speedMs, altitudeFt, forwardOverlapPct, fovVerticalDeg } = input
  if (!Number.isFinite(speedMs) || speedMs <= 0) return null
  if (!Number.isFinite(altitudeFt) || altitudeFt <= 0) return null
  if (!Number.isFinite(forwardOverlapPct) || forwardOverlapPct < 0 || forwardOverlapPct >= 100) {
    return null
  }
  if (!Number.isFinite(fovVerticalDeg) || fovVerticalDeg <= 0 || fovVerticalDeg >= 180) {
    return null
  }

  const altitudeM = altitudeFt * FT_TO_M
  const footprintForwardM = 2 * altitudeM * Math.tan((fovVerticalDeg * Math.PI) / 360)
  const photoSpacingM = footprintForwardM * (1 - forwardOverlapPct / 100)
  const shutterIntervalS = photoSpacingM / speedMs

  return {
    footprintForwardM,
    photoSpacingM,
    shutterIntervalS,
    belowDjiMinInterval: shutterIntervalS < DJI_MIN_INTERVAL_S,
  }
}
