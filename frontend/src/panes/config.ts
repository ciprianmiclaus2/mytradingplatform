/**
 * Helpers to read pane configuration safely. Configuration comes from
 * localStorage, so every value is checked before use.
 */
export function readString(config: Record<string, unknown>, key: string): string | undefined {
  const value = config[key]
  return typeof value === 'string' && value.length > 0 ? value : undefined
}

export function readBoolean(config: Record<string, unknown>, key: string, fallback = false): boolean {
  const value = config[key]
  return typeof value === 'boolean' ? value : fallback
}

export function readObject(config: Record<string, unknown>, key: string): Record<string, unknown> | undefined {
  const value = config[key]
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined
}
