let fallbackSequence = 0

/** Generates an ID for browser-local UI state, not a security token. */
export function createId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  fallbackSequence += 1
  return `${prefix}-${Date.now().toString(36)}-${fallbackSequence.toString(36)}-${Math.random().toString(36).slice(2)}`
}
