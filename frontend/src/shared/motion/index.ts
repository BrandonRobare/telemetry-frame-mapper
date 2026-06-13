import type { Transition, Variants } from 'framer-motion'

/* Centralized motion presets so transitions stay consistent and subtle.
   Reduced-motion is handled globally via <MotionConfig reducedMotion="user">
   in main.tsx plus the prefers-reduced-motion guard in index.css. */

export const easeOut = [0.22, 1, 0.36, 1] as const
export const durations = { fast: 0.12, base: 0.18, slow: 0.28 } as const

export const tabTransition: Transition = { duration: durations.base, ease: easeOut }

/** Cross-fade + small vertical slide — used for tab panel transitions. */
export const fadeSlide: Variants = {
  initial: { opacity: 0, y: 4 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4 },
}
