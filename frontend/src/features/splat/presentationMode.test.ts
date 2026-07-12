import { describe, expect, it } from 'vitest'
import {
  cycleSpeed,
  distance3,
  interpolateKeyframes,
  lerpVec3,
  PRESENTATION_SPEEDS,
  scaledSegmentDurationMs,
  selectNarrationCallout,
  stepKeyframeIndex,
  type NarrationPoint,
  type PresentationKeyframe,
} from './presentationMode'

describe('lerpVec3', () => {
  it('returns the start vector at t=0 and end vector at t=1', () => {
    const a: [number, number, number] = [0, 0, 0]
    const b: [number, number, number] = [10, -20, 5]
    expect(lerpVec3(a, b, 0)).toEqual([0, 0, 0])
    expect(lerpVec3(a, b, 1)).toEqual([10, -20, 5])
  })

  it('interpolates linearly at intermediate t', () => {
    const a: [number, number, number] = [0, 0, 0]
    const b: [number, number, number] = [10, 10, 10]
    expect(lerpVec3(a, b, 0.5)).toEqual([5, 5, 5])
  })
})

describe('interpolateKeyframes', () => {
  const current: PresentationKeyframe = { position: [0, 0, 0], target: [1, 0, 0], duration_s: 3 }
  const next: PresentationKeyframe = { position: [10, 0, 0], target: [1, 0, 10], duration_s: 3 }

  it('interpolates position and target together', () => {
    const result = interpolateKeyframes(current, next, 0.5)
    expect(result.position).toEqual([5, 0, 0])
    expect(result.target).toEqual([1, 0, 5])
  })

  it('matches the endpoints exactly at ease=0 and ease=1', () => {
    expect(interpolateKeyframes(current, next, 0).position).toEqual(current.position)
    expect(interpolateKeyframes(current, next, 1).position).toEqual(next.position)
  })
})

describe('scaledSegmentDurationMs', () => {
  it('converts seconds to milliseconds at 1x speed', () => {
    expect(scaledSegmentDurationMs(3, 1)).toBe(3000)
  })

  it('halves the duration at 2x speed', () => {
    expect(scaledSegmentDurationMs(3, 2)).toBe(1500)
  })

  it('doubles the duration at 0.5x speed', () => {
    expect(scaledSegmentDurationMs(3, 0.5)).toBe(6000)
  })

  it('clamps to the minimum duration for very short/fast segments', () => {
    expect(scaledSegmentDurationMs(0.1, 4)).toBe(250)
  })

  it('falls back to 1x when given a non-positive speed', () => {
    expect(scaledSegmentDurationMs(3, 0)).toBe(3000)
    expect(scaledSegmentDurationMs(3, -1)).toBe(3000)
  })
})

describe('stepKeyframeIndex', () => {
  it('steps forward and backward within range', () => {
    expect(stepKeyframeIndex(1, 1, 4)).toBe(2)
    expect(stepKeyframeIndex(1, -1, 4)).toBe(0)
  })

  it('clamps at the last keyframe going forward', () => {
    expect(stepKeyframeIndex(3, 1, 4)).toBe(3)
  })

  it('clamps at the first keyframe going backward', () => {
    expect(stepKeyframeIndex(0, -1, 4)).toBe(0)
  })

  it('returns 0 when there are no keyframes', () => {
    expect(stepKeyframeIndex(0, 1, 0)).toBe(0)
  })
})

describe('cycleSpeed', () => {
  it('cycles forward through the speed table', () => {
    expect(cycleSpeed(0.5, 1)).toBe(1)
    expect(cycleSpeed(1, 1)).toBe(1.5)
    expect(cycleSpeed(1.5, 1)).toBe(2)
  })

  it('wraps from the fastest speed back to the slowest', () => {
    expect(cycleSpeed(2, 1)).toBe(0.5)
  })

  it('cycles backward and wraps from the slowest to the fastest', () => {
    expect(cycleSpeed(1, -1)).toBe(0.5)
    expect(cycleSpeed(0.5, -1)).toBe(2)
  })

  it('treats an unrecognized current speed as 1x', () => {
    expect(cycleSpeed(3, 1)).toBe(1.5)
  })

  it('exposes the speed table in ascending order', () => {
    expect(PRESENTATION_SPEEDS).toEqual([0.5, 1, 1.5, 2])
  })
})

describe('distance3', () => {
  it('computes euclidean distance', () => {
    expect(distance3([0, 0, 0], [3, 4, 0])).toBe(5)
  })

  it('is zero for coincident points', () => {
    expect(distance3([1, 2, 3], [1, 2, 3])).toBe(0)
  })
})

interface TestPoint extends NarrationPoint {
  label: string
}

const pointA: TestPoint = { id: 1, label: 'A', position: [0, 0, 0] }
const pointB: TestPoint = { id: 2, label: 'B', position: [20, 0, 0] }

describe('selectNarrationCallout', () => {
  it('returns null when there are no candidate points', () => {
    expect(selectNarrationCallout([0, 0, 0], [], null, 5)).toBeNull()
  })

  it('returns null when nothing is within the enter threshold', () => {
    expect(selectNarrationCallout([100, 0, 0], [pointA, pointB], null, 5)).toBeNull()
  })

  it('selects the nearest point within the enter threshold', () => {
    const result = selectNarrationCallout([1, 0, 0], [pointA, pointB], null, 5)
    expect(result?.id).toBe(1)
  })

  it('picks the closer of two in-range points', () => {
    const midpoint: [number, number, number] = [10, 0, 0]
    const result = selectNarrationCallout(midpoint, [pointA, pointB], null, 15)
    // Equidistant — either is acceptable, but it must return one of them.
    expect([1, 2]).toContain(result?.id)
  })

  it('keeps showing the current callout via hysteresis even past the enter threshold', () => {
    // enter=5, exit defaults to 7.5. Camera at distance 6 from A: outside enter,
    // inside exit, and B (dist ~14) is not a closer replacement.
    const cameraPos: [number, number, number] = [6, 0, 0]
    const result = selectNarrationCallout(cameraPos, [pointA, pointB], 1, 5)
    expect(result?.id).toBe(1)
  })

  it('releases the callout once the camera passes the exit threshold', () => {
    // enter=5, exit=7.5 by default. Distance from A is 8 — past exit.
    const cameraPos: [number, number, number] = [8, 0, 0]
    const result = selectNarrationCallout(cameraPos, [pointA, pointB], 1, 5)
    expect(result).toBeNull()
  })

  it('switches to a closer in-range point even while a current callout is active', () => {
    // Camera much closer to B than to A; A is still "current" from a prior frame.
    const cameraPos: [number, number, number] = [19, 0, 0]
    const result = selectNarrationCallout(cameraPos, [pointA, pointB], 1, 5)
    expect(result?.id).toBe(2)
  })

  it('respects an explicit exit threshold override', () => {
    // Distance from A is 6.
    const cameraPos: [number, number, number] = [6, 0, 0]
    const kept = selectNarrationCallout(cameraPos, [pointA, pointB], 1, 5, 6.5)
    expect(kept?.id).toBe(1)
    const released = selectNarrationCallout(cameraPos, [pointA, pointB], 1, 5, 5.5)
    expect(released).toBeNull()
  })
})
