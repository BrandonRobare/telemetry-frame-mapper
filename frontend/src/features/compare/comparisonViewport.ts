export function comparisonViewportSource(reconstructionId: number): `comparison:${number}` {
  return `comparison:${reconstructionId}`
}

export function shouldApplyComparisonViewport(source: string | undefined, reconstructionId: number) {
  return source !== comparisonViewportSource(reconstructionId)
}
