/** Display formatting for prices, quantities, changes and P&L. */

const DASH = '—'
const MINUS = '−'

function fixed(value: number, minFrac: number, maxFrac: number): string {
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: minFrac, maximumFractionDigits: maxFrac }).format(value)
}

/** Prices: 2 decimals, or up to 4 for prices below 1. */
export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH
  return fixed(value, 2, Math.abs(value) < 1 && value !== 0 ? 4 : 2).replace('-', MINUS)
}

/** Monetary amounts (market value, P&L): 2 decimals. */
export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH
  return fixed(value, 2, 2).replace('-', MINUS)
}

/** Signed amount: +1.23 / −1.23 / 0.00. */
export function formatSigned(value: number | null | undefined, format: (v: number) => string = formatMoney): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH
  const text = format(Math.abs(value))
  if (value > 0) return `+${text}`
  if (value < 0) return `${MINUS}${text}`
  return text
}

/** Percent units in, signed text out: 1.5 -> +1.50%. */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH
  return `${formatSigned(value, (v) => fixed(v, 2, 2))}%`
}

/** Plain number with up to `maxFrac` decimals (z-scores, generic metrics). */
export function formatNumber(value: number | null | undefined, maxFrac = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH
  return fixed(value, Math.min(2, maxFrac), maxFrac).replace('-', MINUS)
}

/** Quantities: up to 8 decimals, no trailing zeros. */
export function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH
  return fixed(value, 0, 8).replace('-', MINUS)
}

/** ISO date (YYYY-MM-DD) or timestamp to a short date. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return DASH
  return value.slice(0, 10)
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return DASH
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return DASH
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

/** Tailwind text colour for a gain (green), loss (red) or neither. */
export function gainLossClass(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value) || value === 0) return 'text-slate-700'
  return value > 0 ? 'text-emerald-600' : 'text-red-600'
}

/** Today's date as YYYY-MM-DD in local time, for date inputs. */
export function todayIso(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}
