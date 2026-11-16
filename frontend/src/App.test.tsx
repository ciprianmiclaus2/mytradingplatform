import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { STORAGE_KEY } from './dashboard/storage'

const health = {
  status: 'ok',
  version: '0.1.0',
  environment: 'development',
  data_schema_version: 1,
  market_data_provider: 'yfinance',
  server_time: '2026-11-16T12:00:00Z',
}

const healthy = () =>
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify(health), { status: 200 }))

const paneTitles = () => screen.getAllByRole('region').map((r) => r.getAttribute('aria-label'))
const saved = () => JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)

describe('App', () => {
  beforeEach(() => {
    healthy()
  })

  it('shows the backend as connected when /api/health succeeds', async () => {
    render(<App />)
    expect(await screen.findByText(/Backend connected · v0\.1\.0/)).toBeInTheDocument()
  })

  it('shows an error and recovers on retry when the backend is unavailable', async () => {
    vi.restoreAllMocks()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(new Response(JSON.stringify(health), { status: 200 }))

    render(<App />)
    expect(await screen.findByText('The backend is unavailable.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText(/Backend connected/)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('starts with the default dashboard and saves it', () => {
    render(<App />)
    expect(paneTitles()).toEqual(['Portfolio', 'Positions'])
    expect(saved().panes.map((p: { type: string }) => p.type)).toEqual(['portfolio', 'positions'])
  })

  it('adds multiple panes, including several of the same type', async () => {
    render(<App />)
    for (let i = 0; i < 2; i++) {
      await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
      await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    }
    expect(paneTitles()).toEqual(['Portfolio', 'Positions', 'Strategy', 'Strategy 2'])
    expect(saved().panes).toHaveLength(4)
    expect(saved().layouts).toHaveLength(4)
  })

  it('removes a pane only after confirmation', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Remove Positions' }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(paneTitles()).toEqual(['Portfolio', 'Positions'])

    await userEvent.click(screen.getByRole('button', { name: 'Remove Positions' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Remove' }))
    expect(paneTitles()).toEqual(['Portfolio'])
    expect(saved().panes).toHaveLength(1)
  })

  it('shows an empty state when all panes are removed', async () => {
    render(<App />)
    for (const title of ['Portfolio', 'Positions']) {
      await userEvent.click(screen.getByRole('button', { name: `Remove ${title}` }))
      await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Remove' }))
    }
    expect(screen.getByText(/The dashboard is empty/)).toBeInTheDocument()
  })

  it('minimises and restores a pane', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Minimise Portfolio' }))
    expect(screen.queryByText('Portfolio content will appear here.')).not.toBeInTheDocument()
    expect(Object.values(saved().minimised)).toEqual([10])
    await userEvent.click(screen.getByRole('button', { name: 'Restore Portfolio' }))
    expect(screen.getByText('Portfolio content will appear here.')).toBeInTheDocument()
  })

  it('restores the saved layout after a browser refresh', async () => {
    const first = render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    const ids = saved().panes.map((p: { id: string }) => p.id)
    first.unmount()

    render(<App />)
    expect(paneTitles()).toEqual(['Portfolio', 'Positions', 'Strategy'])
    expect(saved().panes.map((p: { id: string }) => p.id)).toEqual(ids)
  })

  it('resets to the default layout after confirmation', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: /Add pane/ }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Strategy/ }))
    await userEvent.click(screen.getByRole('button', { name: /Menu/ }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Reset layout/ }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Reset' }))
    expect(paneTitles()).toEqual(['Portfolio', 'Positions'])
    expect(saved().panes).toHaveLength(2)
  })

  it('recovers from a corrupted saved layout with a notice', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    window.localStorage.setItem(STORAGE_KEY, '{"version":1,"panes":"broken"')
    render(<App />)
    expect(paneTitles()).toEqual(['Portfolio', 'Positions'])
    expect(screen.getByText(/Saved layout was invalid/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByText(/Saved layout was invalid/)).not.toBeInTheDocument()
  })
})
