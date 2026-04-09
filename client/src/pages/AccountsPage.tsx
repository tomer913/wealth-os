import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAccounts, createAccount, updateAccount, deleteAccount } from '../api/portfolio'
import type { Account } from '../types'
import { Modal, ConfirmDialog } from '../components/shared/Modal'
import { MetadataEditor, jsonToPairs, pairsToJson } from '../components/shared/MetadataEditor'
import type { MetaPair } from '../components/shared/MetadataEditor'
import { Field, Input, Select, Textarea, FormGrid, FormSection, Divider } from '../components/shared/Form'
import clsx from 'clsx'

const ACCOUNT_TYPES = ['broker', 'bank', 'pension', 'real_estate', 'crypto', 'other']
const CURRENCIES = ['ILS', 'USD', 'EUR', 'GBP']
const KNOWN_FIELDS = new Set(['name', 'symbol', 'institution', 'custodian', 'account_type',
  'category', 'currency', 'is_liquid', 'is_income_generating', 'include_in_portfolio',
  'status', 'cash_balance', 'opening_balance', 'notes', 'metadata',
  'portfolio_id', 'id', 'created_at', 'updated_at', 'position_count'])

interface AccountForm {
  name: string
  symbol: string
  institution: string
  account_type: string
  currency: string
  include_in_portfolio: boolean
  status: string
  notes: string
}

function emptyForm(): AccountForm {
  return {
    name: '',
    symbol: '',
    institution: '',
    account_type: 'broker',
    currency: 'ILS',
    include_in_portfolio: true,
    status: 'active',
    notes: '',
  }
}

export default function AccountsPage() {
  const qc = useQueryClient()

  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: getAccounts,
  })

  const createMut = useMutation({
    mutationFn: (payload: Record<string, unknown>) => createAccount(payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['accounts'] }); closeModal() },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      updateAccount(id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['accounts'] }); closeModal() },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteAccount(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts'] })
      setDeleteTarget(null)
    },
  })

  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Account | null>(null)
  const [form, setForm] = useState<AccountForm>(emptyForm())
  const [metaPairs, setMetaPairs] = useState<MetaPair[]>([])
  const [deleteTarget, setDeleteTarget] = useState<Account | null>(null)
  const [deleteError, setDeleteError] = useState('')
  const [importText, setImportText] = useState('')
  const [importError, setImportError] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  function openAdd() {
    setEditTarget(null)
    setForm(emptyForm())
    setMetaPairs([])
    setErrors({})
    setShowImport(false)
    setImportText('')
    setModalOpen(true)
  }

  function openEdit(account: Account) {
    setEditTarget(account)
    setForm({
      name: account.name,
      symbol: account.symbol,
      institution: account.institution ?? '',
      account_type: account.account_type ?? 'broker',
      currency: account.currency,
      include_in_portfolio: account.include_in_portfolio,
      status: account.status,
      notes: account.notes ?? '',
    })
    setMetaPairs(jsonToPairs(account.metadata ?? undefined))
    setErrors({})
    setShowImport(false)
    setModalOpen(true)
  }

  function closeModal() {
    setModalOpen(false)
    setEditTarget(null)
    setImportError('')
  }

  function handleImportJson() {
    try {
      const parsed = JSON.parse(importText) as Record<string, unknown>
      const known: Partial<AccountForm> = {}
      const extra: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(parsed)) {
        if (KNOWN_FIELDS.has(k)) {
          (known as Record<string, unknown>)[k] = v
        } else {
          extra[k] = v
        }
      }
      setForm((f) => ({ ...f, ...known }))
      setMetaPairs(jsonToPairs(extra))
      setImportError('')
      setShowImport(false)
      setImportText('')
    } catch {
      setImportError('Invalid JSON — check your format and try again')
    }
  }

  function validate() {
    const e: Record<string, string> = {}
    if (!form.name.trim()) e.name = 'Name is required'
    if (!form.symbol.trim()) e.symbol = 'Symbol is required'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  function handleSubmit() {
    if (!validate()) return
    const metadata = pairsToJson(metaPairs)
    const payload: Record<string, unknown> = {
      ...form,
      ...(Object.keys(metadata).length ? { metadata } : {}),
    }
    if (editTarget) {
      updateMut.mutate({ id: editTarget.id, payload })
    } else {
      createMut.mutate(payload)
    }
  }

  function handleDelete() {
    if (!deleteTarget) return
    setDeleteError('')
    deleteMut.mutate(deleteTarget.id, {
      onError: (err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail
        setDeleteError(detail ?? 'Cannot delete — this account has linked assets')
      },
    })
  }

  const isSaving = createMut.isPending || updateMut.isPending

  return (
    <div className="p-6 pb-20 md:pb-6">

      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-[16px] font-semibold text-gray-900">Accounts</h2>
          <p className="text-[12px] text-gray-400 mt-0.5">{accounts.length} accounts</p>
        </div>
        <button
          onClick={openAdd}
          className="flex items-center gap-2 px-4 py-2 bg-[#0d9488] hover:bg-teal-700 text-white text-[13px] font-medium rounded-lg transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round">
            <path d="M6 1v10M1 6h10"/>
          </svg>
          Add account
        </button>
      </div>

      {/* Table */}
      {isLoading ? <LoadingRows /> : accounts.length === 0 ? <EmptyState onAdd={openAdd} /> : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                {['Account', 'Type', 'Institution', 'Currency', 'Positions', 'Status', ''].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {accounts.map((acc) => (
                <tr key={acc.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="font-semibold text-gray-900">{acc.name}</div>
                    <div className="text-[11px] text-gray-400 font-mono mt-0.5">{acc.symbol}</div>
                  </td>
                  <td className="px-4 py-3"><TypeBadge type={acc.account_type ?? ''} /></td>
                  <td className="px-4 py-3 text-gray-600">{acc.institution ?? '—'}</td>
                  <td className="px-4 py-3 font-mono text-gray-600">{acc.currency}</td>
                  <td className="px-4 py-3"><PositionCountBadge count={acc.position_count} /></td>
                  <td className="px-4 py-3"><StatusBadge status={acc.status} /></td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1 justify-end">
                      <ActionBtn onClick={() => openEdit(acc)} icon="edit" title="Edit" />
                      <ActionBtn
                        onClick={() => { setDeleteTarget(acc); setDeleteError('') }}
                        icon="delete"
                        title={acc.position_count > 0
                          ? `Cannot delete — ${acc.position_count} linked asset${acc.position_count !== 1 ? 's' : ''}`
                          : 'Delete account'}
                        danger
                        disabled={acc.position_count > 0}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add / Edit Modal */}
      <Modal open={modalOpen} onClose={closeModal} title={editTarget ? `Edit — ${editTarget.name}` : 'Add account'} width="max-w-lg">
        <div className="space-y-5">

          {/* JSON Import */}
          <div>
            <button type="button" onClick={() => setShowImport((v) => !v)}
              className="flex items-center gap-1.5 text-[12px] text-teal-600 hover:text-teal-700 font-medium">
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <path d="M2 9v2h9V9M6.5 1v7M4 5l2.5 3L9 5"/>
              </svg>
              Import from JSON
            </button>
            {showImport && (
              <div className="mt-2 space-y-2">
                <Textarea rows={4}
                  placeholder={'{\n  "name": "IBI Broker",\n  "institution": "IBI Bank",\n  "currency": "ILS"\n}'}
                  value={importText}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setImportText(e.target.value)}
                  className="font-mono text-[12px]" />
                {importError && <p className="text-[11px] text-rose-500">{importError}</p>}
                <div className="flex gap-2">
                  <button onClick={handleImportJson} className="px-3 py-1.5 text-[12px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700">Apply</button>
                  <button onClick={() => { setShowImport(false); setImportText(''); setImportError('') }}
                    className="px-3 py-1.5 text-[12px] font-medium text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
                </div>
              </div>
            )}
          </div>

          <Divider />

          {/* Basic details */}
          <FormSection title="Basic details">
            <Field label="Account name" required error={errors.name}>
              <Input value={form.name}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. IBI Broker" error={!!errors.name} />
            </Field>
            <Field label="Symbol / code" required error={errors.symbol}
              hint="Short unique identifier, e.g. IBI_BROKER">
              <Input value={form.symbol}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, symbol: e.target.value })}
                placeholder="e.g. IBI_BROKER" error={!!errors.symbol} />
            </Field>
            <FormGrid>
              <Field label="Account type">
                <Select value={form.account_type}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, account_type: e.target.value })}>
                  {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1).replace('_', ' ')}</option>)}
                </Select>
              </Field>
              <Field label="Currency">
                <Select value={form.currency}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, currency: e.target.value })}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </Field>
            </FormGrid>
            <Field label="Institution / provider">
              <Input value={form.institution}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, institution: e.target.value })}
                placeholder="e.g. IBI Bank, Interactive Brokers" />
            </Field>
          </FormSection>

          <Divider />

          {/* Settings */}
          <FormSection title="Settings">
            <FormGrid>
              <Field label="Status">
                <Select value={form.status}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, status: e.target.value })}>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="closed">Closed</option>
                </Select>
              </Field>
            </FormGrid>
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input type="checkbox" checked={form.include_in_portfolio}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, include_in_portfolio: e.target.checked })}
                className="w-4 h-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
              <span className="text-[13px] text-gray-700">Include in portfolio calculations</span>
            </label>
          </FormSection>

          {/* Metadata */}
          {metaPairs.length > 0 && (
            <>
              <Divider />
              <FormSection title="Additional fields">
                <MetadataEditor pairs={metaPairs} onChange={setMetaPairs} />
              </FormSection>
            </>
          )}

          <Divider />
          <div className="flex items-center justify-between pt-1">
            <button type="button"
              onClick={() => setMetaPairs((p) => [...p, { key: '', value: '' }])}
              className="text-[12px] text-gray-400 hover:text-teal-600 font-medium transition-colors">
              + Add metadata field
            </button>
            <div className="flex gap-2">
              <button onClick={closeModal}
                className="px-4 py-2 text-[13px] font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={handleSubmit} disabled={isSaving}
                className="px-4 py-2 text-[13px] font-medium bg-[#0d9488] hover:bg-teal-700 text-white rounded-lg transition-colors disabled:opacity-60">
                {isSaving ? 'Saving…' : editTarget ? 'Save changes' : 'Add account'}
              </button>
            </div>
          </div>
        </div>
      </Modal>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title={`Delete "${deleteTarget?.name}"?`}
        message={deleteError || 'This cannot be undone. The account will be permanently removed.'}
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onCancel={() => { setDeleteTarget(null); setDeleteError('') }}
      />
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  broker:      'bg-blue-50 text-blue-700',
  bank:        'bg-teal-50 text-teal-700',
  pension:     'bg-purple-50 text-purple-700',
  real_estate: 'bg-amber-50 text-amber-700',
  crypto:      'bg-orange-50 text-orange-700',
  other:       'bg-gray-100 text-gray-500',
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold', TYPE_COLORS[type] ?? 'bg-gray-100 text-gray-500')}>
      {type.replace('_', ' ') || '—'}
    </span>
  )
}

function PositionCountBadge({ count }: { count: number }) {
  return (
    <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold tabular-nums',
      count > 0 ? 'bg-blue-50 text-blue-700' : 'bg-gray-100 text-gray-400')}>
      {count} asset{count !== 1 ? 's' : ''}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const active = status === 'active'
  return (
    <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold',
      active ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-400')}>
      {status || '—'}
    </span>
  )
}

function ActionBtn({ onClick, icon, title, danger, disabled }: {
  onClick: () => void; icon: 'edit' | 'delete'; title: string; danger?: boolean; disabled?: boolean
}) {
  return (
    <button onClick={disabled ? undefined : onClick} title={title} disabled={disabled}
      className={clsx('w-7 h-7 flex items-center justify-center rounded-lg transition-colors',
        disabled ? 'text-gray-200 cursor-not-allowed'
          : danger ? 'text-gray-300 hover:text-rose-500 hover:bg-rose-50'
          : 'text-gray-300 hover:text-teal-600 hover:bg-teal-50')}>
      {icon === 'edit' ? (
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 2l2 2-6 6H3V8l6-6z"/>
        </svg>
      ) : (
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 4h9M5 4V3h3v1M4 4l.5 6h4l.5-6"/>
        </svg>
      )}
    </button>
  )
}

function LoadingRows() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex gap-4 px-4 py-3.5 border-b border-gray-50 last:border-0 animate-pulse">
          <div className="h-4 bg-gray-100 rounded w-1/4" />
          <div className="h-4 bg-gray-100 rounded w-1/6" />
          <div className="h-4 bg-gray-100 rounded w-1/5" />
        </div>
      ))}
    </div>
  )
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
      <p className="text-[14px] font-medium text-gray-600 mb-1">No accounts yet</p>
      <p className="text-[12px] text-gray-400 mb-4">Add your first account to start tracking</p>
      <button onClick={onAdd} className="px-4 py-2 bg-[#0d9488] text-white text-[13px] font-medium rounded-lg hover:bg-teal-700">
        Add account
      </button>
    </div>
  )
}
