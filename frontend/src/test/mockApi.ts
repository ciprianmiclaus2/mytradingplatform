import { vi } from 'vitest'

export interface MockRequest {
  method: string
  path: string
  query: URLSearchParams
  body: unknown
}

type Reply = unknown | { status: number; body?: unknown }
type Handler = (req: MockRequest, match: RegExpMatchArray) => Reply | Promise<Reply>

interface Route {
  method: string
  pattern: RegExp
  handler: Handler
}

/** Build a reply with an explicit HTTP status (e.g. an API error envelope). */
export const reply = (status: number, body?: unknown) => ({ __reply: true, status, body })
export const apiError = (status: number, message: string, code = 'bad_request', details?: unknown) =>
  reply(status, { error: { code, message, details } })

/**
 * Replace fetch with a small router. Routes are `"METHOD /path"` with
 * `:param` placeholders (matched against the path without /api and query).
 * Unmatched requests fail with 404 so tests notice them.
 */
export function mockApi(routes: Record<string, Handler | Reply>) {
  const table: Route[] = Object.entries(routes).map(([spec, handler]) => {
    const [method, path] = spec.split(' ')
    const pattern = new RegExp(`^${path.replace(/:[a-z_]+/gi, '([^/]+)')}$`)
    return { method, pattern, handler: typeof handler === 'function' ? (handler as Handler) : () => handler }
  })
  const calls: MockRequest[] = []

  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost')
    const path = url.pathname.replace(/^\/api/, '')
    const method = (init?.method ?? 'GET').toUpperCase()
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
    const req: MockRequest = { method, path: decodeURIComponent(path), query: url.searchParams, body }
    calls.push(req)
    for (const route of table) {
      const match = req.path.match(route.pattern)
      if (route.method === method && match) {
        const result = (await route.handler(req, match)) as { __reply?: boolean; status: number; body?: unknown }
        if (result && typeof result === 'object' && result.__reply) {
          return new Response(result.body === undefined ? null : JSON.stringify(result.body), { status: result.status })
        }
        if (result === undefined) return new Response(null, { status: 204 })
        return new Response(JSON.stringify(result), { status: 200 })
      }
    }
    return new Response(JSON.stringify({ error: { code: 'not_found', message: `No mock for ${method} ${path}` } }), { status: 404 })
  })

  return {
    fetchMock,
    calls,
    /** Requests matching a method and path (exact or regex). */
    find: (method: string, path: string | RegExp) =>
      calls.filter((c) => c.method === method && (typeof path === 'string' ? c.path === path : path.test(c.path))),
  }
}
