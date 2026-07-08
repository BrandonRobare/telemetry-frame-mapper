import { describe, expect, it } from 'vitest'
import type { Session } from '../../types/api'
import { collectTags, filterSessionsByTag, parseTagInput } from './sessionTags'

function makeSession(id: number, tags: string[]): Session {
  return {
    id,
    name: `s${id}`,
    folder_path: '/tmp',
    import_mode: 'full',
    imported_at: '2026-07-08T00:00:00Z',
    photo_count: 0,
    usable_count: 0,
    notes: null,
    tags,
    project_id: null,
  }
}

describe('parseTagInput', () => {
  it('splits on commas and trims whitespace', () => {
    expect(parseTagInput('roof, solar , north-field')).toEqual(['roof', 'solar', 'north-field'])
  })

  it('drops empty entries and duplicates', () => {
    expect(parseTagInput(' roof,, roof ,  ')).toEqual(['roof'])
  })

  it('returns empty array for blank input', () => {
    expect(parseTagInput('   ')).toEqual([])
  })

  it('caps tag length at 40 characters', () => {
    const long = 'x'.repeat(50)
    expect(parseTagInput(long)).toEqual(['x'.repeat(40)])
  })
})

describe('collectTags', () => {
  it('returns unique tags sorted alphabetically', () => {
    const sessions = [makeSession(1, ['solar', 'roof']), makeSession(2, ['roof', 'annex'])]
    expect(collectTags(sessions)).toEqual(['annex', 'roof', 'solar'])
  })

  it('returns empty array when no sessions have tags', () => {
    expect(collectTags([makeSession(1, [])])).toEqual([])
  })
})

describe('filterSessionsByTag', () => {
  const sessions = [makeSession(1, ['roof']), makeSession(2, ['solar']), makeSession(3, [])]

  it('returns all sessions when tag is null', () => {
    expect(filterSessionsByTag(sessions, null)).toEqual(sessions)
  })

  it('returns only sessions carrying the tag', () => {
    expect(filterSessionsByTag(sessions, 'roof').map((s) => s.id)).toEqual([1])
  })

  it('returns empty array when nothing matches', () => {
    expect(filterSessionsByTag(sessions, 'missing')).toEqual([])
  })
})
