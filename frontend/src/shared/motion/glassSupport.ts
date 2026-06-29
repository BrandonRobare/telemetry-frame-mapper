/* Feature-detect whether SVG-displacement refraction inside backdrop-filter is
   reliable. The Liquid-Glass refraction (backdrop-filter: ... url(#filter)) only
   works dependably in Chromium — Firefox/Safari either ignore the url() term or
   drop the whole declaration. When unsupported we omit the url() so the panel
   still gets blur + specular + tilt (graceful degradation). */

let cached: boolean | null = null

export function supportsGlassRefraction(): boolean {
  if (cached !== null) return cached
  if (typeof window === 'undefined' || typeof CSS === 'undefined' || !CSS.supports) {
    return (cached = false)
  }
  const hasBackdrop =
    CSS.supports('backdrop-filter', 'blur(2px)') ||
    CSS.supports('-webkit-backdrop-filter', 'blur(2px)')
  const ua = navigator.userAgent
  const isChromium = 'chrome' in window || /\bChrome\/|\bChromium\/|\bEdg\//.test(ua)
  const isFirefox = /\bFirefox\//.test(ua)
  cached = hasBackdrop && isChromium && !isFirefox
  return cached
}

/** Backdrop-filter value for inline (non-component) glass usages — drops the
    refraction term when unsupported so the blur still applies. */
export function glassBackdrop(refraction = true): string {
  const refract = refraction && supportsGlassRefraction() ? ' url(#glassDisplace)' : ''
  return `blur(var(--glass-blur)) saturate(1.35)${refract}`
}
