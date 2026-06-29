import { useCallback, useEffect, useRef } from 'react'
import { useReducedMotion, useSpring } from 'framer-motion'

/* Cursor-reactive glass interaction. Returns a ref + pointer handlers to spread
   onto a panel. Spring-driven tilt (rotateX/rotateY) and lift give the
   "responsive" feel; the cursor position drives the specular highlight via the
   --mx/--my CSS vars. All values are written as CSS custom properties so the
   visual lives in .tg-glass (index.css) and the hook works on any element.

   Reduced motion: handlers become inert and the panel renders static. */

const SPRING = { stiffness: 220, damping: 22, mass: 0.6 } as const
const LIFT_SPRING = { stiffness: 200, damping: 24, mass: 0.5 } as const
const TILT_RANGE = 16 // max degrees of tilt at the panel edges

export function useCursorGlass<T extends HTMLElement = HTMLDivElement>(intensity = 1) {
  const ref = useRef<T | null>(null)
  const reduce = useReducedMotion()

  // tx: horizontal cursor → rotateY, ty: vertical cursor → rotateX
  const tx = useSpring(0, SPRING)
  const ty = useSpring(0, SPRING)
  const lift = useSpring(0, LIFT_SPRING)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const write = () => {
      el.style.setProperty('--tx', tx.get().toFixed(2))
      el.style.setProperty('--ty', ty.get().toFixed(2))
      el.style.setProperty('--lift', lift.get().toFixed(3))
    }
    write()
    const unsub = [tx.on('change', write), ty.on('change', write), lift.on('change', write)]
    return () => unsub.forEach((u) => u())
  }, [tx, ty, lift])

  const onPointerMove = useCallback(
    (e: React.PointerEvent<T>) => {
      const el = ref.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const px = (e.clientX - r.left) / r.width
      const py = (e.clientY - r.top) / r.height
      tx.set((px - 0.5) * TILT_RANGE * intensity)
      ty.set(-(py - 0.5) * TILT_RANGE * intensity)
      lift.set(1)
      el.style.setProperty('--mx', `${(px * 100).toFixed(1)}%`)
      el.style.setProperty('--my', `${(py * 100).toFixed(1)}%`)
    },
    [intensity, tx, ty, lift],
  )

  const onPointerLeave = useCallback(() => {
    tx.set(0)
    ty.set(0)
    lift.set(0)
  }, [tx, ty, lift])

  const handlers = reduce ? {} : { onPointerMove, onPointerLeave }
  return { ref, handlers, reduce }
}
