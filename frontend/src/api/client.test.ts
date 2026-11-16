import { describe, expect, it, vi } from 'vitest'
import { API_BASE_URL, ApiError, apiRequest } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('apiRequest', () => {
  it('defaults the base URL to /api', () => {
    expect(API_BASE_URL).toBe('/api')
  })

  it('returns parsed JSON on success', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(200, { ok: 1 }))
    await expect(apiRequest('/health')).resolves.toEqual({ ok: 1 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/health')
  })

  it('sends JSON bodies', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(200, {}))
    await apiRequest('/x', { method: 'POST', body: { a: 1 } })
    const init = fetchMock.mock.calls[0][1]!
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"a":1}')
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it('maps the backend error envelope to ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(422, { error: { code: 'validation_error', message: 'Bad input', details: [1] } }),
    )
    const err = await apiRequest('/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 422, code: 'validation_error', message: 'Bad input', details: [1] })
  })

  it('handles non-envelope error responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('oops', { status: 500 }))
    await expect(apiRequest('/x')).rejects.toMatchObject({ status: 500, code: 'http_error' })
  })

  it('reports network failures as backend unavailable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const err = (await apiRequest('/x').catch((e: unknown) => e)) as ApiError
    expect(err.code).toBe('backend_unavailable')
    expect(err.isBackendUnavailable).toBe(true)
  })

  it('treats proxy gateway errors as backend unavailable', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 502 }))
    const err = (await apiRequest('/x').catch((e: unknown) => e)) as ApiError
    expect(err.isBackendUnavailable).toBe(true)
  })
})
