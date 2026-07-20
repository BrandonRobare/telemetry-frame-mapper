import type { Footprint } from '../../types/api'

export function comparisonFootprintGeoJson(footprints: Footprint[]) {
  return {
    type: 'FeatureCollection' as const,
    features: footprints.reduce<{ type: 'Feature'; geometry: unknown; properties: { id: number } }[]>(
      (features, footprint) => {
        try {
          features.push({
            type: 'Feature',
            geometry: JSON.parse(footprint.geom_geojson),
            properties: { id: footprint.id },
          })
        } catch {
          // A malformed footprint must not hide the rest of this session's map context.
        }
        return features
      },
      [],
    ),
  }
}

export function comparisonFootprintBounds(footprints: Footprint[]): [number, number][] {
  return comparisonFootprintGeoJson(footprints).features.flatMap((feature) => {
    const geometry = feature.geometry as { coordinates?: number[][][] } | null
    if (!geometry?.coordinates) return []
    return geometry.coordinates.flat(2).reduce<[number, number][]>((points, value, index, flat) => {
      if (index % 2 === 0 && typeof value === 'number' && typeof flat[index + 1] === 'number') {
        points.push([flat[index + 1] as number, value])
      }
      return points
    }, [])
  })
}
