export function formatInstallCommands(commands: Record<string, string>): string {
  const entries = Object.entries(commands)
  if (entries.length === 1) return entries[0][1]
  return entries.map(([platform, command]) => `${platform}: ${command}`).join('\n')
}

export function formatEffectiveSplatSettings(settings: {
  splat_backend: string | null
  iterations: number
  max_gaussians: number
}): string {
  if (settings.splat_backend === null) return 'COLMAP only · no splat training backend'
  const backend = settings.splat_backend === 'metal_msplat'
    ? 'Metal msplat'
    : settings.splat_backend === 'cuda_gsplat'
      ? 'CUDA gsplat'
      : settings.splat_backend
  const number = new Intl.NumberFormat('en-US')
  return `${backend} · ${number.format(settings.iterations)} iterations · ${number.format(settings.max_gaussians)} Gaussian cap`
}
