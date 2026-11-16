export type SortValue = number | string | boolean | null | undefined
export type SortDirection = 'asc' | 'desc'

/**
 * Compare for sorting. Missing values always sort last, in either direction,
 * so blanks never crowd the top of a sorted list.
 */
export function compareSortValues(a: SortValue, b: SortValue, direction: SortDirection): number {
  const aMissing = a === null || a === undefined || (typeof a === 'number' && Number.isNaN(a))
  const bMissing = b === null || b === undefined || (typeof b === 'number' && Number.isNaN(b))
  if (aMissing || bMissing) return aMissing === bMissing ? 0 : aMissing ? 1 : -1
  let result: number
  if (typeof a === 'string' && typeof b === 'string') {
    result = a.localeCompare(b, undefined, { sensitivity: 'base', numeric: true })
  } else {
    result = Number(a) - Number(b)
  }
  return direction === 'asc' ? result : -result
}
