import { describe, expect, it } from 'vitest'
import { latestFootprintId, mergeFootprintPage } from './useFootprints'
import type { Footprint } from '../../../types/api'

function fp(id: number): Footprint {
  return {
    id,
    image_id: id,
    geom_wkt: '',
    geom_geojson: '{"type":"Polygon","coordinates":[]}',
    ground_width_m: 1,
    ground_height_m: 1,
    heading_estimated: true,
  }
}

describe('mergeFootprintPage', () => {
  it('appends a new page onto the accumulated list', () => {
    const existing = [fp(1), fp(2)]
    const merged = mergeFootprintPage(existing, [fp(3), fp(4)])
    expect(merged.map((f) => f.id)).toEqual([1, 2, 3, 4])
  })

  it('returns the existing list unchanged when the new page is empty', () => {
    const existing = [fp(1)]
    const merged = mergeFootprintPage(existing, [])
    expect(merged).toBe(existing)
  })

  it('does not mutate the existing array', () => {
    const existing = [fp(1)]
    mergeFootprintPage(existing, [fp(2)])
    expect(existing).toEqual([fp(1)])
  })
})

describe('latestFootprintId', () => {
  it('returns the highest id in the list', () => {
    expect(latestFootprintId([fp(3), fp(7), fp(2)])).toBe(7)
  })

  it('returns 0 for an empty list', () => {
    expect(latestFootprintId([])).toBe(0)
  })
})
