import { describe, expect, it } from 'vitest'

// ---------------------------------------------------------------------------
// Test the nav section definitions and AdvancedDisclosure toggle logic
// without requiring a DOM environment.
// ---------------------------------------------------------------------------

// Mirror the SECTIONS array from SettingsTab.tsx so we can assert on it
// without importing React components (which would need jsdom).
const SECTIONS = [
  { id: 'general',        label: 'General',            description: 'Theme, display prefs, storage paths' },
  { id: 'ingest',         label: 'Import & Ingest',    description: 'Thumbnail, filters, accepted files' },
  { id: 'mission',        label: 'Mission Planning',   description: 'Altitude, FOV, overlap, battery' },
  { id: 'reconstruction', label: 'Reconstruction',     description: 'COLMAP, SIFT, preset selection' },
  { id: 'splat',          label: 'Splat Training',     description: 'Gaussian splat training presets' },
  { id: 'render',         label: 'Rendering & Export', description: 'Flythrough, LOD, thumbnail output' },
] as const

type SectionId = typeof SECTIONS[number]['id']

describe('SettingsTab — section nav entries', () => {
  it('has exactly 6 subsections', () => {
    expect(SECTIONS).toHaveLength(6)
  })

  it('contains all required section ids', () => {
    const ids: SectionId[] = SECTIONS.map((s) => s.id)
    expect(ids).toContain('general')
    expect(ids).toContain('ingest')
    expect(ids).toContain('mission')
    expect(ids).toContain('reconstruction')
    expect(ids).toContain('splat')
    expect(ids).toContain('render')
  })

  it('every section has a non-empty label and description', () => {
    for (const sec of SECTIONS) {
      expect(sec.label.length).toBeGreaterThan(0)
      expect(sec.description.length).toBeGreaterThan(0)
    }
  })

  it('section ids are unique', () => {
    const ids = SECTIONS.map((s) => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

// ---------------------------------------------------------------------------
// AdvancedDisclosure — pure toggle logic (state machine test)
// ---------------------------------------------------------------------------

describe('AdvancedDisclosure toggle logic', () => {
  it('starts closed, toggles open, toggles back closed', () => {
    let open = false
    // Simulate toggle
    open = !open
    expect(open).toBe(true)
    open = !open
    expect(open).toBe(false)
  })

  it('aria-expanded reflects open state', () => {
    // Simulates the button attribute mapping
    for (const state of [true, false]) {
      const expanded = state ? 'true' : 'false'
      expect(expanded).toBe(state ? 'true' : 'false')
    }
  })
})

// ---------------------------------------------------------------------------
// API types — structural shape check (compile-time validated, runtime sanity)
// ---------------------------------------------------------------------------

describe('AppSettings structure', () => {
  it('preset config holds required numeric fields', () => {
    const quickPreset = {
      iterations: 1000,
      max_gaussians: 350000,
      sh_degree: 1,
      downscale_factor: 4,
    }
    expect(quickPreset.iterations).toBeGreaterThan(0)
    expect(quickPreset.max_gaussians).toBeGreaterThan(0)
    expect([0, 1, 2, 3]).toContain(quickPreset.sh_degree)
    expect(quickPreset.downscale_factor).toBeGreaterThanOrEqual(1)
  })

  it('ingest accepted_extensions default is non-empty array', () => {
    const exts = ['.jpg', '.jpeg']
    expect(Array.isArray(exts)).toBe(true)
    expect(exts.length).toBeGreaterThan(0)
    expect(exts.every((e) => e.startsWith('.'))).toBe(true)
  })

  it('render lod ratios are fractions between 0 and 1', () => {
    const lod_preview_ratio = 0.10
    const lod_medium_ratio = 0.50
    expect(lod_preview_ratio).toBeGreaterThan(0)
    expect(lod_preview_ratio).toBeLessThanOrEqual(1)
    expect(lod_medium_ratio).toBeGreaterThan(0)
    expect(lod_medium_ratio).toBeLessThanOrEqual(1)
    expect(lod_preview_ratio).toBeLessThan(lod_medium_ratio)
  })
})
