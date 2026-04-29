import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppStore } from '../store'
import { Modal, ConfirmDialog } from '../components/shared/Modal'
import { Field, Input, Select, FormGrid, FormSection, Divider } from '../components/shared/Form'
import clsx from 'clsx'
import type { Account } from '../types'
import { getAccounts } from '../api/portfolio'

// ─── Types ────────────────────────────────────────────────────────────────────

interface ConnectorRead {
  id: string
  portfolio_id: string
  name: string
  type: string
  config_keys: string[]
  config_display: Record<string, unknown> | null
  asset_filter: string[] | null
  auto_create_assets: boolean
  schedule: string
  is_active: boolean
  last_run_at: string | null
  last_error: string | null
  last_run_status: string | null
  last_run_started_at: string | null
  last_run_summary: {
    transactions_created: number | null
    assets_created: number | null
    fx_rates_updated: number | null
    prices_updated: number | null
    duration_ms: number | null
  } | null
  created_at: string
}

// Sensitive field keys — left blank on edit = keep existing value
const SENSITIVE_KEYS = new Set(['api_key', 'api_secret', 'password', 'token', 'secret'])

interface ScraperCard {
  id: string
  name: string
  card6?: string
  enabled: boolean
}

interface ConnectorRun {
  id: string
  connector_id: string
  status: string
  triggered_by: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  records_fetched: number | null
  transactions_created: number | null
  transactions_skipped: number | null
  assets_created: number | null
  fx_rates_updated: number | null
  prices_updated: number | null
  error_message: string | null
  checkpoint: { github_run_url?: string; github_run_id?: string } | null
  created_at: string
}

interface ConnectorType {
  type: string
  display_name: string
  description: string
  config_fields: { key: string; label: string; type: string; default: string; hint: string }[]
}

// ─── API functions ────────────────────────────────────────────────────────────

import apiClient from '../api/client'
import { DEFAULT_PORTFOLIO_ID, uploadBankStatement } from '../api/portfolio'

async function getConnectors(): Promise<ConnectorRead[]> {
  const { data } = await apiClient.get('/api/v1/connectors/', {
    params: { portfolio_id: DEFAULT_PORTFOLIO_ID },
  })
  return Array.isArray(data) ? data : []
}

async function getConnectorTypes(): Promise<ConnectorType[]> {
  const { data } = await apiClient.get('/api/v1/connector-types')
  return Array.isArray(data) ? data : []
}

async function createConnector(payload: Record<string, unknown>): Promise<ConnectorRead> {
  const { data } = await apiClient.post('/api/v1/connectors/', payload, {
    params: { portfolio_id: DEFAULT_PORTFOLIO_ID },
  })
  return data
}

async function updateConnector(id: string, payload: Record<string, unknown>): Promise<ConnectorRead> {
  const { data } = await apiClient.patch(`/api/v1/connectors/${id}`, payload)
  return data
}

async function deleteConnector(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/connectors/${id}`)
}

async function triggerRun(id: string): Promise<void> {
  await apiClient.post(`/api/v1/connectors/${id}/run`)
}

async function getConnectorRuns(id: string, page = 1): Promise<{ items: ConnectorRun[]; total: number }> {
  const { data } = await apiClient.get(`/api/v1/connectors/${id}/runs`, {
    params: { page, limit: 20 },
  })
  return data
}

async function pushSecrets(id: string, secrets: Record<string, string>): Promise<{ saved: string[]; failed: string[] }> {
  const { data } = await apiClient.post(`/api/v1/connectors/${id}/secrets`, secrets)
  return data
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Legacy types (backward compat) + new per-company types
const SCRAPER_TYPES = new Set(['scraper', 'isracard', 'isracard_scraper', 'cal_scraper', 'max_scraper', 'leumi_card_scraper', 'amex_scraper'])
function isScraperType(type: string) { return SCRAPER_TYPES.has(type) }

interface CompanyInfo { name: string; prefix: string; hasCard6: boolean; hasNationalId: boolean }
const COMPANY_INFO: Record<string, CompanyInfo> = {
  isracard:   { name: 'Isracard',    prefix: 'ISRACARD',   hasCard6: true,  hasNationalId: false },
  cal:        { name: 'Cal',         prefix: 'CAL',        hasCard6: false, hasNationalId: false },
  max:        { name: 'Max',         prefix: 'MAX',        hasCard6: false, hasNationalId: false },
  leumi_card: { name: 'Leumi Card',  prefix: 'LEUMI_CARD', hasCard6: false, hasNationalId: true  },
  amex:       { name: 'Amex Israel', prefix: 'AMEX',       hasCard6: false, hasNationalId: false },
}

function getCompany(c: ConnectorRead): string {
  return (c.config_display?.company as string) ?? c.type.replace('_scraper', '')
}

function buildSecretsPayload(
  company: string,
  creds: { username: string; password: string; national_id: string },
  cards: ScraperCard[],
): Record<string, string> {
  const info = COMPANY_INFO[company]
  if (!info) return {}
  const p = info.prefix
  const out: Record<string, string> = {}
  if (creds.username)   out[`${p}_USERNAME`] = creds.username
  if (creds.password)   out[`${p}_PASSWORD`] = creds.password
  if (creds.national_id && info.hasNationalId) out[`${p}_NATIONAL_ID`] = creds.national_id
  if (info.hasCard6) {
    const card6s = cards.filter(c => c.card6).map(c => c.card6!)
    card6s.forEach((c6, i) => {
      out[i === 0 ? `${p}_CARD6` : `${p}_CARD6_${i + 1}`] = c6
    })
  }
  return out
}

function formatElapsed(startedAt: string | null): string {
  if (!startedAt) return ''
  const secs = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  return `${mins}m ${secs % 60}s`
}

function formatDuration(ms: number | null) {
  if (!ms) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatRelative(dt: string | null) {
  if (!dt) return '—'
  const diff = Date.now() - new Date(dt).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ConnectorsPage() {
  const qc = useQueryClient()

  const { data: connectors = [], isLoading } = useQuery({
    queryKey: ['connectors'],
    queryFn: getConnectors,
    // Poll every 5 s while any connector is running so the UI updates automatically
    refetchInterval: (query) => {
      const data = query.state.data as ConnectorRead[] | undefined
      const anyRunning = data?.some(
        c => c.last_run_status === 'running' || c.last_run_status === 'pending'
      )
      return anyRunning ? 5000 : false
    },
  })

  const { data: connectorTypes = [] } = useQuery({
    queryKey: ['connector-types'],
    queryFn: getConnectorTypes,
  })

  const { data: accounts = [] } = useQuery<Account[]>({
    queryKey: ['accounts'],
    queryFn: getAccounts,
  })

  const createMut = useMutation({
    mutationFn: createConnector,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['connectors'] }); closeModal() },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      updateConnector(id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['connectors'] }); closeModal() },
  })

  const deleteMut = useMutation({
    mutationFn: deleteConnector,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['connectors'] }); setDeleteTarget(null) },
  })

  const runMut = useMutation({
    mutationFn: triggerRun,
    onSuccess: () => {
      // Refetch immediately so last_run_status = 'running' shows up
      qc.invalidateQueries({ queryKey: ['connectors'] })
    },
  })

  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<ConnectorRead | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ConnectorRead | null>(null)
  const [historyTarget, setHistoryTarget] = useState<ConnectorRead | null>(null)
  const [selectedType, setSelectedType] = useState('')
  const [form, setForm] = useState<Record<string, string>>({})
  const [configForm, setConfigForm] = useState<Record<string, string>>({})
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set())

  // Scraper-specific state
  const [scraperCards, setScraperCards] = useState<ScraperCard[]>([])
  const [scraperCreds, setScraperCreds] = useState({ username: '', password: '', national_id: '' })
  const [newCard, setNewCard] = useState({ name: '', card6: '' })
  const [showAddCard, setShowAddCard] = useState(false)
  const [secretsPending, setSecretsPending] = useState(false)

  // On mount: hit the status endpoint for any connector that appears running so
  // the backend can auto-fail stuck runs and the UI gets fresh data.
  const checkedRef = useRef(false)
  useEffect(() => {
    if (checkedRef.current || connectors.length === 0) return
    const running = connectors.filter(
      c => c.last_run_status === 'running' || c.last_run_status === 'pending'
    )
    if (running.length === 0) return
    checkedRef.current = true
    running.forEach(c =>
      apiClient.get(`/api/v1/connectors/${c.id}/status/`).catch(() => {})
    )
    qc.invalidateQueries({ queryKey: ['connectors'] })
  }, [connectors.length])

  const selectedTypeDef = connectorTypes.find(t => t.type === selectedType)

  // Accounts filtered for crypto/brokerage connectors
  const cryptoAccounts = accounts.filter(
    a => a.category === 'crypto' || a.account_type === 'brokerage'
  )
  const otherAccounts = accounts.filter(
    a => a.category !== 'crypto' && a.account_type !== 'brokerage'
  )

  function openAdd() {
    setEditTarget(null)
    setSelectedType(connectorTypes[0]?.type ?? '')
    setForm({ name: '', schedule: 'daily', is_active: 'true', asset_filter: '' })
    setConfigForm({})
    setModalOpen(true)
  }

  function openEdit(c: ConnectorRead) {
    setEditTarget(c)
    setSelectedType(c.type)
    setForm({
      name: c.name,
      schedule: c.schedule,
      is_active: String(c.is_active),
      asset_filter: c.asset_filter?.join(',') ?? '',
    })
    // Pre-populate non-sensitive fields from config_display; leave sensitive blank
    const prefilled: Record<string, string> = {}
    if (c.config_display) {
      for (const [k, v] of Object.entries(c.config_display)) {
        if (k === 'cards') continue  // handled by scraper state
        prefilled[k] = SENSITIVE_KEYS.has(k) ? '' : String(v ?? '')
      }
    }
    setConfigForm(prefilled)

    // Scraper-specific state
    if (isScraperType(c.type)) {
      const display = c.config_display ?? {}
      setScraperCards(Array.isArray(display.cards) ? (display.cards as ScraperCard[]) : [])
      setScraperCreds({
        username: (display.username as string) ?? '',
        password: '',
        national_id: (display.national_id as string) ?? '',
      })
      setShowAddCard(false)
      setNewCard({ name: '', card6: '' })
    }

    setModalOpen(true)
  }

  function closeModal() {
    setModalOpen(false)
    setEditTarget(null)
    setShowAddCard(false)
    setNewCard({ name: '', card6: '' })
  }

  function handleSubmit() {
    if (isScraperType(selectedType)) {
      handleScraperSubmit()
      return
    }
    // Generic connector — existing logic
    const configPayload: Record<string, string> = {}
    for (const [k, v] of Object.entries(configForm)) {
      if (editTarget && SENSITIVE_KEYS.has(k) && !v) continue  // keep existing
      configPayload[k] = v
    }
    const payload: Record<string, unknown> = {
      name: form.name,
      type: selectedType,
      schedule: form.schedule,
      is_active: form.is_active === 'true',
      auto_create_assets: true,
      asset_filter: form.asset_filter ? form.asset_filter.split(',').map(s => s.trim()) : null,
      config: configPayload,
    }
    if (editTarget) updateMut.mutate({ id: editTarget.id, payload })
    else createMut.mutate(payload)
  }

  async function handleScraperSubmit() {
    if (!editTarget) return
    const company = getCompany(editTarget)
    const configPayload: Record<string, unknown> = {
      username: scraperCreds.username,
      cards: scraperCards,
    }
    if (scraperCreds.password)   configPayload.password    = scraperCreds.password
    if (scraperCreds.national_id) configPayload.national_id = scraperCreds.national_id

    const patchPayload: Record<string, unknown> = {
      config: configPayload,
      is_active: scraperCards.length > 0,
    }

    updateMut.mutate({ id: editTarget.id, payload: patchPayload }, {
      onSuccess: async () => {
        // Push credentials to GitHub Secrets if any were provided
        const secrets = buildSecretsPayload(company, scraperCreds, scraperCards)
        if (Object.keys(secrets).length > 0) {
          setSecretsPending(true)
          try { await pushSecrets(editTarget.id, secrets) }
          catch (e) { console.error('Failed to push secrets:', e) }
          finally { setSecretsPending(false) }
        }
        qc.invalidateQueries({ queryKey: ['connectors'] })
        closeModal()
      },
    })
  }

  function handleRun(c: ConnectorRead) {
    setRunningIds(prev => new Set(prev).add(c.id))
    runMut.mutate(c.id, {
      // Keep runningIds until the DB echoes back status='running' in the next poll
      onSettled: () => {
        // Remove from local set after a short delay — DB status takes over from here
        setTimeout(
          () => setRunningIds(prev => { const s = new Set(prev); s.delete(c.id); return s }),
          3000,
        )
      },
    })
  }

  return (
    <div className="p-6 pb-20 md:pb-6">

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-[16px] font-semibold text-gray-900">Connectors</h2>
          <p className="text-[12px] text-gray-400 mt-0.5">
            {connectors.length} connector{connectors.length !== 1 ? 's' : ''} configured
          </p>
        </div>
        <button onClick={openAdd}
          className="flex items-center gap-2 px-4 py-2 bg-[#0d9488] hover:bg-teal-700 text-white text-[13px] font-medium rounded-lg transition-colors">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round"><path d="M6 1v10M1 6h10"/></svg>
          Add connector
        </button>
      </div>

      {/* Connector cards */}
      {isLoading ? <LoadingCards /> : connectors.length === 0 ? <EmptyState onAdd={openAdd} /> : (
        <div className="space-y-3">
          {connectors.map((c) => (
            <ConnectorCard
              key={c.id}
              connector={c}
              isRunning={
                runningIds.has(c.id) ||
                c.last_run_status === 'running' ||
                c.last_run_status === 'pending'
              }
              onRun={() => handleRun(c)}
              onEdit={() => openEdit(c)}
              onDelete={() => setDeleteTarget(c)}
              onHistory={() => setHistoryTarget(c)}
            />
          ))}
        </div>
      )}

      {/* Upload bank statement */}
      <UploadSection connectors={connectors} onUploaded={() => qc.invalidateQueries({ queryKey: ['connectors'] })} />

      {/* Add/Edit Modal */}
      <Modal open={modalOpen} onClose={closeModal}
        title={editTarget ? `Edit — ${editTarget.name}` : 'Add connector'}
        width="max-w-xl">
        <div className="space-y-5">
          <FormSection title="Connector">
            <FormGrid>
              <Field label="Name" required>
                <Input value={form.name ?? ''}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. My Kraken Account" />
              </Field>
              <Field label="Type">
                <Select value={selectedType}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
                    setSelectedType(e.target.value)
                    setConfigForm({})
                  }}
                  disabled={!!editTarget}>
                  {connectorTypes.map(t => (
                    <option key={t.type} value={t.type}>{t.display_name}</option>
                  ))}
                </Select>
              </Field>
            </FormGrid>
            {selectedTypeDef?.description && (
              <p className="text-[12px] text-gray-400">{selectedTypeDef.description}</p>
            )}
            <FormGrid>
              <Field label="Schedule">
                <Select value={form.schedule ?? 'daily'}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, schedule: e.target.value })}>
                  <option value="daily">Daily</option>
                  <option value="hourly">Hourly</option>
                  <option value="manual">Manual only</option>
                </Select>
              </Field>
              <Field label="Status">
                <Select value={form.is_active ?? 'true'}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, is_active: e.target.value })}>
                  <option value="true">Active</option>
                  <option value="false">Disabled</option>
                </Select>
              </Field>
            </FormGrid>
            <Field label="Asset filter" hint="Comma-separated symbols. Leave empty for all assets.">
              <Input value={form.asset_filter ?? ''}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, asset_filter: e.target.value })}
                placeholder="e.g. BTC,ETH or leave empty" />
            </Field>
          </FormSection>

          {/* Scraper-specific config form */}
          {isScraperType(selectedType) ? (
            <>
              <Divider />
              <FormSection title="Company credentials">
                <p className="text-[12px] text-gray-400 -mt-1 mb-2">
                  Saved encrypted in the database and pushed to GitHub Secrets for the Actions runner.
                </p>
                <Field label="Username / ID">
                  <Input value={scraperCreds.username}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setScraperCreds({ ...scraperCreds, username: e.target.value })}
                    placeholder="e.g. 0512345678" />
                </Field>
                <Field label="Password" hint={editTarget ? 'Leave blank to keep existing password' : undefined}>
                  <Input type="password" value={scraperCreds.password}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setScraperCreds({ ...scraperCreds, password: e.target.value })}
                    placeholder={editTarget ? '••••••••' : 'Password'} />
                </Field>
                {editTarget && COMPANY_INFO[getCompany(editTarget)]?.hasNationalId && (
                  <Field label="National ID (Teudat Zehut)">
                    <Input value={scraperCreds.national_id}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                        setScraperCreds({ ...scraperCreds, national_id: e.target.value })}
                      placeholder="9-digit ID" />
                  </Field>
                )}
              </FormSection>

              <Divider />
              <FormSection title="Cards">
                {scraperCards.length === 0 && (
                  <p className="text-[12px] text-gray-400">No cards configured yet.</p>
                )}
                {scraperCards.map((card, i) => (
                  <div key={card.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                    <div className="text-[13px] text-gray-800">
                      {card.name}
                      {card.card6 && <span className="ml-2 text-[12px] text-gray-400">••• {card.card6.slice(-4)}</span>}
                    </div>
                    <button onClick={() => setScraperCards(scraperCards.filter((_, j) => j !== i))}
                      className="text-[11px] text-rose-400 hover:text-rose-600 px-2 py-1">
                      Remove
                    </button>
                  </div>
                ))}

                {showAddCard ? (
                  <div className="mt-3 p-3 bg-gray-50 rounded-lg space-y-3">
                    <Field label="Card nickname">
                      <Input value={newCard.name}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewCard({ ...newCard, name: e.target.value })}
                        placeholder="e.g. My Isracard" />
                    </Field>
                    {editTarget && COMPANY_INFO[getCompany(editTarget)]?.hasCard6 && (
                      <Field label="Last 6 digits" hint="Printed on the front of the card">
                        <Input value={newCard.card6}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewCard({ ...newCard, card6: e.target.value })}
                          placeholder="e.g. 105177" maxLength={6} />
                      </Field>
                    )}
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          if (!newCard.name) return
                          setScraperCards([...scraperCards, {
                            id: `card_${Date.now()}`,
                            name: newCard.name,
                            card6: newCard.card6 || undefined,
                            enabled: true,
                          }])
                          setNewCard({ name: '', card6: '' })
                          setShowAddCard(false)
                        }}
                        className="px-3 py-1.5 text-[12px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700">
                        Add card
                      </button>
                      <button onClick={() => setShowAddCard(false)}
                        className="px-3 py-1.5 text-[12px] text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50">
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button onClick={() => setShowAddCard(true)}
                    className="mt-2 flex items-center gap-1.5 text-[12px] text-teal-600 hover:text-teal-700 font-medium">
                    <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M5.5 1v9M1 5.5h9"/></svg>
                    Add another card
                  </button>
                )}
              </FormSection>
            </>
          ) : (
            /* Generic config fields */
            selectedTypeDef && selectedTypeDef.config_fields.length > 0 && (
              <>
                <Divider />
                <FormSection title="Configuration">
                  {selectedTypeDef.config_fields.map(field => {
                    if (field.key === 'account_id') {
                      return (
                        <Field key={field.key} label={field.label}
                          hint="Select which account these trades belong to. Add accounts in the Accounts page first.">
                          <select
                            value={configForm[field.key] ?? ''}
                            onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                              setConfigForm({ ...configForm, [field.key]: e.target.value })}
                            className="w-full px-3 py-2 text-[13px] border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-teal-400">
                            <option value="">— Select account —</option>
                            {cryptoAccounts.length > 0 && (
                              <optgroup label="Crypto / Brokerage">
                                {cryptoAccounts.map(a => (
                                  <option key={a.id} value={a.id}>{a.name}</option>
                                ))}
                              </optgroup>
                            )}
                            {otherAccounts.length > 0 && (
                              <optgroup label="Other">
                                {otherAccounts.map(a => (
                                  <option key={a.id} value={a.id}>{a.name}</option>
                                ))}
                              </optgroup>
                            )}
                          </select>
                        </Field>
                      )
                    }

                    const isSensitive = SENSITIVE_KEYS.has(field.key)
                    const maskedPlaceholder = editTarget && isSensitive && editTarget.config_display?.[field.key]
                      ? String(editTarget.config_display[field.key])
                      : field.default
                    const fieldHint = editTarget && isSensitive ? 'Leave blank to keep existing value' : field.hint

                    return (
                      <Field key={field.key} label={field.label} hint={fieldHint}>
                        <Input
                          type={field.key.includes('secret') || field.key.includes('password') ? 'password' : 'text'}
                          value={configForm[field.key] ?? ''}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                            setConfigForm({ ...configForm, [field.key]: e.target.value })}
                          placeholder={maskedPlaceholder} />
                      </Field>
                    )
                  })}
                </FormSection>
              </>
            )
          )}

          <Divider />
          <div className="flex justify-end gap-2">
            <button onClick={closeModal}
              className="px-4 py-2 text-[13px] font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
              Cancel
            </button>
            <button onClick={handleSubmit}
              disabled={createMut.isPending || updateMut.isPending || secretsPending}
              className="px-4 py-2 text-[13px] font-medium bg-[#0d9488] hover:bg-teal-700 text-white rounded-lg disabled:opacity-60">
              {secretsPending ? 'Pushing secrets…' : createMut.isPending || updateMut.isPending ? 'Saving…' : editTarget ? 'Save changes' : 'Add connector'}
            </button>
          </div>
        </div>
      </Modal>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title={`Delete "${deleteTarget?.name}"?`}
        message="This will also delete all run history for this connector."
        confirmLabel="Delete" danger
        onConfirm={() => { if (deleteTarget) deleteMut.mutate(deleteTarget.id) }}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* Run history drawer */}
      {historyTarget && (
        <RunHistoryDrawer
          connector={historyTarget}
          onClose={() => setHistoryTarget(null)}
        />
      )}
    </div>
  )
}

// ─── Connector Card ───────────────────────────────────────────────────────────

function ConnectorCard({
  connector: c, isRunning, onRun, onEdit, onDelete, onHistory
}: {
  connector: ConnectorRead
  isRunning: boolean
  onRun: () => void
  onEdit: () => void
  onDelete: () => void
  onHistory: () => void
}) {
  const status = c.last_run_status
  const summary = c.last_run_summary

  const cards = isScraperType(c.type) && Array.isArray(c.config_display?.cards)
    ? (c.config_display!.cards as ScraperCard[])
    : []

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          {/* Status dot */}
          <div className={clsx('w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0',
            !c.is_active ? 'bg-gray-300' :
            status === 'success' ? 'bg-emerald-500' :
            status === 'failed' ? 'bg-rose-500' :
            status === 'running' ? 'bg-amber-400 animate-pulse' :
            'bg-gray-300')} />

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[14px] font-semibold text-gray-900">{c.name}</span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 font-mono">
                {c.type}
              </span>
              {!c.is_active && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-400">
                  disabled
                </span>
              )}
            </div>

            <div className="mt-1 flex items-center gap-3 flex-wrap text-[12px] text-gray-400">
              <span>{c.schedule}</span>
              {c.last_run_at && (
                <>
                  <span>·</span>
                  <span>Last run {formatRelative(c.last_run_at)}</span>
                </>
              )}
              {isRunning && isScraperType(c.type) && (
                <span className="text-amber-600">
                  Scraping credit cards…
                  {c.last_run_started_at && ` (${formatElapsed(c.last_run_started_at)} elapsed)`}
                </span>
              )}
              {isRunning && !isScraperType(c.type) && (
                <span className="text-amber-600">
                  Running…
                  {c.last_run_started_at && ` (${formatElapsed(c.last_run_started_at)})`}
                </span>
              )}
              {status === 'success' && summary && (
                <>
                  <span>·</span>
                  <span className="text-emerald-600">
                    {[
                      summary.transactions_created ? `${summary.transactions_created} txns` : null,
                      summary.assets_created ? `${summary.assets_created} assets` : null,
                      summary.fx_rates_updated ? `${summary.fx_rates_updated} FX rates` : null,
                      summary.prices_updated ? `${summary.prices_updated} prices` : null,
                    ].filter(Boolean).join(' · ') || '✓ no changes'}
                  </span>
                  {summary.duration_ms && (
                    <>
                      <span>·</span>
                      <span>{formatDuration(summary.duration_ms)}</span>
                    </>
                  )}
                </>
              )}
              {status === 'failed' && c.last_error && (
                <>
                  <span>·</span>
                  <span className="text-rose-500 truncate max-w-[300px]">{c.last_error}</span>
                </>
              )}
            </div>

            {/* Scraper: card list */}
            {isScraperType(c.type) && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {cards.length === 0 ? (
                  <span className="text-[11px] text-gray-400 italic">No cards configured — click edit to set up</span>
                ) : cards.map(card => (
                  <span key={card.id} className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                    {card.name}
                    {card.card6 && <span className="text-gray-400">••• {card.card6.slice(-4)}</span>}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <button onClick={onHistory} title="Run history"
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-300 hover:text-gray-600 hover:bg-gray-50 transition-colors">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><circle cx="7" cy="7" r="5"/><path d="M7 4v3l2 1"/></svg>
          </button>
          <button onClick={onEdit} title="Edit"
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-300 hover:text-teal-600 hover:bg-teal-50 transition-colors">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 2l2 2-6 6H3V8l6-6z"/></svg>
          </button>
          <button onClick={onDelete} title="Delete"
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-300 hover:text-rose-500 hover:bg-rose-50 transition-colors">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M2 4h9M5 4V3h3v1M4 4l.5 6h4l.5-6"/></svg>
          </button>
          <button onClick={onRun} disabled={isRunning || !c.is_active} title="Run now"
            className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium rounded-lg transition-colors ml-1',
              c.is_active
                ? 'bg-teal-600 hover:bg-teal-700 text-white disabled:opacity-60'
                : 'bg-gray-100 text-gray-400 cursor-not-allowed'
            )}>
            {isRunning ? (
              <svg className="animate-spin" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2"><path d="M6 1v2M6 9v2M1 6h2M9 6h2" strokeLinecap="round"/></svg>
            ) : (
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 2l7 4-7 4V2z" fill="currentColor"/></svg>
            )}
            {isRunning ? 'Running…' : 'Run'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Run History Drawer ───────────────────────────────────────────────────────

function RunHistoryDrawer({ connector, onClose }: { connector: ConnectorRead; onClose: () => void }) {
  const { data } = useQuery({
    queryKey: ['runs', connector.id],
    queryFn: () => getConnectorRuns(connector.id),
    refetchInterval: 5000, // poll while runs might be in progress
  })
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const runs = data?.items ?? []

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <div className="relative bg-white w-full max-w-lg shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <h3 className="text-[14px] font-semibold text-gray-900">Run History</h3>
            <p className="text-[12px] text-gray-400 mt-0.5">{connector.name}</p>
          </div>
          <button onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l10 10M12 2L2 12"/></svg>
          </button>
        </div>

        {/* Runs list */}
        <div className="flex-1 overflow-y-auto">
          {runs.length === 0 ? (
            <div className="p-8 text-center text-[13px] text-gray-400">No runs yet</div>
          ) : runs.map((run) => (
            <div key={run.id} className="border-b border-gray-50 last:border-0">
              <button
                onClick={() => setExpandedId(expandedId === run.id ? null : run.id)}
                className="w-full flex items-start gap-3 px-5 py-3.5 hover:bg-gray-50 text-left transition-colors">
                {/* Status icon */}
                <div className="mt-0.5 flex-shrink-0">
                  {run.status === 'success' && (
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#10b981" strokeWidth="2" strokeLinecap="round"><path d="M2 7l3.5 3.5L12 3"/></svg>
                  )}
                  {run.status === 'failed' && (
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round"><path d="M2 2l10 10M12 2L2 12"/></svg>
                  )}
                  {(run.status === 'running' || run.status === 'pending') && (
                    <svg className="animate-spin" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#f59e0b" strokeWidth="2"><path d="M7 1v2M7 11v2M1 7h2M11 7h2" strokeLinecap="round"/></svg>
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className={clsx('text-[13px] font-medium',
                      run.status === 'success' ? 'text-gray-900' :
                      run.status === 'failed' ? 'text-rose-600' : 'text-amber-600')}>
                      {run.status.charAt(0).toUpperCase() + run.status.slice(1)}
                    </span>
                    <span className="text-[11px] text-gray-400">
                      {formatRelative(run.started_at)}
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-400 mt-0.5 flex gap-3 flex-wrap">
                    {run.duration_ms && <span>{formatDuration(run.duration_ms)}</span>}
                    {run.transactions_created != null && run.transactions_created > 0 && (
                      <span className="text-emerald-600">+{run.transactions_created} txns</span>
                    )}
                    {run.assets_created != null && run.assets_created > 0 && (
                      <span className="text-blue-600">+{run.assets_created} assets</span>
                    )}
                    {run.fx_rates_updated != null && run.fx_rates_updated > 0 && (
                      <span>{run.fx_rates_updated} FX rates</span>
                    )}
                    {run.prices_updated != null && run.prices_updated > 0 && (
                      <span>{run.prices_updated} prices</span>
                    )}
                    {run.transactions_skipped != null && run.transactions_skipped > 0 && (
                      <span className="text-gray-400">{run.transactions_skipped} skipped</span>
                    )}
                    <span className="text-gray-300">{run.triggered_by}</span>
                  </div>
                  {run.status === 'failed' && run.error_message && (
                    <p className="text-[11px] text-rose-500 mt-1 truncate">{run.error_message}</p>
                  )}
                  {run.checkpoint?.github_run_url && (
                    <a
                      href={run.checkpoint.github_run_url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={e => e.stopPropagation()}
                      className="text-[11px] text-teal-600 hover:underline mt-0.5 block">
                      View on GitHub →
                    </a>
                  )}
                </div>
              </button>

              {/* Expanded error details */}
              {expandedId === run.id && run.error_message && (
                <div className="mx-5 mb-3 p-3 bg-rose-50 rounded-lg space-y-2">
                  <p className="text-[12px] font-medium text-rose-700">Error</p>
                  <pre className="text-[11px] text-rose-600 whitespace-pre-wrap font-sans leading-relaxed">
                    {run.error_message}
                  </pre>
                  {run.checkpoint?.github_run_url && (
                    <a
                      href={run.checkpoint.github_run_url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={e => e.stopPropagation()}
                      className="inline-flex items-center gap-1 text-[11px] text-teal-600 hover:underline font-medium">
                      View full logs on GitHub →
                    </a>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Upload Section ───────────────────────────────────────────────────────────

const UPLOAD_TYPES = ['mizrachi_bank', 'fibi_bank']

function UploadSection({ connectors, onUploaded }: { connectors: ConnectorRead[]; onUploaded: () => void }) {
  const uploadable = connectors.filter(c => UPLOAD_TYPES.includes(c.type) && c.is_active)
  const [selectedId, setSelectedId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<{ created: number; skipped: number; total: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useMemo(() => ({ current: null as HTMLInputElement | null }), [])

  const selected = uploadable.find(c => c.id === selectedId) ?? uploadable[0] ?? null

  async function handleUpload() {
    if (!file || !selected) return
    setUploading(true)
    setResult(null)
    setError(null)
    try {
      const res = await uploadBankStatement(selected.type, selected.portfolio_id, file)
      setResult(res)
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
      onUploaded()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? String(e)
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    } finally {
      setUploading(false)
    }
  }

  if (uploadable.length === 0) return null

  return (
    <div className="mt-6 bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <h3 className="text-[14px] font-semibold text-gray-900 mb-1">Upload bank statement</h3>
      <p className="text-[12px] text-gray-400 mb-4">Manually import a PDF or XLSX export from your bank</p>

      <div className="flex flex-wrap items-end gap-3">
        {/* Connector picker */}
        <div className="flex flex-col gap-1">
          <label className="text-[11px] text-gray-500 font-medium">Bank</label>
          <select
            value={selectedId || selected?.id || ''}
            onChange={e => setSelectedId(e.target.value)}
            className="px-3 py-2 text-[13px] border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-teal-400"
          >
            {uploadable.map(c => (
              <option key={c.id} value={c.id}>{c.name} ({c.type})</option>
            ))}
          </select>
        </div>

        {/* File picker */}
        <div className="flex flex-col gap-1">
          <label className="text-[11px] text-gray-500 font-medium">File</label>
          <input
            type="file"
            accept=".pdf,.xlsx"
            ref={el => { fileRef.current = el }}
            onChange={e => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(null) }}
            className="text-[13px] text-gray-700 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-gray-200 file:text-[12px] file:bg-white file:text-gray-600 hover:file:bg-gray-50 cursor-pointer"
          />
        </div>

        {/* Upload button */}
        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="flex items-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white text-[13px] font-medium rounded-lg disabled:opacity-50 transition-colors"
        >
          {uploading ? (
            <svg className="animate-spin" width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="white" strokeWidth="2"><path d="M6.5 1v2M6.5 10v2M1 6.5h2M10 6.5h2" strokeLinecap="round"/></svg>
          ) : (
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round"><path d="M6.5 9V2M3 5l3.5-3.5L10 5"/><path d="M1 11h11"/></svg>
          )}
          {uploading ? 'Uploading…' : 'Upload'}
        </button>
      </div>

      {/* Result */}
      {result && (
        <div className="mt-3 flex items-center gap-2 text-[12px] text-emerald-700 bg-emerald-50 rounded-lg px-3 py-2">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 6.5l3 3 6-6"/></svg>
          <span>
            <strong>{result.created}</strong> new transactions imported,{' '}
            <strong>{result.skipped}</strong> already existed
            {result.total > 0 && ` (${result.total} total in file)`}
          </span>
        </div>
      )}
      {error && (
        <div className="mt-3 text-[12px] text-rose-600 bg-rose-50 rounded-lg px-3 py-2">
          {error}
        </div>
      )}
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function LoadingCards() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map(i => (
        <div key={i} className="bg-white rounded-xl border border-gray-200 p-4 animate-pulse">
          <div className="flex items-center gap-3">
            <div className="w-2.5 h-2.5 rounded-full bg-gray-100" />
            <div className="h-4 bg-gray-100 rounded w-48" />
            <div className="h-4 bg-gray-100 rounded w-20" />
          </div>
          <div className="h-3 bg-gray-100 rounded w-64 mt-2 ml-6" />
        </div>
      ))}
    </div>
  )
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
      <div className="w-12 h-12 bg-teal-50 rounded-full flex items-center justify-center mx-auto mb-4">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#0d9488" strokeWidth="1.5" strokeLinecap="round"><path d="M10 2v4M10 14v4M2 10h4M14 10h4M4.9 4.9l2.8 2.8M12.3 12.3l2.8 2.8M4.9 15.1l2.8-2.8M12.3 7.7l2.8-2.8"/></svg>
      </div>
      <p className="text-[14px] font-medium text-gray-700 mb-1">No connectors yet</p>
      <p className="text-[12px] text-gray-400 mb-5">Add your first connector to start fetching data automatically</p>
      <button onClick={onAdd}
        className="px-4 py-2 bg-[#0d9488] text-white text-[13px] font-medium rounded-lg hover:bg-teal-700">
        Add connector
      </button>
    </div>
  )
}
