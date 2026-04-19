import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getValuations, createValuation, updateValuation, deleteValuation, getAssets, getAccounts } from '../api/portfolio'
import { useCategoryFilter } from '../hooks/usePortfolio'
import type { ManualValuation } from '../types'
import { Modal, ConfirmDialog } from '../components/shared/Modal'
import { Field, Input, Select, Textarea, FormGrid, FormSection, Divider } from '../components/shared/Form'
import { formatILS, formatILSShort, formatDate } from '../utils/format'
import clsx from 'clsx'

const METHODS = ['manual', 'appraisal', 'broker_estimate', 'model']
const CONFIDENCE = ['low', 'medium', 'high']
const CURRENCIES = ['ILS', 'USD', 'EUR', 'GBP']
const SOURCES = ['manual', 'import', 'connector']
const PAGE_SIZE = 50

interface ValForm {
  valuation_date: string
  market_value: string
  currency: string
  fx_rate_to_ils: string
  value_ils: string
  valuation_method: string
  confidence_level: string
  valuation_source: string
  is_estimated: boolean
  notes: string
  source: string
  asset_id: string
  account_id: string
}

function emptyForm(): ValForm {
  return {
    valuation_date: new Date().toISOString().split('T')[0],
    market_value: '', currency: 'ILS', fx_rate_to_ils: '1.0',
    value_ils: '', valuation_method: 'manual', confidence_level: 'medium',
    valuation_source: '', is_estimated: false, notes: '',
    source: 'manual', asset_id: '', account_id: '',
  }
}

export default function ValuationsPage() {
  const { t } = useTranslation('valuations')
  const qc = useQueryClient()
  const categoryFilter = useCategoryFilter()

  const [page, setPage] = useState(1)
  const [filterAsset, setFilterAsset] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['valuations', { page, filterAsset, dateFrom, dateTo }],
    queryFn: () => getValuations({
      page,
      limit: PAGE_SIZE,
      ...(filterAsset ? { asset_id: filterAsset } : {}),
      ...(dateFrom ? { date_from: dateFrom } : {}),
      ...(dateTo ? { date_to: dateTo } : {}),
    }),
  })

  const { data: assetsData } = useQuery({
    queryKey: ['assets'],
    queryFn: () => getAssets({ limit: 500 }),
  })

  const { data: accountsData = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => import('../api/portfolio').then(m => m.getAccounts()),
  })

  const assetList = assetsData?.items ?? []
  const assetMap = useMemo(() =>
    Object.fromEntries(assetList.map((a) => [a.id, a])), [assetList])
  const accountMap = useMemo(() =>
    Object.fromEntries(accountsData.map((a) => [a.id, a])), [accountsData])

  // Apply category chip filter client-side
  const valuations = useMemo(() => {
    const items = data?.items ?? []
    if (categoryFilter.length === 0) return items
    return items.filter((v) => {
      const asset = assetMap[v.asset_id]
      return asset && categoryFilter.includes(asset.category ?? '')
    })
  }, [data, categoryFilter, assetMap])

  const total = data?.total ?? 0
  const totalPages = data?.pages ?? 1

  // Summary stats
  const totalValueILS = valuations.reduce((sum, v) => sum + (Number(v.value_ils) || 0), 0)
  const uniqueAssets = new Set(valuations.map((v) => v.asset_id)).size

  const createMut = useMutation({
    mutationFn: (p: Record<string, unknown>) => createValuation(p),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['valuations'] }); closeModal() },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      updateValuation(id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['valuations'] }); closeModal() },
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteValuation(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['valuations'] }); setDeleteTarget(null) },
  })

  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<ManualValuation | null>(null)
  const [form, setForm] = useState<ValForm>(emptyForm())
  const [deleteTarget, setDeleteTarget] = useState<ManualValuation | null>(null)
  const [deleteError, setDeleteError] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  function openAdd() {
    setEditTarget(null); setForm(emptyForm()); setErrors({}); setModalOpen(true)
  }

  function openEdit(v: ManualValuation) {
    setEditTarget(v)
    setForm({
      valuation_date: v.valuation_date,
      market_value: v.market_value.toString(),
      currency: v.currency,
      fx_rate_to_ils: v.fx_rate_to_ils.toString(),
      value_ils: v.value_ils?.toString() ?? '',
      valuation_method: v.valuation_method,
      confidence_level: v.confidence_level,
      valuation_source: v.valuation_source ?? '',
      is_estimated: v.is_estimated,
      notes: v.notes ?? '',
      source: v.source,
      asset_id: v.asset_id,
      account_id: v.account_id ?? '',
    })
    setErrors({}); setModalOpen(true)
  }

  function closeModal() { setModalOpen(false); setEditTarget(null) }

  function validate() {
    const e: Record<string, string> = {}
    if (!form.asset_id) e.asset_id = t('error_asset_required')
    if (!form.valuation_date) e.valuation_date = t('error_date_required')
    if (!form.market_value) e.market_value = t('error_value_required')
    setErrors(e)
    return Object.keys(e).length === 0
  }

  function handleSubmit() {
    if (!validate()) return
    const payload: Record<string, unknown> = {
      valuation_date: form.valuation_date,
      market_value: parseFloat(form.market_value),
      currency: form.currency,
      fx_rate_to_ils: parseFloat(form.fx_rate_to_ils || '1'),
      valuation_method: form.valuation_method,
      confidence_level: form.confidence_level,
      is_estimated: form.is_estimated,
      source: form.source,
      asset_id: form.asset_id,
      ...(form.account_id ? { account_id: form.account_id } : {}),
      ...(form.value_ils ? { value_ils: parseFloat(form.value_ils) } : {}),
      ...(form.valuation_source ? { valuation_source: form.valuation_source } : {}),
      ...(form.notes ? { notes: form.notes } : {}),
    }
    if (editTarget) updateMut.mutate({ id: editTarget.id, payload })
    else createMut.mutate(payload)
  }

  const isSaving = createMut.isPending || updateMut.isPending

  // Auto-compute value_ils when market_value or fx_rate changes
  function handleMarketValueChange(val: string) {
    const mv = parseFloat(val) || 0
    const fx = parseFloat(form.fx_rate_to_ils) || 1
    setForm({ ...form, market_value: val, value_ils: (mv * fx).toFixed(4) })
  }

  function handleFxRateChange(val: string) {
    const mv = parseFloat(form.market_value) || 0
    const fx = parseFloat(val) || 1
    setForm({ ...form, fx_rate_to_ils: val, value_ils: (mv * fx).toFixed(4) })
  }

  const clearFilters = () => {
    setFilterAsset(''); setDateFrom(''); setDateTo(''); setPage(1)
  }
  const hasFilters = filterAsset || dateFrom || dateTo

  return (
    <div className="p-6 pb-20 md:pb-6">

      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-[16px] font-semibold text-gray-900">{t('title')}</h2>
          <p className="text-[12px] text-gray-400 mt-0.5">
            {t('count', { count: total })} · {t('assets_covered', { count: uniqueAssets })}
            {totalPages > 1 && ` · ${t('page_of', { page, total: totalPages })}`}
          </p>
        </div>
        <button onClick={openAdd}
          className="flex items-center gap-2 px-4 py-2 bg-[#0d9488] hover:bg-teal-700 text-white text-[13px] font-medium rounded-lg transition-colors">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round"><path d="M6 1v10M1 6h10"/></svg>
          {t('add_valuation')}
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
          <p className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">{t('label_records')}</p>
          <p className="text-[22px] font-bold text-gray-900 num">{total}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
          <p className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">{t('label_assets')}</p>
          <p className="text-[22px] font-bold text-gray-900 num">{uniqueAssets}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
          <p className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">{t('total_value')}</p>
          <p className="text-[22px] font-bold text-gray-900 num">{formatILSShort(totalValueILS)}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4 flex-wrap">
        <select value={filterAsset} onChange={(e) => { setFilterAsset(e.target.value); setPage(1) }}
          className="px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none bg-white flex-1 max-w-[240px]">
          <option value="">{t('all_assets')}</option>
          {assetList.map((a) => <option key={a.id} value={a.id}>{a.symbol} — {a.name}</option>)}
        </select>
        <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }}
          className="px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none bg-white"/>
        <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }}
          className="px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none bg-white"/>
        {hasFilters && (
          <button onClick={clearFilters}
            className="px-3 py-2 text-[12px] text-gray-400 hover:text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
            Clear
          </button>
        )}
      </div>

      {/* Valuation list */}
      {isLoading ? <LoadingRows /> : valuations.length === 0 ? <EmptyState onAdd={openAdd} noLabel={t('no_valuations')} noDesc={t('no_valuations_desc')} addLabel={t('add_valuation')} /> : (
        <>
          {/* Mobile card view */}
          <div className="md:hidden space-y-2">
            {valuations.map((v) => {
              const asset = assetMap[v.asset_id]
              const account = accountMap[v.account_id ?? '']
              return (
                <div key={v.id} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-gray-900 truncate">
                        {asset?.name ?? '—'}
                      </div>
                      <div className="text-[11px] text-gray-400 font-mono truncate mt-0.5" dir="ltr">
                        {asset?.symbol ?? ''}
                        {account ? ` · ${account.name}` : ''}
                      </div>
                      <div className="text-[11px] text-gray-500 font-mono mt-1" dir="ltr">
                        {formatILS(Number(v.market_value))} {v.currency}
                      </div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <div className="font-mono font-semibold text-emerald-700 text-[15px]" dir="ltr">
                        {v.value_ils != null ? formatILSShort(Number(v.value_ils)) : '—'}
                      </div>
                      <div className="text-[11px] text-gray-400 font-mono mt-0.5" dir="ltr">
                        {formatDate(v.valuation_date)}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-gray-50">
                    <div className="flex items-center gap-1.5">
                      <MethodBadge method={v.valuation_method} />
                      <ConfidenceBadge level={v.confidence_level} />
                    </div>
                    <div className="hidden lg:flex items-center gap-1">
                      <ActionBtn onClick={() => openEdit(v)} icon="edit" title="Edit" />
                      <ActionBtn onClick={() => { setDeleteTarget(v); setDeleteError('') }} icon="delete" title="Delete" danger />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Desktop table view */}
          <div className="hidden md:block bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    {[t('col_date'),t('col_asset'),t('col_account'),t('col_market_value'),t('col_currency'),t('col_fx_rate'),t('col_value_ils'),t('col_method'),t('col_confidence'),''].map((h) => (
                      <th key={h} className="text-left px-4 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {valuations.map((v) => {
                    const asset = assetMap[v.asset_id]
                    const account = accountMap[v.account_id ?? '']
                    return (
                      <tr key={v.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                        <td className="px-4 py-3 font-mono text-[12px] text-gray-600 whitespace-nowrap">
                          {formatDate(v.valuation_date)}
                        </td>
                        <td className="px-4 py-3">
                          {asset ? (
                            <>
                              <div className="font-semibold text-gray-900 truncate max-w-[160px]">{asset.name}</div>
                              <div className="text-[11px] text-gray-400 font-mono mt-0.5" dir="ltr">{asset.symbol}</div>
                            </>
                          ) : <span className="text-gray-300">—</span>}
                        </td>
                        <td className="px-4 py-3 text-[12px] text-gray-500">
                          {account?.name ?? <span className="text-gray-300">—</span>}
                        </td>
                        <td className="px-4 py-3 font-mono font-semibold text-gray-800" dir="ltr">
                          {formatILS(Number(v.market_value))}
                        </td>
                        <td className="px-4 py-3 font-mono text-gray-500" dir="ltr">{v.currency}</td>
                        <td className="px-4 py-3 font-mono text-gray-500 text-[12px]" dir="ltr">
                          {Number(v.fx_rate_to_ils).toFixed(4)}
                        </td>
                        <td className="px-4 py-3 font-mono font-semibold text-emerald-700" dir="ltr">
                          {v.value_ils != null ? formatILS(Number(v.value_ils)) : '—'}
                        </td>
                        <td className="px-4 py-3"><MethodBadge method={v.valuation_method} /></td>
                        <td className="px-4 py-3"><ConfidenceBadge level={v.confidence_level} /></td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1 justify-end">
                            <ActionBtn onClick={() => openEdit(v)} icon="edit" title="Edit" />
                            <ActionBtn onClick={() => { setDeleteTarget(v); setDeleteError('') }} icon="delete" title="Delete" danger />
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-[12px] text-gray-400">
            {t('showing', { from: (page - 1) * PAGE_SIZE + 1, to: Math.min(page * PAGE_SIZE, total), total })}
          </p>
          <div className="flex items-center gap-1">
            <PagBtn onClick={() => setPage(1)} disabled={page === 1} label="«" />
            <PagBtn onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} label="‹" />
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const start = Math.max(1, Math.min(page - 2, totalPages - 4))
              const p = start + i
              return (
                <button key={p} onClick={() => setPage(p)}
                  className={clsx('w-8 h-8 rounded-lg text-[12px] font-medium transition-colors',
                    p === page ? 'bg-[#0d9488] text-white' : 'text-gray-500 hover:bg-gray-100')}>
                  {p}
                </button>
              )
            })}
            <PagBtn onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} label="›" />
            <PagBtn onClick={() => setPage(totalPages)} disabled={page === totalPages} label="»" />
          </div>
        </div>
      )}

      {/* Add / Edit Modal */}
      <Modal open={modalOpen} onClose={closeModal}
        title={editTarget ? t('edit_valuation') : t('add_valuation')}
        width="max-w-xl">
        <div className="space-y-5">

          <FormSection title={t('section_asset_date')}>
            <Field label={t('field_asset')} required error={errors.asset_id}>
              <Select value={form.asset_id}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, asset_id: e.target.value })}
                error={!!errors.asset_id}>
                <option value="">— Select asset —</option>
                {assetList.map((a) => <option key={a.id} value={a.id}>{a.symbol} — {a.name}</option>)}
              </Select>
            </Field>
            <FormGrid>
              <Field label={t('field_date')} required error={errors.valuation_date}>
                <Input type="date" value={form.valuation_date}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, valuation_date: e.target.value })}
                  error={!!errors.valuation_date} />
              </Field>
              <Field label={t('field_account')}>
                <Select value={form.account_id}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, account_id: e.target.value })}>
                  <option value="">— None —</option>
                  {accountsData.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </Select>
              </Field>
            </FormGrid>
          </FormSection>

          <Divider />

          <FormSection title={t('section_value')}>
            <FormGrid>
              <Field label={t('field_market_value')} required error={errors.market_value}>
                <Input type="number" value={form.market_value}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleMarketValueChange(e.target.value)}
                  placeholder="0.00" className="font-mono" error={!!errors.market_value} />
              </Field>
              <Field label={t('field_currency')} required>
                <Select value={form.currency}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, currency: e.target.value })}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </Field>
            </FormGrid>
            <FormGrid>
              <Field label={t('field_fx_rate')} hint={t('field_fx_rate_hint')}>
                <Input type="number" value={form.fx_rate_to_ils}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleFxRateChange(e.target.value)}
                  placeholder="1.0" className="font-mono" />
              </Field>
              <Field label={t('field_value_ils')} hint={t('field_value_ils_hint')}>
                <Input type="number" value={form.value_ils}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, value_ils: e.target.value })}
                  placeholder="Auto" className="font-mono" />
              </Field>
            </FormGrid>
          </FormSection>

          <Divider />

          <FormSection title={t('section_metadata')}>
            <FormGrid>
              <Field label={t('field_method')}>
                <Select value={form.valuation_method}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, valuation_method: e.target.value })}>
                  {METHODS.map((m) => <option key={m} value={m}>{m.replace('_', ' ')}</option>)}
                </Select>
              </Field>
              <Field label={t('field_confidence')}>
                <Select value={form.confidence_level}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, confidence_level: e.target.value })}>
                  {CONFIDENCE.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </Field>
            </FormGrid>
            <FormGrid>
              <Field label={t('field_source')}>
                <Select value={form.source}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, source: e.target.value })}>
                  {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </Field>
              <Field label={t('field_valuation_source')} hint={t('field_valuation_source_hint')}>
                <Input value={form.valuation_source}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, valuation_source: e.target.value })}
                  placeholder="Optional source name" />
              </Field>
            </FormGrid>
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input type="checkbox" checked={form.is_estimated}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, is_estimated: e.target.checked })}
                className="w-4 h-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
              <span className="text-[13px] text-gray-700">{t('field_estimated')}</span>
            </label>
          </FormSection>

          <Divider />

          <FormSection title={t('section_notes')}>
            <Textarea rows={3} value={form.notes} placeholder="Optional notes…"
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setForm({ ...form, notes: e.target.value })} />
          </FormSection>

          <Divider />
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={closeModal}
              className="px-4 py-2 text-[13px] font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
              Cancel
            </button>
            <button onClick={handleSubmit} disabled={isSaving}
              className="px-4 py-2 text-[13px] font-medium bg-[#0d9488] hover:bg-teal-700 text-white rounded-lg transition-colors disabled:opacity-60">
              {isSaving ? 'Saving…' : editTarget ? 'Save changes' : t('add_valuation')}
            </button>
          </div>
        </div>
      </Modal>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title={t('delete_title')}
        message={deleteError || t('delete_message')}
        confirmLabel="Delete" danger
        onConfirm={() => {
          if (!deleteTarget) return
          setDeleteError('')
          deleteMut.mutate(deleteTarget.id, {
            onError: (err: unknown) => {
              const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
              setDeleteError(detail ?? 'Could not delete valuation')
            },
          })
        }}
        onCancel={() => { setDeleteTarget(null); setDeleteError('') }}
      />
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function MethodBadge({ method }: { method: string }) {
  const colors: Record<string, string> = {
    manual: 'bg-gray-100 text-gray-600',
    appraisal: 'bg-blue-50 text-blue-700',
    broker_estimate: 'bg-purple-50 text-purple-700',
    model: 'bg-amber-50 text-amber-700',
  }
  return <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold', colors[method] ?? 'bg-gray-100 text-gray-500')}>{method.replace('_', ' ')}</span>
}

function ConfidenceBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    high: 'bg-emerald-50 text-emerald-700',
    medium: 'bg-amber-50 text-amber-700',
    low: 'bg-rose-50 text-rose-700',
  }
  return <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold', colors[level] ?? 'bg-gray-100 text-gray-500')}>{level}</span>
}

function PagBtn({ onClick, disabled, label }: { onClick: () => void; disabled: boolean; label: string }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={clsx('w-8 h-8 rounded-lg text-[12px] font-medium transition-colors',
        disabled ? 'text-gray-200 cursor-not-allowed' : 'text-gray-500 hover:bg-gray-100')}>
      {label}
    </button>
  )
}

function ActionBtn({ onClick, icon, title, danger }: { onClick: () => void; icon: 'edit' | 'delete'; title: string; danger?: boolean }) {
  return (
    <button onClick={onClick} title={title}
      className={clsx('w-7 h-7 flex items-center justify-center rounded-lg transition-colors',
        danger ? 'text-gray-300 hover:text-rose-500 hover:bg-rose-50' : 'text-gray-300 hover:text-teal-600 hover:bg-teal-50')}>
      {icon === 'edit'
        ? <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 2l2 2-6 6H3V8l6-6z"/></svg>
        : <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M2 4h9M5 4V3h3v1M4 4l.5 6h4l.5-6"/></svg>}
    </button>
  )
}

function LoadingRows() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      {[1,2,3,4,5].map((i) => (
        <div key={i} className="flex gap-4 px-4 py-3.5 border-b border-gray-50 last:border-0 animate-pulse">
          <div className="h-4 bg-gray-100 rounded w-24"/>
          <div className="h-4 bg-gray-100 rounded w-32"/>
          <div className="h-4 bg-gray-100 rounded w-20"/>
          <div className="h-4 bg-gray-100 rounded w-24"/>
        </div>
      ))}
    </div>
  )
}

function EmptyState({ onAdd, noLabel, noDesc, addLabel }: { onAdd: () => void; noLabel: string; noDesc: string; addLabel: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
      <p className="text-[14px] font-medium text-gray-600 mb-1">{noLabel}</p>
      <p className="text-[12px] text-gray-400 mb-4">{noDesc}</p>
      <button onClick={onAdd} className="px-4 py-2 bg-[#0d9488] text-white text-[13px] font-medium rounded-lg hover:bg-teal-700">
        {addLabel}
      </button>
    </div>
  )
}
