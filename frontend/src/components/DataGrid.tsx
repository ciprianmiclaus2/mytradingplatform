import { useMemo, useState, type ReactNode } from 'react'
import { compareSortValues, type SortDirection, type SortValue } from './sorting'

export type { SortDirection, SortValue }

export interface Column<T> {
  key: string
  header: ReactNode
  /** Accessible / tooltip name, when `header` is not plain text. */
  label?: string
  align?: 'left' | 'right' | 'center'
  /** Value used for sorting. Columns without one are not sortable. */
  sortValue?: (row: T) => SortValue
  render: (row: T) => ReactNode
  /** Extra classes for body cells (may depend on the row). */
  cellClassName?: (row: T) => string
}

export interface FooterRow {
  key: string
  /** Cells by column key; missing keys render empty cells. */
  cells: Record<string, ReactNode>
  className?: string
}

export interface SortState {
  key: string
  direction: SortDirection
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[] | undefined
  rowKey: (row: T) => string
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  emptyMessage?: ReactNode
  footerRows?: FooterRow[]
  defaultSort?: SortState
  rowClassName?: (row: T) => string
  /** Accessible table name. */
  label: string
}

const alignClass = { left: 'text-left', right: 'text-right', center: 'text-center' } as const

/** Sortable table with loading, error and empty states, shared by all panes. */
export function DataGrid<T>({
  columns,
  rows,
  rowKey,
  loading = false,
  error = null,
  onRetry,
  emptyMessage = 'No data.',
  footerRows = [],
  defaultSort,
  rowClassName,
  label,
}: Props<T>) {
  const [sort, setSort] = useState<SortState | null>(defaultSort ?? null)

  const sorted = useMemo(() => {
    if (!rows) return []
    const column = sort ? columns.find((c) => c.key === sort.key) : undefined
    if (!sort || !column?.sortValue) return rows
    const value = column.sortValue
    // Stable sort: ties keep the backend order.
    return rows
      .map((row, index) => ({ row, index }))
      .sort((a, b) => compareSortValues(value(a.row), value(b.row), sort.direction) || a.index - b.index)
      .map((item) => item.row)
  }, [rows, columns, sort])

  const toggleSort = (key: string) =>
    setSort((current) =>
      current?.key === key
        ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: 'asc' },
    )

  const hasRows = rows !== undefined && rows.length > 0

  return (
    <div className="text-sm">
      {error && (
        <div role="alert" className="flex items-center gap-2 border-b border-red-200 bg-red-50 px-3 py-1.5 text-red-700">
          <span className="min-w-0 flex-1">
            {error}
            {hasRows && <span className="text-red-600/80"> Showing the last loaded data.</span>}
          </span>
          {onRetry && (
            <button type="button" onClick={onRetry} className="rounded border border-red-300 px-2 py-0.5 text-xs hover:bg-red-100">
              Retry
            </button>
          )}
        </div>
      )}
      <table aria-label={label} aria-busy={loading} className="w-full border-collapse">
        <thead className="sticky top-0 z-10 bg-white">
          <tr className="border-b border-slate-200">
            {columns.map((column) => {
              const align = alignClass[column.align ?? 'left']
              const active = sort?.key === column.key
              const ariaSort = active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'
              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={column.sortValue ? ariaSort : undefined}
                  title={column.label}
                  className={`whitespace-nowrap px-2 py-1.5 text-xs font-medium text-slate-500 ${align}`}
                >
                  {column.sortValue ? (
                    <button
                      type="button"
                      onClick={() => toggleSort(column.key)}
                      aria-label={column.label ? `Sort by ${column.label}` : undefined}
                      className="inline-flex items-center gap-1 hover:text-slate-900"
                    >
                      {column.header}
                      <span aria-hidden className={active ? 'text-slate-700' : 'text-slate-300'}>
                        {active && sort.direction === 'desc' ? '▼' : '▲'}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={rowKey(row)} className={`border-b border-slate-100 hover:bg-slate-50 ${rowClassName?.(row) ?? ''}`}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`whitespace-nowrap px-2 py-1 tabular-nums ${alignClass[column.align ?? 'left']} ${column.cellClassName?.(row) ?? ''}`}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {hasRows && footerRows.length > 0 && (
          <tfoot>
            {footerRows.map((footer) => (
              <tr key={footer.key} className={`border-t border-slate-300 bg-slate-50 font-medium ${footer.className ?? ''}`}>
                {columns.map((column) => (
                  <td key={column.key} className={`whitespace-nowrap px-2 py-1 tabular-nums ${alignClass[column.align ?? 'left']}`}>
                    {footer.cells[column.key] ?? null}
                  </td>
                ))}
              </tr>
            ))}
          </tfoot>
        )}
      </table>
      {!hasRows && (
        <p className="px-3 py-6 text-center text-slate-500" role={loading ? 'status' : undefined}>
          {loading ? 'Loading…' : rows === undefined && error ? 'No data available.' : emptyMessage}
        </p>
      )}
    </div>
  )
}
