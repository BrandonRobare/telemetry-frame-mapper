// Client-side mirror of the backend import-path rules (backend/routers/sessions.py):
// the path must be relative and stay inside the server's imports/ directory.
// The backend remains authoritative — this only gives users an early, clearer error
// (regression guard for walkthrough finding F4).
export function validateImportPath(raw: string): string | null {
  const trimmed = raw.trim()
  if (!trimmed) return 'Folder path is required'
  if (/^[a-zA-Z]:/.test(trimmed) || /^[\\/]/.test(trimmed)) {
    return 'Folder path must be relative (inside the imports/ folder)'
  }
  const segments = trimmed.split(/[\\/]/).filter((segment) => segment !== '')
  if (segments.length === 0 || segments.some((segment) => segment === '.' || segment === '..')) {
    return 'Folder path contains invalid segments'
  }
  return null
}
