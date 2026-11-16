import { act, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { notifyDataChanged } from './dataVersion'
import { useApiData } from './useApiData'

function Consumer({ id, load }: { id: string; load: () => Promise<string> }) {
  const { data, error, loading } = useApiData('shared-key', load)
  return <p data-testid={id}>{loading ? 'loading' : (error ?? data)}</p>
}

describe('useApiData', () => {
  it('shares one request between components asking for the same key, and reloads on data changes', async () => {
    let n = 0
    const load = vi.fn(async () => `value ${++n}`)
    render(
      <>
        <Consumer id="a" load={load} />
        <Consumer id="b" load={load} />
      </>,
    )
    await waitFor(() => expect(screen.getByTestId('a')).toHaveTextContent('value 1'))
    expect(screen.getByTestId('b')).toHaveTextContent('value 1')
    expect(load).toHaveBeenCalledTimes(1)

    act(() => notifyDataChanged())
    await waitFor(() => expect(screen.getByTestId('a')).toHaveTextContent('value 2'))
    expect(screen.getByTestId('b')).toHaveTextContent('value 2')
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('keeps the last data when a reload fails', async () => {
    let fail = false
    const load = vi.fn(async () => {
      if (fail) throw new Error('down')
      return 'good'
    })
    render(<Consumer id="a" load={load} />)
    await waitFor(() => expect(screen.getByTestId('a')).toHaveTextContent('good'))
    fail = true
    act(() => notifyDataChanged())
    await waitFor(() => expect(screen.getByTestId('a')).toHaveTextContent('down'))
  })
})
