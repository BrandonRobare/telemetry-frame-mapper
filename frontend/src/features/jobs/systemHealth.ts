export function formatInstallCommands(commands: Record<string, string>): string {
  const entries = Object.entries(commands)
  if (entries.length === 1) return entries[0][1]
  return entries.map(([platform, command]) => `${platform}: ${command}`).join('\n')
}
