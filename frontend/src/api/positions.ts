import type { PositionClose, PositionCreate, PositionsResponse, PositionUpdate, PositionView } from '../types/api'
import { apiRequest } from './client'

const enc = encodeURIComponent

export function listPositions(portfolioId: string, signal?: AbortSignal): Promise<PositionsResponse> {
  return apiRequest<PositionsResponse>(`/portfolios/${enc(portfolioId)}/positions?status=all`, { signal })
}

export function createPosition(portfolioId: string, body: PositionCreate): Promise<PositionView> {
  return apiRequest<PositionView>(`/portfolios/${enc(portfolioId)}/positions`, { method: 'POST', body })
}

export function updatePosition(id: string, body: PositionUpdate): Promise<PositionView> {
  return apiRequest<PositionView>(`/positions/${enc(id)}`, { method: 'PUT', body })
}

export function closePosition(id: string, body: PositionClose): Promise<PositionView> {
  return apiRequest<PositionView>(`/positions/${enc(id)}/close`, { method: 'POST', body })
}

export function deletePosition(id: string): Promise<void> {
  return apiRequest<void>(`/positions/${enc(id)}`, { method: 'DELETE' })
}
