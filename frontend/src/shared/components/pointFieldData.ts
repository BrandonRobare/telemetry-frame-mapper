export interface FieldPoint {
  /** position in a 0..100 box */
  x: number
  y: number
  /** radius in viewBox units */
  r: number
  /** base opacity */
  o: number
  /** index into the terracotta/tan color set */
  c: number
}

/* mulberry32 — a tiny deterministic PRNG. A given seed always yields the same
   field, so the layout is stable across renders (and unit-testable). */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Deterministically scatter `count` points across a 0..100 box. Pure — exported for tests. */
export function generatePoints(count: number, seed: number): FieldPoint[] {
  const rand = mulberry32(seed)
  const points: FieldPoint[] = []
  for (let i = 0; i < count; i++) {
    points.push({
      x: rand() * 100,
      y: rand() * 100,
      r: 0.18 + rand() * 0.55,
      o: 0.22 + rand() * 0.5,
      c: Math.floor(rand() * 3),
    })
  }
  return points
}

/** Terracotta / tan point colors, indexed by `FieldPoint.c`. */
export const POINT_COLORS = ['var(--accent)', 'var(--tan)', 'var(--accent-strong)']
