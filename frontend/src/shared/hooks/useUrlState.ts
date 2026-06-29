import { useCallback, useEffect, useState } from 'react'

// Lightweight deep-link state: sync a single value to a URL query param without
// pulling in a router. Reading the param on init makes views bookmarkable and
// reload-safe; history.replaceState keeps the URL in step without growing the
// back stack on every change. A popstate listener handles browser back/forward.

export function getUrlParam(key: string): string | null {
  if (typeof window === 'undefined') return null
  return new URLSearchParams(window.location.search).get(key)
}

export function setUrlParam(key: string, value: string | null): void {
  if (typeof window === 'undefined') return
  const params = new URLSearchParams(window.location.search)
  if (value === null || value === '') params.delete(key)
  else params.set(key, value)
  const qs = params.toString()
  window.history.replaceState(null, '', qs ? `${window.location.pathname}?${qs}` : window.location.pathname)
}

/**
 * State synced to a URL query param. The initial value is taken from the URL
 * (falling back to `fallback`), and updates both React state and the URL.
 */
export function useUrlState(key: string, fallback: string): [string, (value: string) => void] {
  const [value, setValue] = useState<string>(() => getUrlParam(key) ?? fallback)

  useEffect(() => {
    const onPop = () => setValue(getUrlParam(key) ?? fallback)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [key, fallback])

  const set = useCallback(
    (next: string) => {
      setValue(next)
      setUrlParam(key, next)
    },
    [key],
  )

  return [value, set]
}
