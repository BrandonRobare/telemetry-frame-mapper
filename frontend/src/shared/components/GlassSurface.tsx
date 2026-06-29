import React from 'react'
import { useCursorGlass } from '../motion/useCursorGlass'
import { supportsGlassRefraction } from '../motion/glassSupport'

interface GlassSurfaceProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Refract the content behind the panel. Auto-disabled where unsupported.
      Reserve `true` for surfaces with rich content behind them (hero, map). */
  refraction?: boolean
  /** Tilt/specular strength (0–1+). Lower for small/dense chips. */
  intensity?: number
  /** Wire up cursor tilt + specular. Off = static glass (e.g. toasts). */
  interactive?: boolean
  /** Corner radius in px. Default 0 — sharp editorial panes. */
  radius?: number
}

/* The reusable Terrain-glass panel. Composes the cursor hook with the .tg-glass
   styling from index.css. Renders a div; spread `style`/`className` to theme it
   (e.g. a custom translucent background). */
export function GlassSurface({
  refraction = true,
  intensity = 1,
  interactive = true,
  radius = 0,
  className = '',
  style,
  children,
  ...rest
}: GlassSurfaceProps) {
  const { ref, handlers } = useCursorGlass<HTMLDivElement>(intensity)
  const useRefract = refraction && supportsGlassRefraction()

  return (
    <div
      ref={interactive ? ref : undefined}
      {...(interactive ? handlers : {})}
      className={`tg-glass ${interactive ? 'tg-glass--interactive' : ''} ${className}`.trim()}
      style={
        {
          '--glass-radius': `${radius}px`,
          '--refract': useRefract ? 'url(#glassDisplace)' : ' ',
          ...style,
        } as React.CSSProperties
      }
      {...rest}
    >
      {children}
    </div>
  )
}

export default GlassSurface
