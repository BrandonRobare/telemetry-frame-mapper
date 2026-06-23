export function filterReconstructionLogLines(lines: string[], query: string): string[] {
  const normalizedQuery = query.trim().toLowerCase()
  if (normalizedQuery.length === 0) return lines
  return lines.filter((line) => line.toLowerCase().includes(normalizedQuery))
}
