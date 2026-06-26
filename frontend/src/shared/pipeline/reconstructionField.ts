export interface ReconstructionField {
  /** count*3 scattered positions (raw, pre-solve). */
  scatter: Float32Array
  /** count*3 target positions sampled on the terrain heightfield. */
  target: Float32Array
  /** per-point 0..1 tint offset for color variety. */
  tint: Float32Array
}

// mulberry32 — a tiny deterministic PRNG (mirrors pointFieldData.ts) so a given
// seed always yields the same field (stable across renders, unit-testable).
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

/** Radius of the terrain disc the target points sample. */
export const FIELD_RADIUS = 1.1

/** Terrain height at (x, z): two gaussian bumps over a dished base. Pure; output in ~[-0.18, 0.69]. */
export function heightAt(x: number, z: number): number {
  const b1 = 0.55 * Math.exp(-(((x - 0.15) ** 2 + (z + 0.1) ** 2) / 0.35))
  const b2 = 0.32 * Math.exp(-(((x + 0.45) ** 2 + (z - 0.35) ** 2) / 0.18))
  return b1 + b2 - 0.18
}

/**
 * Deterministically build the scatter + terrain-target buffers for the logo cloud.
 * Pure — same (count, seed) always yields identical buffers.
 */
export function generateReconstructionField(count: number, seed: number): ReconstructionField {
  const rand = mulberry32(seed)
  const scatter = new Float32Array(count * 3)
  const target = new Float32Array(count * 3)
  const tint = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    const j = i * 3
    // scatter: random within a loose volume
    scatter[j] = (rand() * 2 - 1) * 1.15
    scatter[j + 1] = rand() * 1.5 - 0.25
    scatter[j + 2] = (rand() * 2 - 1) * 1.15
    // target: a point on the terrain disc (sqrt for uniform area distribution)
    const r = Math.sqrt(rand()) * FIELD_RADIUS
    const angle = rand() * Math.PI * 2
    const tx = r * Math.cos(angle)
    const tz = r * Math.sin(angle)
    target[j] = tx
    target[j + 1] = heightAt(tx, tz)
    target[j + 2] = tz
    tint[i] = rand()
  }
  return { scatter, target, tint }
}
