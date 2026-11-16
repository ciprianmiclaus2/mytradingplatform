const DECIMAL_RE = /^\d{1,12}(\.\d{1,8})?$/

/** Validate a positive decimal typed by the user. Returns an error message or null. */
export function decimalError(value: string, label: string, required: boolean): string | null {
  const text = value.trim()
  if (!text) return required ? `${label} is required.` : null
  if (!DECIMAL_RE.test(text)) return `${label} must be a number with at most 8 decimals.`
  if (Number(text) <= 0) return `${label} must be greater than zero.`
  return null
}
