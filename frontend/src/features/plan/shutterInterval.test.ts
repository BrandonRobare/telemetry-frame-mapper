import { describe, it, expect } from 'vitest'
import {
  CAMERA_PRESETS,
  DJI_MIN_INTERVAL_S,
  computeShutterInterval,
} from './shutterInterval'

describe('computeShutterInterval', () => {
  it('computes footprint, spacing, and interval for the generic wide camera', () => {
    // Matches backend/services/mission_planner.py::generate_lawnmower defaults:
    // altitude_m = 200 ft * 0.3048 = 60.96 m
    // gh = 2 * 60.96 * tan(64/2 deg) = 76.186 m
    // spacing = gh * (1 - 0.80) = 15.237 m
    // interval = spacing / 10 m/s = 1.524 s
    const result = computeShutterInterval({
      speedMs: 10,
      altitudeFt: 200,
      forwardOverlapPct: 80,
      fovVerticalDeg: 64,
    })
    expect(result).not.toBeNull()
    expect(result!.footprintForwardM).toBeCloseTo(76.186, 2)
    expect(result!.photoSpacingM).toBeCloseTo(15.237, 2)
    expect(result!.shutterIntervalS).toBeCloseTo(1.524, 2)
  })

  it('computes interval for a DJI Mini 3/4 Pro profile', () => {
    // fov_v 52.2 deg (backend camera_calibration.py default profile)
    // altitude_m = 300 ft * 0.3048 = 91.44 m
    // gh = 2 * 91.44 * tan(26.1 deg) = 89.592 m
    // spacing = gh * (1 - 0.70) = 26.878 m
    // interval = spacing / 5 m/s = 5.376 s
    const result = computeShutterInterval({
      speedMs: 5,
      altitudeFt: 300,
      forwardOverlapPct: 70,
      fovVerticalDeg: 52.2,
    })
    expect(result).not.toBeNull()
    expect(result!.footprintForwardM).toBeCloseTo(89.592, 2)
    expect(result!.photoSpacingM).toBeCloseTo(26.878, 2)
    expect(result!.shutterIntervalS).toBeCloseTo(5.376, 2)
    expect(result!.belowDjiMinInterval).toBe(false)
  })

  it('flags intervals below the typical DJI 2 s minimum', () => {
    const result = computeShutterInterval({
      speedMs: 10,
      altitudeFt: 200,
      forwardOverlapPct: 80,
      fovVerticalDeg: 64,
    })
    expect(result!.shutterIntervalS).toBeLessThan(DJI_MIN_INTERVAL_S)
    expect(result!.belowDjiMinInterval).toBe(true)
  })

  it('does not flag an interval exactly at the DJI minimum', () => {
    // Choose speed so interval is exactly spacing / speed = 2 s.
    const base = computeShutterInterval({
      speedMs: 1,
      altitudeFt: 200,
      forwardOverlapPct: 80,
      fovVerticalDeg: 64,
    })!
    const speedForTwoSeconds = base.photoSpacingM / DJI_MIN_INTERVAL_S
    const result = computeShutterInterval({
      speedMs: speedForTwoSeconds,
      altitudeFt: 200,
      forwardOverlapPct: 80,
      fovVerticalDeg: 64,
    })
    expect(result!.shutterIntervalS).toBeCloseTo(DJI_MIN_INTERVAL_S, 6)
    expect(result!.belowDjiMinInterval).toBe(false)
  })

  it('returns null for degenerate inputs', () => {
    const valid = {
      speedMs: 5,
      altitudeFt: 200,
      forwardOverlapPct: 80,
      fovVerticalDeg: 64,
    }
    expect(computeShutterInterval({ ...valid, speedMs: 0 })).toBeNull()
    expect(computeShutterInterval({ ...valid, speedMs: -1 })).toBeNull()
    expect(computeShutterInterval({ ...valid, altitudeFt: 0 })).toBeNull()
    expect(computeShutterInterval({ ...valid, altitudeFt: -50 })).toBeNull()
    expect(computeShutterInterval({ ...valid, forwardOverlapPct: 100 })).toBeNull()
    expect(computeShutterInterval({ ...valid, forwardOverlapPct: -5 })).toBeNull()
    expect(computeShutterInterval({ ...valid, fovVerticalDeg: 0 })).toBeNull()
    expect(computeShutterInterval({ ...valid, fovVerticalDeg: 180 })).toBeNull()
    expect(computeShutterInterval({ ...valid, speedMs: Number.NaN })).toBeNull()
  })

  it('zero overlap means spacing equals the full footprint', () => {
    const result = computeShutterInterval({
      speedMs: 5,
      altitudeFt: 200,
      forwardOverlapPct: 0,
      fovVerticalDeg: 64,
    })
    expect(result!.photoSpacingM).toBeCloseTo(result!.footprintForwardM, 6)
  })
})

describe('CAMERA_PRESETS', () => {
  it('mirrors the backend default DJI camera profiles', () => {
    // Values must stay in sync with
    // backend/services/camera_calibration.py::default_camera_profiles()
    const byName = Object.fromEntries(CAMERA_PRESETS.map((p) => [p.name, p]))
    expect(byName['DJI Mini 3/4 Pro wide camera'].fovVerticalDeg).toBeCloseTo(52.2)
    expect(byName['DJI Air 2S wide camera'].fovVerticalDeg).toBeCloseTo(55.3)
    expect(byName['DJI Mavic 3 wide camera'].fovVerticalDeg).toBeCloseTo(55.8)
  })

  it('includes the generic planner default (84/64 deg) first', () => {
    expect(CAMERA_PRESETS[0].fovHorizontalDeg).toBe(84)
    expect(CAMERA_PRESETS[0].fovVerticalDeg).toBe(64)
  })
})
