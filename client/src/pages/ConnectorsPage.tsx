import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Modal, ConfirmDialog } from '../components/shared/Modal'
import clsx from 'clsx'
import type { Account } from '../types'
import { getAccounts, getAssets, uploadConnectorFile, UploadResult, getProcessingStatus, ProcessingStatus } from '../api/portfolio'

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
  category: 'automatic' | 'manual_upload' | 'scraper'
  flow_type: 'investment' | 'budget' | 'both'
  supports_multi_asset: boolean
  requires_asset_selection_on_upload: boolean
  supported_file_types: string[]
  asset_linking: string
  supports_auto_scrape: boolean
  supports_manual_upload: boolean
  schedule_default: string
  config_fields: { key: string; label: string; type: string; default: string; hint: string }[]
}

// ─── API functions ────────────────────────────────────────────────────────────

import apiClient from '../api/client'
import { DEFAULT_PORTFOLIO_ID } from '../api/portfolio'

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

// ─── Helpers ──────────────────────────────────────────────────────────────────

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

// ─── Section grouping ──────────────────────────────────────────────────────────

const FEED_TYPES = new Set(['ecb_fx', 'yahoo_prices'])

function getSectionKey(type: string, typeDef: ConnectorType | undefined): 'investment' | 'budget' | 'feeds' {
  if (FEED_TYPES.has(type)) return 'feeds'
  const ft = typeDef?.flow_type
  if (ft === 'budget' || ft === 'both') return 'budget'
  return 'investment'
}

function getStatusBadge(c: ConnectorRead, typeDef: ConnectorType | undefined): {
  label: string
  color: 'green' | 'red' | 'yellow' | 'orange' | 'gray'
} {
  if (!c.is_active) return { label: 'notConfigured', color: 'gray' }
  const s = c.last_run_status
  if (!s && !c.last_run_at) {
    return typeDef?.supports_manual_upload
      ? { label: 'uploadPending', color: 'orange' }
      : { label: 'notConfigured', color: 'gray' }
  }
  if (s === 'success') return {
    label: typeDef?.supports_manual_upload ? 'uploaded' : 'active',
    color: 'green',
  }
  if (s === 'failed') return { label: 'failed', color: 'red' }
  if (s === 'skipped') return { label: 'invalidCredentials', color: 'yellow' }
  return { label: 'notConfigured', color: 'gray' }
}

const BADGE_COLORS: Record<string, string> = {
  green:  'bg-emerald-50 text-emerald-700',
  red:    'bg-rose-50 text-rose-700',
  yellow: 'bg-amber-50 text-amber-700',
  orange: 'bg-orange-50 text-orange-700',
  gray:   'bg-gray-100 text-gray-500',
}

// When the user picks "Manual upload" in step 2, remap to the file-upload type
const MANUAL_UPLOAD_TYPE_MAP: Record<string, string> = {
  isracard: 'isracard_xlsx', // isracard scraper → Excel upload
}

// Credential fields shown per connector type in the wizard
const CREDENTIAL_FIELDS: Record<string, { key: string; label: string; sensitive: boolean }[]> = {
  ib_flex: [
    { key: 'query_id',   label: 'Flex Query ID',           sensitive: false },
    { key: 'token',      label: 'Flex Web Service Token',  sensitive: true  },
    { key: 'account_id', label: 'IB Account ID',           sensitive: false },
  ],
  kraken: [
    { key: 'api_key',    label: 'API Key',    sensitive: false },
    { key: 'api_secret', label: 'API Secret', sensitive: true  },
  ],
  cexio: [
    { key: 'api_key',    label: 'API Key',    sensitive: false },
    { key: 'api_secret', label: 'API Secret', sensitive: true  },
    { key: 'username',   label: 'Username',   sensitive: false },
  ],
  isracard: [
    { key: 'username', label: 'ID number (username)', sensitive: false },
    { key: 'password', label: 'Password',              sensitive: true  },
  ],
  cal_scraper: [
    { key: 'username', label: 'Username', sensitive: false },
    { key: 'password', label: 'Password', sensitive: true  },
  ],
}

// ─── SourceSection ─────────────────────────────────────────────────────────────

function SourceSection({
  title, emoji, badge, sources, connectorTypes, onAdd,
  onEdit, onDelete, onRun, onUpload, onHistory, runningIds,
}: {
  title: string
  emoji: string
  badge?: string
  sources: ConnectorRead[]
  connectorTypes: ConnectorType[]
  onAdd: (() => void) | null
  onEdit: (c: ConnectorRead) => void
  onDelete: (c: ConnectorRead) => void
  onRun: (c: ConnectorRead) => void
  onUpload: (c: ConnectorRead) => void
  onHistory: (c: ConnectorRead) => void
  runningIds: Set<string>
}) {
  const { t: tc } = useTranslation('common')
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-[18px]">{emoji}</span>
          <h3 className="text-[14px] font-semibold text-gray-800">{title}</h3>
          {badge && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 font-medium uppercase tracking-wide">
              {badge}
            </span>
          )}
        </div>
        {onAdd && (
          <button type="button" onClick={onAdd}
            className="flex items-center gap-1.5 text-[12px] font-medium text-teal-600 hover:text-teal-700 transition-colors">
            <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M5.5 1v9M1 5.5h9"/></svg>
            {tc('dataSources.addSource')}
          </button>
        )}
      </div>
      {sources.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-gray-200 p-6 text-center">
          <p className="text-[13px] text-gray-400">
            {onAdd ? (
              <>No sources yet.{' '}
                <button type="button" onClick={onAdd} className="text-teal-600 hover:underline">
                  {tc('dataSources.addSource')}
                </button>
              </>
            ) : 'No feeds configured.'}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {sources.map(c => {
            const td = connectorTypes.find(t => t.type === c.type)
            return (
              <DataSourceCard
                key={c.id}
                connector={c}
                typeDef={td}
                isRunning={runningIds.has(c.id) || c.last_run_status === 'running'}
                onEdit={() => onEdit(c)}
                onDelete={() => onDelete(c)}
                onRun={() => onRun(c)}
                onUpload={() => onUpload(c)}
                onHistory={() => onHistory(c)}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── DataSourceCard ────────────────────────────────────────────────────────────

function DataSourceCard({
  connector: c, typeDef, isRunning, onEdit, onDelete, onRun, onUpload, onHistory,
}: {
  connector: ConnectorRead
  typeDef: ConnectorType | undefined
  isRunning: boolean
  onEdit: () => void
  onDelete: () => void
  onRun: () => void
  onUpload: () => void
  onHistory: () => void
}) {
  const { t: tc } = useTranslation('common')
  const { label, color } = getStatusBadge(c, typeDef)

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3 flex items-center gap-3">
      {/* Status dot */}
      <div className={clsx('w-2 h-2 rounded-full flex-shrink-0', {
        'bg-emerald-400': color === 'green',
        'bg-rose-400':    color === 'red',
        'bg-amber-400':   color === 'yellow',
        'bg-orange-400':  color === 'orange',
        'bg-gray-300':    color === 'gray',
      })} />

      {/* Name + details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[13px] font-semibold text-gray-900 truncate">{c.name}</span>
          <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium', BADGE_COLORS[color])}>
            {tc(`dataSources.badges.${label}`)}
          </span>
          {!c.is_active && (
            <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-gray-100 text-gray-400">disabled</span>
          )}
        </div>
        <div className="text-[11px] text-gray-400 mt-0.5 flex items-center gap-2 flex-wrap">
          <span className="font-mono" dir="ltr">{c.type}</span>
          {c.last_run_at && (
            <><span>·</span><span dir="ltr">{formatRelative(c.last_run_at)}</span></>
          )}
          {c.last_error && !isRunning && (
            <><span>·</span><span className="text-rose-500 truncate max-w-[200px]">{c.last_error}</span></>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1 flex-shrink-0">
        {isRunning ? (
          <span className="text-[11px] text-gray-400 px-2 flex items-center gap-1">
            <svg className="animate-spin" width="11" height="11" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6.5 1v2M6.5 10v2M1 6.5h2M10 6.5h2" strokeLinecap="round"/></svg>
            Running…
          </span>
        ) : (
          <>
            {typeDef?.supports_manual_upload && (
              <button type="button" onClick={onUpload}
                className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium text-teal-600 border border-teal-200 rounded-lg hover:bg-teal-50 transition-colors">
                <svg width="11" height="11" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6.5 9V2M3 5l3.5-3.5L10 5"/><path d="M1 11h11"/></svg>
                {tc('dataSources.actions.uploadStatement')}
              </button>
            )}
            {typeDef?.supports_auto_scrape && (
              <button type="button" onClick={onRun} title={tc('dataSources.actions.run')}
                className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-400 hover:text-teal-600 hover:bg-teal-50 transition-colors">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M2 2l9 4.5-9 4.5V2z"/></svg>
              </button>
            )}
          </>
        )}
        <button type="button" onClick={onHistory} title="Run history"
          className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-300 hover:text-gray-600 hover:bg-gray-50 transition-colors">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="6.5" cy="6.5" r="5"/><path d="M6.5 3.5v3l2 1.5"/></svg>
        </button>
        <button type="button" onClick={onEdit} title={tc('dataSources.actions.edit')}
          className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-300 hover:text-teal-600 hover:bg-teal-50 transition-colors">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 2l2 2-6 6H3V8l6-6z"/></svg>
        </button>
        <button type="button" onClick={onDelete} title={tc('dataSources.actions.delete')}
          className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-300 hover:text-rose-500 hover:bg-rose-50 transition-colors">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M2 4h9M5 4V3h3v1M4 4l.5 6h4l.5-6"/></svg>
        </button>
      </div>
    </div>
  )
}

// ─── AddWizardModal ────────────────────────────────────────────────────────────

function AddWizardModal({
  open, mode, editTarget, connectorTypes, onClose, onSave, isSaving,
}: {
  open: boolean
  mode: 'investment' | 'budget'
  editTarget: ConnectorRead | null
  connectorTypes: ConnectorType[]
  onClose: () => void
  onSave: (payload: Record<string, unknown>) => void
  isSaving: boolean
}) {
  const { t: tc } = useTranslation('common')
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [selectedType, setSelectedType] = useState(editTarget?.type ?? '')
  const [connMethod, setConnMethod] = useState<'auto' | 'manual'>('auto')
  const [name, setName] = useState(editTarget?.name ?? '')
  const [config, setConfig] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!open) return
    setStep(1)
    setSelectedType(editTarget?.type ?? '')
    setName(editTarget?.name ?? '')
    setConfig({})
    setConnMethod('auto')
  }, [open, editTarget])

  const typeDef = connectorTypes.find(t => t.type === selectedType)
  const isEditing = !!editTarget
  const isManualOnly = typeDef?.supports_manual_upload && !typeDef?.supports_auto_scrape
  // True when auto scrape exists but is known-broken (a manual upload alternative exists)
  const hasBrokenScraper = !!MANUAL_UPLOAD_TYPE_MAP[selectedType]

  const providers = connectorTypes.filter(t => {
    if (mode === 'investment') return t.flow_type === 'investment' && !FEED_TYPES.has(t.type)
    return t.flow_type === 'budget' || t.flow_type === 'both'
  })

  // Step 2 is shown: investment → only if single-asset; budget → if auto_scrape available
  const needsStep2 = mode === 'investment'
    ? !!(typeDef && !typeDef.supports_multi_asset)
    : !!(typeDef && typeDef.supports_auto_scrape && !isManualOnly)

  const credFields = CREDENTIAL_FIELDS[selectedType] ?? []

  function handleNext() {
    if (step === 1) {
      if (!name) setName(typeDef?.display_name ?? selectedType)
      setStep(needsStep2 ? 2 : 3)
    } else {
      setStep(3)
    }
  }

  function handleBack() {
    if (step === 3) setStep(needsStep2 ? 2 : 1)
    else setStep(1)
  }

  function handleSave() {
    // Remap to manual-upload type when user chose "Manual upload" in step 2
    const finalType = connMethod === 'manual' && MANUAL_UPLOAD_TYPE_MAP[selectedType]
      ? MANUAL_UPLOAD_TYPE_MAP[selectedType]
      : selectedType
    const payload: Record<string, unknown> = {
      name,
      type: finalType,
      schedule: 'daily',
      is_active: true,
      config: Object.fromEntries(Object.entries(config).filter(([, v]) => v !== '')),
    }
    onSave(payload)
  }

  if (!open) return null

  const wizKey = mode === 'investment' ? 'investment' : 'budget'
  const title = isEditing
    ? tc('dataSources.wizard.edit.title')
    : tc(`dataSources.wizard.${wizKey}.title`)

  const stepLabel = step === 1
    ? tc(`dataSources.wizard.${wizKey}.step1`)
    : step === 2
      ? tc(`dataSources.wizard.${wizKey}.step2`)
      : tc(`dataSources.wizard.${wizKey}.step3`)

  return (
    <Modal open={open} onClose={onClose} title={title} width="max-w-lg">
      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-5">
        {([1, 2, 3] as const).map(n => {
          const active = n === step
          const done = n < step
          if (n === 2 && !needsStep2) return null
          return (
            <div key={n} className="flex items-center gap-2">
              {n > 1 && <div className="h-px w-5 bg-gray-200" />}
              <div className={clsx(
                'w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold',
                active ? 'bg-teal-600 text-white' : done ? 'bg-teal-100 text-teal-600' : 'bg-gray-100 text-gray-400',
              )}>
                <span dir="ltr">{n}</span>
              </div>
              {active && <span className="text-[12px] text-gray-600 font-medium">{stepLabel}</span>}
            </div>
          )
        })}
      </div>

      {/* Type-locked warning when editing */}
      {isEditing && step === 1 && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-100 rounded-lg text-[12px] text-amber-700">
          {tc('dataSources.wizard.edit.typeLockedWarning')}
        </div>
      )}

      {/* Step 1 — Provider grid */}
      {step === 1 && (
        <div className="grid grid-cols-2 gap-2">
          {providers.map(t => (
            <button
              key={t.type}
              type="button"
              disabled={isEditing}
              onClick={() => {
                setSelectedType(t.type)
                if (!name) setName(t.display_name)
                // Pre-select manual when provider has a known-broken scraper
                setConnMethod(MANUAL_UPLOAD_TYPE_MAP[t.type] ? 'manual' : 'auto')
              }}
              className={clsx(
                'text-start p-3 rounded-xl border-2 transition-colors',
                isEditing ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer hover:border-teal-300',
                selectedType === t.type ? 'border-teal-500 bg-teal-50' : 'border-gray-200 bg-white',
              )}>
              <div className="text-[13px] font-semibold text-gray-900">
                {t.display_name}
              </div>
              <div className="text-[11px] text-gray-400 mt-0.5 line-clamp-2">{t.description}</div>
            </button>
          ))}
        </div>
      )}

      {/* Step 2 — Investment: multi-asset info / Budget: connection method */}
      {step === 2 && mode === 'investment' && typeDef && (
        <div className="p-3 bg-blue-50 rounded-lg text-[13px] text-gray-700">
          {typeDef.supports_multi_asset
            ? tc('dataSources.wizard.investment.step2MultiAsset')
            : 'This source is linked to a single asset.'}
        </div>
      )}
      {step === 2 && mode === 'budget' && (
        <div className="space-y-3">
          {/* Auto sync option */}
          <label className={clsx(
            'flex items-start gap-3 p-3 rounded-xl border-2 transition-colors',
            hasBrokenScraper ? 'border-gray-200 bg-gray-50 cursor-not-allowed' :
              connMethod === 'auto' ? 'border-teal-500 bg-teal-50 cursor-pointer' : 'border-gray-200 cursor-pointer',
          )}>
            <input type="radio" name="connMethod" value="auto"
              checked={connMethod === 'auto'}
              disabled={hasBrokenScraper}
              onChange={() => setConnMethod('auto')}
              className="mt-0.5" />
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={clsx('text-[13px] font-semibold', hasBrokenScraper ? 'text-gray-400' : 'text-gray-900')}>
                  {tc('dataSources.wizard.budget.step2Auto')}
                </span>
                {hasBrokenScraper && (
                  <span className="text-[11px] text-amber-600 font-medium">
                    ⚠️ Currently unavailable (SMS 2FA required)
                  </span>
                )}
              </div>
              <div className={clsx('text-[12px] mt-0.5', hasBrokenScraper ? 'text-gray-400' : 'text-gray-500')}>
                {tc('dataSources.wizard.budget.step2AutoDesc')}
              </div>
            </div>
          </label>
          {/* Manual upload option */}
          <label className={clsx(
            'flex items-start gap-3 p-3 rounded-xl border-2 cursor-pointer transition-colors',
            connMethod === 'manual' ? 'border-teal-500 bg-teal-50' : 'border-gray-200',
          )}>
            <input type="radio" name="connMethod" value="manual"
              checked={connMethod === 'manual'}
              onChange={() => setConnMethod('manual')}
              className="mt-0.5" />
            <div>
              <div className="text-[13px] font-semibold text-gray-900">{tc('dataSources.wizard.budget.step2Manual')}</div>
              <div className="text-[12px] text-gray-500 mt-0.5">
                {hasBrokenScraper
                  ? 'Upload Excel files from the Isracard website (btbisrael.co.il)'
                  : tc('dataSources.wizard.budget.step2ManualDesc')}
              </div>
            </div>
          </label>
        </div>
      )}

      {/* Step 3 — Name + credentials */}
      {step === 3 && (
        <div className="space-y-4">
          <div className="space-y-1">
            <label className="text-[12px] font-medium text-gray-700">{tc('dataSources.wizard.common.name')}</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder={tc('dataSources.wizard.common.namePlaceholder')}
              className="w-full px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400" />
          </div>

          {/* Credential fields — auto sync only */}
          {(connMethod === 'auto' || mode === 'investment') && !isManualOnly &&
            credFields.map(f => (
              <div key={f.key} className="space-y-1">
                <label className="text-[12px] font-medium text-gray-700">{f.label}</label>
                <input
                  type={f.sensitive ? 'password' : 'text'}
                  value={config[f.key] ?? ''}
                  onChange={e => setConfig(c => ({ ...c, [f.key]: e.target.value }))}
                  placeholder={isEditing ? tc('dataSources.wizard.edit.credentialsPlaceholder') : ''}
                  className="w-full px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 font-mono" />
              </div>
            ))}

          {/* Info note */}
          {(connMethod === 'manual' || isManualOnly) ? (
            <p className="text-[12px] text-gray-500 bg-blue-50 rounded-lg p-3">
              {tc('dataSources.wizard.budget.manualNote')}
            </p>
          ) : credFields.length > 0 ? (
            <p className="text-[11px] text-gray-400">
              🔒 {tc('dataSources.wizard.investment.credentialsEncrypted')}
            </p>
          ) : null}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-100">
        <button type="button" onClick={step === 1 ? onClose : handleBack}
          className="px-4 py-2 text-[13px] font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
          {step === 1 ? tc('dataSources.wizard.common.cancel') : tc('dataSources.wizard.common.back')}
        </button>
        {step < 3 ? (
          <button type="button" onClick={handleNext} disabled={step === 1 && !selectedType}
            className="px-4 py-2 text-[13px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50">
            {tc('dataSources.wizard.common.next')}
          </button>
        ) : (
          <button type="button" onClick={handleSave} disabled={isSaving || !name}
            className="px-4 py-2 text-[13px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-60">
            {isSaving ? 'Saving…' : tc('dataSources.wizard.common.save')}
          </button>
        )}
      </div>
    </Modal>
  )
}

// ─── UploadModal ───────────────────────────────────────────────────────────────

interface PendingFile {
  file: File
  status: 'pending' | 'uploading' | 'done' | 'error'
  transactionCount: number | null
  needsReview: number | null
  error: string | null
}

type UploadState = 'form' | 'uploading' | 'processing' | 'done' | 'timeout'

function UploadModal({
  connector, connectorTypes, onClose, onSuccess,
}: {
  connector: ConnectorRead
  connectorTypes: ConnectorType[]
  onClose: () => void
  onSuccess: () => void
}) {
  const { t: tc } = useTranslation('common')
  const typeDef = connectorTypes.find(t => t.type === connector.type)
  const needsAsset = typeDef?.requires_asset_selection_on_upload ?? false
  const acceptAttr = typeDef?.supported_file_types.map(e => `.${e}`).join(',') ?? '.pdf'

  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([])
  const [assetId, setAssetId] = useState('')
  const [uploadState, setUploadState] = useState<UploadState>('form')
  const [processingStatus, setProcessingStatus] = useState<ProcessingStatus | null>(null)

  const { data: assetList } = useQuery({
    queryKey: ['assets'],
    queryFn: () => getAssets({ limit: 500 }),
    enabled: needsAsset,
  })
  const assets = assetList?.items ?? []

  const canUpload = pendingFiles.length > 0 && (!needsAsset || !!assetId) && uploadState === 'form'

  function addFiles(fileList: FileList | null) {
    if (!fileList) return
    setPendingFiles(prev => [
      ...prev,
      ...Array.from(fileList).map(f => ({
        file: f, status: 'pending' as const,
        transactionCount: null, needsReview: null, error: null,
      })),
    ])
  }

  async function pollStatus(jobId: string) {
    const MAX_POLLS = 40  // 40 × 3s = 2 min max
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise(r => setTimeout(r, 3000))
      try {
        const s = await getProcessingStatus(jobId)
        setProcessingStatus(s)
        if (s.status === 'done' || s.status === 'failed') return
      } catch {
        // transient network error — keep polling
      }
    }
    setUploadState('timeout')
  }

  async function handleUploadAll() {
    if (!canUpload) return
    setUploadState('uploading')
    let lastJobId: string | null = null

    for (let i = 0; i < pendingFiles.length; i++) {
      const isLast = i === pendingFiles.length - 1
      const currentFile = pendingFiles[i]
      setPendingFiles(prev => prev.map((f, j) => j === i ? { ...f, status: 'uploading' } : f))
      try {
        const res = await uploadConnectorFile(
          connector.id, currentFile.file,
          needsAsset ? assetId : undefined,
          isLast,
        )
        const raw = res as Record<string, unknown>
        const txCount = (raw.raw_created ?? raw.created ?? null) as number | null
        if (isLast && raw.job_id) lastJobId = raw.job_id as string
        setPendingFiles(prev => prev.map((f, j) =>
          j === i ? { ...f, status: 'done', transactionCount: txCount, needsReview: null } : f,
        ))
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? String(e)
        setPendingFiles(prev => prev.map((f, j) =>
          j === i ? { ...f, status: 'error', error: typeof msg === 'string' ? msg : 'Upload failed' } : f,
        ))
      }
    }

    if (lastJobId) {
      setUploadState('processing')
      await pollStatus(lastJobId)
      setUploadState('done')
    } else {
      setUploadState('done')
    }
    onSuccess()
  }

  const totalInserted = pendingFiles.reduce((s, f) => s + (f.transactionCount ?? 0), 0)
  const doneCount     = pendingFiles.filter(f => f.status === 'done').length
  const errorCount    = pendingFiles.filter(f => f.status === 'error').length
  const title = `${tc('dataSources.upload.title')} — ${connector.name}`

  function FileStatusIcon({ f }: { f: PendingFile }) {
    if (f.status === 'done')     return <span className="text-[14px]">✅</span>
    if (f.status === 'error')    return <span className="text-[14px]">❌</span>
    if (f.status === 'uploading')
      return <svg className="animate-spin text-teal-500" width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6.5 1v2M6.5 10v2M1 6.5h2M10 6.5h2" strokeLinecap="round"/></svg>
    return <span className="text-gray-300 text-[14px]">📄</span>
  }

  return (
    <Modal open onClose={onClose} title={title} width="max-w-md">

      {/* ── Processing state ────────────────────────────────────────────────── */}
      {uploadState === 'processing' && (
        <div className="space-y-4 py-4 text-center">
          <div className="text-[28px]">⏳</div>
          <div className="text-[14px] font-semibold text-gray-800">{tc('upload.classifying')}</div>
          {processingStatus && (
            <div className="text-[13px] text-gray-500">
              {tc('upload.classifyingProgress', {
                done: processingStatus.classified,
                total: totalInserted,
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Timeout state ───────────────────────────────────────────────────── */}
      {uploadState === 'timeout' && (
        <div className="space-y-4 py-4 text-center">
          <div className="text-[28px]">⏳</div>
          <div className="text-[14px] font-semibold text-gray-800">{tc('upload.stillRunning')}</div>
          <div className="text-[12px] text-gray-500">{tc('upload.checkLater')}</div>
          <button type="button" onClick={onClose}
            className="w-full px-4 py-2 text-[13px] font-medium border border-gray-200 rounded-lg hover:bg-gray-50">
            Close
          </button>
        </div>
      )}

      {/* ── Done state ──────────────────────────────────────────────────────── */}
      {uploadState === 'done' && (
        <div className="space-y-4">
          <div className="text-center py-2">
            <div className="text-[28px] mb-1">{errorCount === 0 ? '✅' : '⚠️'}</div>
            <div className="text-[15px] font-bold text-gray-900">{tc('upload.uploadComplete')}</div>
          </div>
          <div className="space-y-1.5">
            {pendingFiles.map((f, i) => (
              <div key={i} className="flex items-center gap-2 text-[12px]">
                <FileStatusIcon f={f} />
                <span dir="ltr" className="flex-1 font-mono text-gray-600 truncate">{f.file.name}</span>
                {f.status === 'done' && (
                  <span dir="ltr" className="text-emerald-600 font-medium">
                    {f.transactionCount ?? 0} imported
                  </span>
                )}
                {f.status === 'error' && (
                  <span className="text-rose-500 truncate max-w-[120px]">{f.error}</span>
                )}
              </div>
            ))}
          </div>
          {processingStatus && (
            <div className="bg-gray-50 rounded-lg p-3 text-[12px] space-y-1">
              <div className="text-gray-700">
                {tc('upload.combinedTotal', { count: processingStatus.classified })}
              </div>
              {processingStatus.needs_review > 0 && (
                <div className="text-amber-600">
                  {tc('dataSources.upload.success.needsReview')}: {processingStatus.needs_review}
                </div>
              )}
            </div>
          )}
          <button type="button" onClick={onClose}
            className="w-full px-4 py-2 text-[13px] font-medium border border-gray-200 rounded-lg hover:bg-gray-50">
            Close
          </button>
        </div>
      )}

      {/* ── Form + uploading states ─────────────────────────────────────────── */}
      {(uploadState === 'form' || uploadState === 'uploading') && (
        <div className="space-y-4">
          <p className="text-[12px] text-gray-500">
            {tc('dataSources.upload.accepts')}:{' '}
            <span dir="ltr" className="font-mono">{acceptAttr}</span>
          </p>

          {needsAsset && (
            <div className="space-y-1">
              <label className="text-[12px] font-medium text-gray-700">{tc('dataSources.upload.asset')}</label>
              <select value={assetId} onChange={e => setAssetId(e.target.value)}
                className="w-full px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400">
                <option value="">— select asset —</option>
                {assets.map(a => <option key={a.id} value={a.id}>{a.name} ({a.symbol})</option>)}
              </select>
            </div>
          )}

          {pendingFiles.length > 0 && (
            <div className="space-y-1.5">
              {pendingFiles.map((f, i) => (
                <div key={i} className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg text-[12px]">
                  <FileStatusIcon f={f} />
                  <span dir="ltr" className="flex-1 font-mono text-gray-700 truncate">{f.file.name}</span>
                  {f.status === 'done' && (
                    <span dir="ltr" className="text-emerald-600 font-medium">
                      {f.transactionCount ?? 0} imported
                    </span>
                  )}
                  {f.status === 'uploading' && (
                    <span className="text-gray-400">{tc('upload.uploading')}</span>
                  )}
                  {f.status === 'pending' && uploadState === 'form' && (
                    <button type="button" onClick={() => setPendingFiles(prev => prev.filter((_, j) => j !== i))}
                      className="text-gray-300 hover:text-rose-400 flex-shrink-0">
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M1 1l10 10M11 1L1 11"/></svg>
                    </button>
                  )}
                  {f.status === 'error' && (
                    <span className="text-rose-500 truncate max-w-[100px]">{f.error}</span>
                  )}
                </div>
              ))}
            </div>
          )}

          <label className={clsx(
            'block border-2 border-dashed rounded-xl p-4 text-center cursor-pointer transition-colors',
            uploadState === 'uploading' ? 'border-gray-100 opacity-50 pointer-events-none' : 'border-gray-200 hover:border-teal-300',
          )}>
            <div className="text-[13px] text-gray-500">
              {pendingFiles.length === 0 ? tc('dataSources.upload.dragDrop') : tc('upload.addFiles')}
            </div>
            <input type="file" accept={acceptAttr} multiple className="hidden"
              onChange={e => addFiles(e.target.files)} />
            <div className="mt-2 inline-flex px-3 py-1.5 text-[12px] font-medium text-teal-600 border border-teal-200 rounded-lg hover:bg-teal-50">
              {pendingFiles.length === 0 ? tc('dataSources.upload.chooseFile') : tc('upload.addFiles')}
            </div>
          </label>

          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} disabled={uploadState === 'uploading'}
              className="flex-1 px-4 py-2 text-[13px] font-medium border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50">
              Cancel
            </button>
            <button type="button" onClick={handleUploadAll} disabled={!canUpload}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-[13px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50">
              {uploadState === 'uploading' ? (
                <><svg className="animate-spin" width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="white" strokeWidth="2"><path d="M6.5 1v2M6.5 10v2M1 6.5h2M10 6.5h2" strokeLinecap="round"/></svg>{tc('upload.uploading')}</>
              ) : (
                <><svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round"><path d="M6.5 9V2M3 5l3.5-3.5L10 5"/><path d="M1 11h11"/></svg>
                  {pendingFiles.length > 1 ? tc('upload.uploadAll', { count: pendingFiles.length }) : 'Upload'}</>
              )}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ─── RunHistoryDrawer ──────────────────────────────────────────────────────────

function RunHistoryDrawer({ connector, onClose }: { connector: ConnectorRead; onClose: () => void }) {
  const { data } = useQuery({
    queryKey: ['runs', connector.id],
    queryFn: () => getConnectorRuns(connector.id),
    refetchInterval: 5000,
  })
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const runs = data?.items ?? []

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <div className="relative bg-white w-full max-w-lg shadow-2xl flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <h3 className="text-[14px] font-semibold text-gray-900">Run History</h3>
            <p className="text-[12px] text-gray-400 mt-0.5">{connector.name}</p>
          </div>
          <button type="button" onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l10 10M12 2L2 12"/></svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {runs.length === 0 ? (
            <div className="p-8 text-center text-[13px] text-gray-400">No runs yet</div>
          ) : runs.map(run => (
            <div key={run.id} className="border-b border-gray-50 last:border-0">
              <button type="button"
                onClick={() => setExpandedId(expandedId === run.id ? null : run.id)}
                className="w-full flex items-start gap-3 px-5 py-3.5 hover:bg-gray-50 text-left transition-colors">
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
                    <span className="text-[11px] text-gray-400">{formatRelative(run.started_at)}</span>
                  </div>
                  <div className="text-[11px] text-gray-400 mt-0.5 flex gap-3 flex-wrap">
                    {run.duration_ms && <span>{formatDuration(run.duration_ms)}</span>}
                    {run.transactions_created != null && run.transactions_created > 0 && (
                      <span className="text-emerald-600">+{run.transactions_created} txns</span>
                    )}
                    {run.assets_created != null && run.assets_created > 0 && (
                      <span className="text-blue-600">+{run.assets_created} assets</span>
                    )}
                    {run.prices_updated != null && run.prices_updated > 0 && (
                      <span>{run.prices_updated} prices</span>
                    )}
                    <span className="text-gray-300">{run.triggered_by}</span>
                  </div>
                  {run.status === 'failed' && run.error_message && (
                    <p className="text-[11px] text-rose-500 mt-1 truncate">{run.error_message}</p>
                  )}
                  {run.checkpoint?.github_run_url && (
                    <a href={run.checkpoint.github_run_url} target="_blank" rel="noreferrer"
                      onClick={e => e.stopPropagation()}
                      className="text-[11px] text-teal-600 hover:underline mt-0.5 block">
                      View on GitHub →
                    </a>
                  )}
                </div>
              </button>
              {expandedId === run.id && run.error_message && (
                <div className="mx-5 mb-3 p-3 bg-rose-50 rounded-lg space-y-2">
                  <p className="text-[12px] font-medium text-rose-700">Error</p>
                  <pre className="text-[11px] text-rose-600 whitespace-pre-wrap font-sans leading-relaxed">{run.error_message}</pre>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── LoadingCards ──────────────────────────────────────────────────────────────

function LoadingCards() {
  return (
    <div className="space-y-2">
      {[1, 2, 3, 4].map(i => (
        <div key={i} className="bg-white rounded-xl border border-gray-200 px-4 py-3 flex items-center gap-3 animate-pulse">
          <div className="w-2 h-2 rounded-full bg-gray-200 flex-shrink-0" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3.5 bg-gray-200 rounded w-1/3" />
            <div className="h-3 bg-gray-100 rounded w-1/4" />
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ConnectorsPage() {
  const qc = useQueryClient()
  const { t: tc } = useTranslation('common')

  const { data: connectors = [], isLoading } = useQuery({
    queryKey: ['connectors'],
    queryFn: getConnectors,
    refetchInterval: (query) => {
      const data = query.state.data as ConnectorRead[] | undefined
      return data?.some(c => c.last_run_status === 'running' || c.last_run_status === 'pending')
        ? 5000
        : false
    },
  })

  const { data: connectorTypes = [] } = useQuery({
    queryKey: ['connector-types'],
    queryFn: getConnectorTypes,
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ['connectors'] }),
  })

  // Report toast
  const [reportToast, setReportToast] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  async function handleSendReport() {
    setReportToast('sending')
    try {
      await apiClient.post('/api/v1/connectors/send-daily-report/')
      setReportToast('sent')
      setTimeout(() => setReportToast('idle'), 4000)
    } catch {
      setReportToast('error')
      setTimeout(() => setReportToast('idle'), 4000)
    }
  }

  // Modal / drawer state
  const [wizardOpen, setWizardOpen]     = useState(false)
  const [wizardMode, setWizardMode]     = useState<'investment' | 'budget'>('investment')
  const [editTarget, setEditTarget]     = useState<ConnectorRead | null>(null)
  const [uploadTarget, setUploadTarget] = useState<ConnectorRead | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ConnectorRead | null>(null)
  const [deleteError, setDeleteError]   = useState('')
  const [historyTarget, setHistoryTarget] = useState<ConnectorRead | null>(null)
  const [runningIds] = useState<Set<string>>(new Set())

  const isSaving = createMut.isPending || updateMut.isPending

  // Auto-fail stuck runs on mount
  const checkedRef = useRef(false)
  useEffect(() => {
    if (checkedRef.current || connectors.length === 0) return
    const running = connectors.filter(
      c => c.last_run_status === 'running' || c.last_run_status === 'pending'
    )
    if (running.length === 0) return
    checkedRef.current = true
    running.forEach(c => apiClient.get(`/api/v1/connectors/${c.id}/status/`).catch(() => {}))
    qc.invalidateQueries({ queryKey: ['connectors'] })
  }, [connectors.length]) // eslint-disable-line react-hooks/exhaustive-deps

  function openEdit(c: ConnectorRead) {
    setEditTarget(c)
    const td = connectorTypes.find(t => t.type === c.type)
    const section = getSectionKey(c.type, td)
    setWizardMode(section === 'budget' ? 'budget' : 'investment')
    setWizardOpen(true)
  }

  function closeModal() {
    setWizardOpen(false)
    setEditTarget(null)
  }

  function handleSubmit(payload: Record<string, unknown>) {
    if (editTarget) {
      updateMut.mutate({ id: editTarget.id, payload })
    } else {
      createMut.mutate(payload)
    }
  }

  // Group connectors into sections
  const investSources = connectors.filter(c => {
    const td = connectorTypes.find(t => t.type === c.type)
    return getSectionKey(c.type, td) === 'investment'
  })
  const budgetSources = connectors.filter(c => {
    const td = connectorTypes.find(t => t.type === c.type)
    return getSectionKey(c.type, td) === 'budget'
  })
  const feedSources = connectors.filter(c => FEED_TYPES.has(c.type))

  const activeSources = connectors.filter(
    c => c.is_active && c.last_run_status === 'success'
  ).length
  const lastSyncDates = connectors.map(c => c.last_run_at).filter(Boolean).sort() as string[]
  const lastSyncAt: string | null = lastSyncDates.length > 0 ? lastSyncDates[lastSyncDates.length - 1] : null

  return (
    <div className="p-6 pb-20 md:pb-6">

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-[16px] font-semibold text-gray-900">{tc('dataSources.title')}</h2>
          <p className="text-[12px] text-gray-400 mt-0.5">
            {connectors.length} source{connectors.length !== 1 ? 's' : ''} configured
          </p>
        </div>
        <button type="button" onClick={handleSendReport} disabled={reportToast === 'sending'}
          className="flex items-center gap-1.5 px-3 py-2 text-[13px] font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors">
          {reportToast === 'sending'
            ? <svg className="animate-spin" width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6.5 1v2M6.5 10v2M1 6.5h2M10 6.5h2" strokeLinecap="round"/></svg>
            : <span>📱</span>}
          {reportToast === 'sent' ? 'Sent!' : reportToast === 'error' ? 'Failed' : tc('dataSources.sendReport')}
        </button>
      </div>

      {/* Report toast */}
      {reportToast === 'sent' && (
        <div className="mb-4 flex items-center gap-2 px-4 py-2.5 bg-emerald-50 border border-emerald-100 rounded-xl text-[13px] text-emerald-700 font-medium">
          📱 Report sent to Telegram!
        </div>
      )}
      {reportToast === 'error' && (
        <div className="mb-4 flex items-center gap-2 px-4 py-2.5 bg-rose-50 border border-rose-100 rounded-xl text-[13px] text-rose-700 font-medium">
          Failed to send report — check Railway logs
        </div>
      )}

      {/* Stats bar */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3">
          <div className="text-[11px] text-gray-400 font-medium uppercase tracking-wide">{tc('dataSources.activeSources')}</div>
          <div className="text-[22px] font-bold text-gray-900 mt-0.5">
            {activeSources}{' '}
            <span className="text-[14px] font-normal text-gray-400">/ {connectors.length}</span>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3">
          <div className="text-[11px] text-gray-400 font-medium uppercase tracking-wide">{tc('dataSources.lastSync')}</div>
          <div className="text-[14px] font-semibold text-gray-900 mt-0.5" dir="ltr">
            {lastSyncAt ? formatRelative(lastSyncAt) : tc('dataSources.neverSynced')}
          </div>
        </div>
      </div>

      {/* Sections */}
      {isLoading ? <LoadingCards /> : (
        <div className="space-y-8">
          <SourceSection
            title={tc('dataSources.sections.investment')}
            emoji="📈"
            badge={tc('dataSources.badges.autoSync')}
            sources={investSources}
            connectorTypes={connectorTypes}
            onAdd={() => { setWizardMode('investment'); setWizardOpen(true) }}
            onEdit={openEdit}
            onDelete={c => { setDeleteTarget(c); setDeleteError('') }}
            onRun={c => runMut.mutate(c.id)}
            onUpload={c => setUploadTarget(c)}
            onHistory={c => setHistoryTarget(c)}
            runningIds={runningIds}
          />
          <SourceSection
            title={tc('dataSources.sections.budget')}
            emoji="💳"
            badge={tc('dataSources.badges.manualUpload')}
            sources={budgetSources}
            connectorTypes={connectorTypes}
            onAdd={() => { setWizardMode('budget'); setWizardOpen(true) }}
            onEdit={openEdit}
            onDelete={c => { setDeleteTarget(c); setDeleteError('') }}
            onRun={c => runMut.mutate(c.id)}
            onUpload={c => setUploadTarget(c)}
            onHistory={c => setHistoryTarget(c)}
            runningIds={runningIds}
          />
          {feedSources.length > 0 && (
            <SourceSection
              title={tc('dataSources.sections.feeds')}
              emoji="🌍"
              sources={feedSources}
              connectorTypes={connectorTypes}
              onAdd={null}
              onEdit={openEdit}
              onDelete={c => { setDeleteTarget(c); setDeleteError('') }}
              onRun={c => runMut.mutate(c.id)}
              onUpload={c => setUploadTarget(c)}
              onHistory={c => setHistoryTarget(c)}
              runningIds={runningIds}
            />
          )}
        </div>
      )}

      {/* Wizard modal */}
      <AddWizardModal
        open={wizardOpen}
        mode={wizardMode}
        editTarget={editTarget}
        connectorTypes={connectorTypes}
        onClose={closeModal}
        onSave={handleSubmit}
        isSaving={isSaving}
      />

      {/* Upload modal */}
      {uploadTarget && (
        <UploadModal
          connector={uploadTarget}
          connectorTypes={connectorTypes}
          onClose={() => setUploadTarget(null)}
          onSuccess={() => {
            setUploadTarget(null)
            qc.invalidateQueries({ queryKey: ['connectors'] })
          }}
        />
      )}

      {/* Run history drawer */}
      {historyTarget && (
        <RunHistoryDrawer connector={historyTarget} onClose={() => setHistoryTarget(null)} />
      )}

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title={deleteTarget ? `Delete "${deleteTarget.name}"?` : ''}
        message={deleteError || 'This will also delete all run history for this connector.'}
        confirmLabel="Delete" danger
        onConfirm={() => {
          if (!deleteTarget) return
          setDeleteError('')
          deleteMut.mutate(deleteTarget.id, {
            onError: (err: unknown) => {
              const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
              setDeleteError(detail ?? 'Cannot delete connector')
            },
          })
        }}
        onCancel={() => { setDeleteTarget(null); setDeleteError('') }}
      />
    </div>
  )
}
