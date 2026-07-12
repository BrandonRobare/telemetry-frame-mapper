// Route matching for the mobile quick-check view (issue #364). A phone-sized
// operator view lives at /mobile (or the /m shorthand) and bypasses the
// desktop tab shell entirely — same pattern as ShareViewer's /view/share/.

const MOBILE_PATHS = new Set(['/mobile', '/m'])

export function isMobileRoute(pathname: string): boolean {
  const trimmed = pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
  return MOBILE_PATHS.has(trimmed)
}
