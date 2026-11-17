import type {
  BrokerAccounts,
  BrokerPositionsResponse,
  BrokerRefreshResult,
  SnapTradeCredentials,
  SnapTradeStatus,
} from '../types/api'
import { apiRequest } from './client'

const enc = encodeURIComponent
// Refreshes call SnapTrade once per account; allow more time than a normal request.
const REFRESH_TIMEOUT_MS = 120_000

export function getSnapTradeStatus(signal?: AbortSignal): Promise<SnapTradeStatus> {
  return apiRequest<SnapTradeStatus>('/brokers/snaptrade/settings', { signal })
}

/** Checks the credentials with SnapTrade, saves them, and loads every account's positions. */
export function saveSnapTradeSettings(body: SnapTradeCredentials): Promise<BrokerRefreshResult> {
  return apiRequest<BrokerRefreshResult>('/brokers/snaptrade/settings', { method: 'PUT', body, timeoutMs: REFRESH_TIMEOUT_MS })
}

export function deleteSnapTradeSettings(): Promise<void> {
  return apiRequest<void>('/brokers/snaptrade/settings', { method: 'DELETE' })
}

/** Accounts as of the last refresh (no SnapTrade call). */
export function listBrokerAccounts(signal?: AbortSignal): Promise<BrokerAccounts> {
  return apiRequest<BrokerAccounts>('/brokers/accounts', { signal })
}

/** Lists the accounts, then fetches each account's positions from SnapTrade. */
export function refreshAllBrokerAccounts(): Promise<BrokerRefreshResult> {
  return apiRequest<BrokerRefreshResult>('/brokers/refresh', { method: 'POST', timeoutMs: REFRESH_TIMEOUT_MS })
}

/** Positions as of the last refresh, valued with the latest market prices (no SnapTrade call). */
export function getBrokerPositions(accountId: string, signal?: AbortSignal): Promise<BrokerPositionsResponse> {
  return apiRequest<BrokerPositionsResponse>(`/brokers/accounts/${enc(accountId)}/positions`, { signal })
}

/** Fetches this account's positions from SnapTrade (after listing the accounts). */
export function refreshBrokerAccount(accountId: string): Promise<BrokerPositionsResponse> {
  return apiRequest<BrokerPositionsResponse>(`/brokers/accounts/${enc(accountId)}/refresh`, {
    method: 'POST',
    timeoutMs: REFRESH_TIMEOUT_MS,
  })
}
