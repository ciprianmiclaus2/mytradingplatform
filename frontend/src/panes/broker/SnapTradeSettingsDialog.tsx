import { useState, type FormEvent, type ReactNode } from 'react'
import { deleteSnapTradeSettings, getSnapTradeStatus, saveSnapTradeSettings } from '../../api/brokers'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { buttonClass, DialogButtons, FormError, inputClass, Modal, primaryButtonClass } from '../../components/Modal'
import { useDashboardActions } from '../../dashboard/actions'
import { notifyDataChanged } from '../../hooks/dataVersion'
import { errorMessage, useApiData } from '../../hooks/useApiData'
import { accountLabel } from '../../hooks/useBrokerAccounts'
import type { BrokerRefreshResult, SnapTradeCredentials } from '../../types/api'
import { readString } from '../config'
import { POSITIONS_PANE } from './constants'

const KEY_FIELDS: { key: keyof SnapTradeCredentials; label: string; secret: boolean }[] = [
  { key: 'client_id', label: 'Client ID', secret: false },
  { key: 'consumer_key', label: 'Consumer key', secret: true },
]
const USER_FIELDS: { key: keyof SnapTradeCredentials; label: string; secret: boolean }[] = [
  { key: 'user_id', label: 'User ID', secret: false },
  { key: 'user_secret', label: 'User secret', secret: true },
]

const EMPTY: SnapTradeCredentials = { client_id: '', consumer_key: '', user_id: '', user_secret: '' }

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-2 text-sm">
      <dt className="w-28 shrink-0 text-slate-500">{label}</dt>
      <dd className="min-w-0 break-all text-slate-800">{children}</dd>
    </div>
  )
}

/** Set up, replace or remove the SnapTrade connection; afterwards, offer a pane per account. */
export function SnapTradeSettingsDialog({ onClose }: { onClose: () => void }) {
  const status = useApiData('snaptrade-settings', getSnapTradeStatus)
  const dashboard = useDashboardActions()
  const [editing, setEditing] = useState(false)
  const [values, setValues] = useState<SnapTradeCredentials>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<BrokerRefreshResult | null>(null)
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const [added, setAdded] = useState(false)

  const configured = status.data?.configured ?? false

  const field = (f: { key: keyof SnapTradeCredentials; label: string; secret: boolean }, optional = false) => (
    <label key={f.key} className="mb-3 block text-sm">
      <span className="mb-1 block text-slate-600">
        {f.label}
        {optional && <span className="text-slate-400"> (optional)</span>}
      </span>
      <input
        aria-label={f.label}
        type={f.secret ? 'password' : 'text'}
        autoComplete="off"
        spellCheck={false}
        value={values[f.key]}
        onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
        className={inputClass}
      />
    </label>
  )
  const showForm = editing || (status.data !== undefined && !configured)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const missing = KEY_FIELDS.filter((f) => !values[f.key].trim()).map((f) => f.label)
    if (missing.length > 0) {
      setError(`Required: ${missing.join(', ')}.`)
      return
    }
    if (!values.user_id.trim() !== !values.user_secret.trim()) {
      setError('Enter both the User ID and the User secret, or leave both empty for a Personal API key.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const saved = await saveSnapTradeSettings(values)
      setResult(saved)
      setEditing(false)
      setValues(EMPTY)
      status.reload()
      notifyDataChanged()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async () => {
    setConfirmDisconnect(false)
    try {
      await deleteSnapTradeSettings()
      setResult(null)
      status.reload()
      notifyDataChanged()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  // Accounts without a positions pane yet. Positions panes with no (or an unknown) account are
  // given one of these accounts first, so the default pane is used rather than duplicated.
  const accountIds = new Set(result?.accounts.map((a) => a.id))
  const positionsPanes = (dashboard?.panes ?? []).filter((p) => p.type === POSITIONS_PANE)
  const assigned = new Set(positionsPanes.map((p) => readString(p.config, 'accountId')).filter((id) => id && accountIds.has(id)))
  const unassignedPanes = positionsPanes.filter((p) => !assigned.has(readString(p.config, 'accountId')))
  const newAccounts = result?.accounts.filter((a) => !assigned.has(a.id)) ?? []

  const addAccountPanes = () => {
    if (!dashboard) return
    newAccounts.forEach((account, i) => {
      const pane = unassignedPanes[i]
      if (pane) dashboard.updateConfig(pane.id, { ...pane.config, accountId: account.id })
    })
    dashboard.addPanes(POSITIONS_PANE, newAccounts.slice(unassignedPanes.length).map((a) => ({ accountId: a.id })))
    setAdded(true)
  }

  return (
    <Modal title="SnapTrade settings" onClose={onClose}>
      {!status.data ? (
        <p role={status.error ? 'alert' : 'status'} className={`text-sm ${status.error ? 'text-red-600' : 'text-slate-500'}`}>
          {status.error ?? 'Loading…'}
        </p>
      ) : result ? (
        <div className="space-y-3 text-sm">
          <p role="status" className="text-emerald-700">
            Connected. {result.accounts.length === 0 ? 'No accounts were found.' : `${result.accounts.length} account${result.accounts.length === 1 ? '' : 's'} found:`}
          </p>
          <ul className="list-disc pl-5 text-slate-700">
            {result.accounts.map((a) => (
              <li key={a.id}>{accountLabel(a)}</li>
            ))}
          </ul>
          {result.errors.length > 0 && (
            <div role="alert" className="rounded border border-amber-200 bg-amber-50 px-2 py-1.5 text-amber-800">
              Positions could not be loaded for:
              <ul className="list-disc pl-5">
                {result.errors.map((e) => (
                  <li key={e.account_id}>
                    {e.account_name}: {e.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex flex-wrap justify-end gap-2 pt-1">
            {dashboard && newAccounts.length > 0 && !added && (
              <button
                type="button"
                className={primaryButtonClass}
                onClick={addAccountPanes}
              >
                Add a pane for {newAccounts.length === 1 ? 'the account' : `each account (${newAccounts.length})`}
              </button>
            )}
            {added && <span className="self-center text-emerald-700">Panes added.</span>}
            <button type="button" className={buttonClass} onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      ) : showForm ? (
        <form onSubmit={submit} noValidate>
          <p className="mb-3 text-sm text-slate-600">
            Enter your SnapTrade API key, from the API Key page of the SnapTrade dashboard. It is checked with SnapTrade,
            then stored on this computer in the data folder (<code>config/snaptrade.json</code>, readable only by you).
            The secrets are never shown again.
          </p>
          {KEY_FIELDS.map((f) => field(f))}
          <fieldset className="mt-1 rounded border border-slate-200 px-3 pt-2">
            <legend className="px-1 text-xs text-slate-500">Commercial keys only</legend>
            <p className="mb-2 text-xs text-slate-500">
              Leave these empty for a Personal API key: SnapTrade finds your accounts from the key itself. Fill them in
              only for a Commercial key, with the user you registered through the SnapTrade API.
            </p>
            {USER_FIELDS.map((f) => field(f, true))}
          </fieldset>
          <FormError message={error} />
          <DialogButtons
            onCancel={configured ? () => setEditing(false) : onClose}
            submitLabel="Connect"
            busy={busy}
          />
        </form>
      ) : (
        <div className="space-y-3">
          <dl className="space-y-1">
            <Row label="Status">Connected</Row>
            <Row label="Key type">{status.data.personal ? 'Personal API key' : 'Commercial key with a SnapTrade user'}</Row>
            <Row label="Client ID">{status.data.client_id}</Row>
            <Row label="Consumer key">{status.data.consumer_key_hint ? `••••${status.data.consumer_key_hint}` : '••••'}</Row>
            {!status.data.personal && (
              <>
                <Row label="User ID">{status.data.user_id}</Row>
                <Row label="User secret">{status.data.user_secret_hint ? `••••${status.data.user_secret_hint}` : '••••'}</Row>
              </>
            )}
          </dl>
          <FormError message={error} />
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" className={`${buttonClass} mr-auto text-red-700`} onClick={() => setConfirmDisconnect(true)}>
              Disconnect…
            </button>
            <button type="button" className={buttonClass} onClick={() => setEditing(true)}>
              Replace credentials
            </button>
            <button type="button" className={primaryButtonClass} onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      )}
      {confirmDisconnect && (
        <ConfirmDialog
          title="Disconnect SnapTrade?"
          message="The stored credentials and all cached accounts and positions are removed from this computer. Your brokerage connections at SnapTrade are not changed."
          confirmLabel="Disconnect"
          onConfirm={disconnect}
          onCancel={() => setConfirmDisconnect(false)}
        />
      )}
    </Modal>
  )
}
