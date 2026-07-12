import { describe, expect, it } from 'vitest'
import { isMobileRoute } from './mobileRoute'

describe('isMobileRoute', () => {
  it('matches /mobile', () => {
    expect(isMobileRoute('/mobile')).toBe(true)
  })

  it('matches /mobile/ with a trailing slash', () => {
    expect(isMobileRoute('/mobile/')).toBe(true)
  })

  it('matches the /m shorthand', () => {
    expect(isMobileRoute('/m')).toBe(true)
  })

  it('matches /m/ with a trailing slash', () => {
    expect(isMobileRoute('/m/')).toBe(true)
  })

  it('does not match the desktop root path', () => {
    expect(isMobileRoute('/')).toBe(false)
  })

  it('does not match unrelated paths', () => {
    expect(isMobileRoute('/view/share/abc123')).toBe(false)
  })

  it('does not match paths that merely start with the same letters', () => {
    expect(isMobileRoute('/mobiletest')).toBe(false)
    expect(isMobileRoute('/measure')).toBe(false)
  })
})
