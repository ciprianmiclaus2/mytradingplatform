import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

const health = {
  status: 'ok',
  version: '0.1.0',
  environment: 'development',
  data_schema_version: 1,
  market_data_provider: 'yfinance',
  server_time: '2026-11-16T12:00:00Z',
}

describe('App', () => {
  it('shows the backend as connected when /api/health succeeds', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(health), { status: 200 }))
    render(<App />)
    expect(await screen.findByText(/Backend connected · v0\.1\.0/)).toBeInTheDocument()
  })

  it('shows an error and recovers on retry when the backend is unavailable', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response(JSON.stringify(health), { status: 200 }))

    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('The backend is unavailable.')

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText(/Backend connected/)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
