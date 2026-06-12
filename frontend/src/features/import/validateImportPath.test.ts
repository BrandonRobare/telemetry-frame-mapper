import { describe, expect, it } from 'vitest'
import { validateImportPath } from './validateImportPath'

describe('validateImportPath', () => {
  it('accepts simple relative paths', () => {
    expect(validateImportPath('2026-05-02-field-a')).toBeNull()
    expect(validateImportPath('site-a/flight-1')).toBeNull()
    expect(validateImportPath('  padded  ')).toBeNull()
  })

  it('rejects absolute paths (F4 regression: backend requires relative-under-imports/)', () => {
    expect(validateImportPath('C:\\flights\\site-a')).toMatch(/must be relative/)
    expect(validateImportPath('/flights/site-a')).toMatch(/must be relative/)
    expect(validateImportPath('\\\\server\\share')).toMatch(/must be relative/)
  })

  it('rejects traversal and dot segments', () => {
    expect(validateImportPath('../escape')).toMatch(/invalid segments/)
    expect(validateImportPath('a/../b')).toMatch(/invalid segments/)
    expect(validateImportPath('./a')).toMatch(/invalid segments/)
  })

  it('rejects empty input', () => {
    expect(validateImportPath('')).toMatch(/required/)
    expect(validateImportPath('   ')).toMatch(/required/)
  })
})
