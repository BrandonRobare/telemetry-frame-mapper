// Smoothstep easing used for flythrough keyframe interpolation in the in-browser preview.
// Cross-implementation contract: the server-side renderer (backend/services/splat_trainer.py)
// must interpolate with the identical formula so preview and exported MP4 match.
export function smoothstep(t: number): number {
  return t * t * (3 - 2 * t)
}
