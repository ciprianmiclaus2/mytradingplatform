import type { Portfolio, PortfolioQuotes, PortfolioType } from '../types/api'
import { apiRequest } from './client'

const enc = encodeURIComponent

export function listPortfolios(signal?: AbortSignal): Promise<Portfolio[]> {
  return apiRequest<Portfolio[]>('/portfolios', { signal })
}

export function getPortfolio(id: string, signal?: AbortSignal): Promise<Portfolio> {
  return apiRequest<Portfolio>(`/portfolios/${enc(id)}`, { signal })
}

export function createPortfolio(body: { name: string; description?: string; type: PortfolioType }): Promise<Portfolio> {
  return apiRequest<Portfolio>('/portfolios', { method: 'POST', body })
}

export function updatePortfolio(id: string, body: { name?: string; description?: string }): Promise<Portfolio> {
  return apiRequest<Portfolio>(`/portfolios/${enc(id)}`, { method: 'PUT', body })
}

export function deletePortfolio(id: string): Promise<void> {
  return apiRequest<void>(`/portfolios/${enc(id)}`, { method: 'DELETE' })
}

export function getQuotes(id: string, signal?: AbortSignal): Promise<PortfolioQuotes> {
  return apiRequest<PortfolioQuotes>(`/portfolios/${enc(id)}/quotes`, { signal })
}

export function addTicker(id: string, ticker: string): Promise<Portfolio> {
  return apiRequest<Portfolio>(`/portfolios/${enc(id)}/tickers`, { method: 'POST', body: { ticker } })
}

export function removeTicker(id: string, ticker: string): Promise<Portfolio> {
  return apiRequest<Portfolio>(`/portfolios/${enc(id)}/tickers/${enc(ticker)}`, { method: 'DELETE' })
}

export function setFavourite(id: string, ticker: string, favourite: boolean): Promise<Portfolio> {
  return apiRequest<Portfolio>(`/portfolios/${enc(id)}/favourites/${enc(ticker)}`, {
    method: favourite ? 'PUT' : 'DELETE',
  })
}
