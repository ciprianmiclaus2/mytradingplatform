import { listBrokerAccounts } from '../api/brokers'
import type { BrokerAccounts, BrokerAccountView } from '../types/api'
import { useApiData, type ApiData } from './useApiData'

/** Broker accounts as of the last SnapTrade refresh (shared by all panes). */
export function useBrokerAccounts(): ApiData<BrokerAccounts> {
  return useApiData('broker-accounts', listBrokerAccounts)
}

/** "Brokerage ****1234", or just the name when there is no number. */
export function accountLabel(account: Pick<BrokerAccountView, 'name' | 'number'>): string {
  return account.number && !account.name.includes(account.number) ? `${account.name} ${account.number}` : account.name
}
