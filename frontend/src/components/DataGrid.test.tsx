import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { gainLossClass } from '../utils/format'
import { DataGrid, type Column } from './DataGrid'
import { compareSortValues } from './sorting'

interface Row {
  ticker: string
  price: number | null
  change: number | null
}

const rows: Row[] = [
  { ticker: 'msft', price: 400, change: -1.5 },
  { ticker: 'AAPL', price: null, change: 2 },
  { ticker: 'VOD.L', price: 70.5, change: 0 },
  { ticker: 'BP.L', price: 450, change: null },
]

const columns: Column<Row>[] = [
  { key: 'ticker', header: 'Ticker', sortValue: (r) => r.ticker, render: (r) => r.ticker },
  { key: 'price', header: 'Price', align: 'right', sortValue: (r) => r.price, render: (r) => String(r.price ?? '—') },
  { key: 'change', header: 'Change', sortValue: (r) => r.change, cellClassName: (r) => gainLossClass(r.change), render: (r) => String(r.change ?? '—') },
  { key: 'note', header: 'Note', render: () => 'x' },
]

const firstColumn = () =>
  within(screen.getByRole('table'))
    .getAllByRole('row')
    .slice(1)
    .map((tr) => within(tr).getAllByRole('cell')[0].textContent)

describe('DataGrid', () => {
  it('renders rows in the given order until a column is sorted', () => {
    render(<DataGrid label="t" columns={columns} rows={rows} rowKey={(r) => r.ticker} />)
    expect(firstColumn()).toEqual(['msft', 'AAPL', 'VOD.L', 'BP.L'])
  })

  it('sorts tickers alphabetically, case-insensitive, both ways', async () => {
    render(<DataGrid label="t" columns={columns} rows={rows} rowKey={(r) => r.ticker} />)
    await userEvent.click(screen.getByRole('button', { name: /Ticker/ }))
    expect(firstColumn()).toEqual(['AAPL', 'BP.L', 'msft', 'VOD.L'])
    expect(screen.getByRole('columnheader', { name: /Ticker/ })).toHaveAttribute('aria-sort', 'ascending')
    await userEvent.click(screen.getByRole('button', { name: /Ticker/ }))
    expect(firstColumn()).toEqual(['VOD.L', 'msft', 'BP.L', 'AAPL'])
    expect(screen.getByRole('columnheader', { name: /Ticker/ })).toHaveAttribute('aria-sort', 'descending')
  })

  it('sorts numbers numerically with missing values last in both directions', async () => {
    render(<DataGrid label="t" columns={columns} rows={rows} rowKey={(r) => r.ticker} />)
    await userEvent.click(screen.getByRole('button', { name: /Price/ }))
    expect(firstColumn()).toEqual(['VOD.L', 'msft', 'BP.L', 'AAPL'])
    await userEvent.click(screen.getByRole('button', { name: /Price/ }))
    expect(firstColumn()).toEqual(['BP.L', 'msft', 'VOD.L', 'AAPL'])
    await userEvent.click(screen.getByRole('button', { name: /Change/ }))
    expect(firstColumn()).toEqual(['msft', 'VOD.L', 'AAPL', 'BP.L'])
  })

  it('does not make columns without a sort value sortable', () => {
    render(<DataGrid label="t" columns={columns} rows={rows} rowKey={(r) => r.ticker} />)
    expect(screen.queryByRole('button', { name: /Note/ })).not.toBeInTheDocument()
  })

  it('applies gain/loss classes to cells', () => {
    render(<DataGrid label="t" columns={columns} rows={rows} rowKey={(r) => r.ticker} />)
    expect(screen.getByText('-1.5')).toHaveClass('text-red-600')
    expect(screen.getByText('2')).toHaveClass('text-emerald-600')
  })

  it('shows loading, empty and error states', async () => {
    const onRetry = vi.fn()
    const { rerender } = render(<DataGrid label="t" columns={columns} rows={undefined} rowKey={(r) => r.ticker} loading />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()

    rerender(<DataGrid label="t" columns={columns} rows={[]} rowKey={(r) => r.ticker} emptyMessage="Nothing here." />)
    expect(screen.getByText('Nothing here.')).toBeInTheDocument()

    rerender(<DataGrid label="t" columns={columns} rows={rows} rowKey={(r) => r.ticker} error="Backend down." onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Backend down. Showing the last loaded data.')
    expect(firstColumn()).toHaveLength(4)
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalled()
  })

  it('renders footer rows aligned to columns', () => {
    render(
      <DataGrid label="t" columns={columns} rows={rows} rowKey={(r) => r.ticker} footerRows={[{ key: 'f', cells: { ticker: 'Total', price: '920.5' } }]} />,
    )
    const footer = screen.getByText('Total').closest('tr')!
    const cells = within(footer).getAllByRole('cell')
    expect(cells).toHaveLength(4)
    expect(cells[1]).toHaveTextContent('920.5')
  })
})

describe('compareSortValues', () => {
  it('keeps missing values last', () => {
    expect(compareSortValues(null, 1, 'asc')).toBeGreaterThan(0)
    expect(compareSortValues(null, 1, 'desc')).toBeGreaterThan(0)
    expect(compareSortValues(1, undefined, 'desc')).toBeLessThan(0)
    expect(compareSortValues(Number.NaN, null, 'asc')).toBe(0)
  })
})
