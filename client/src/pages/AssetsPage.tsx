import { useState, useMemo, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getAssets, createAsset, updateAsset, deleteAsset } from '../api/portfolio'
import { useCategoryFilter } from '../hooks/usePortfolio'
import type { Asset } from '../types'
import { Modal, ConfirmDialog } from '../components/shared/Modal'
import { MetadataEditor, jsonToPairs, pairsToJson } from '../components/shared/MetadataEditor'
import type { MetaPair } from '../components/shared/MetadataEditor'
import { Field, Input, Select, Textarea, FormGrid, FormSection, Divider } from '../components/shared/Form'
import { formatILS, formatILSShort, formatPct, gainClass, categoryLabel } from '../utils/format'
import { isEnabled } from '../config/features'
import clsx from 'clsx'

const BEHAVIORS = ['MARKET', 'MANUAL', 'FUND', 'CASH_OR_DEBT', 'REAL_ESTATE', 'LOAN']
const CATEGORIES = ['real_estate', 'pension', 'securities', 'alternatives', 'cash', 'crypto', 'mutual_fund', 'etf', 'energy_income']
const CURRENCIES = ['ILS', 'USD', 'EUR', 'GBP']
const PRICING_MODES = ['manual_valuation', 'market_price', 'transaction_based']
const STATUSES = ['active', 'inactive', 'closed', 'pending']
const KNOWN_FIELDS = new Set(['name', 'symbol', 'asset_behavior', 'category', 'asset_type',
  'sub_type', 'status', 'lifecycle_stage', 'exchange', 'currency', 'country', 'sector',
  'current_price', 'pricing_mode', 'is_manual', 'extra_data', 'account_id',
  'portfolio_id', 'id', 'created_at', 'updated_at', 'price_updated_at'])

interface AssetForm {
  name: string
  symbol: string
  asset_behavior: string
  category: string
  asset_type: string
  currency: string
  exchange: string
  country: string
  sector: string
  current_price: string
  pricing_mode: string
  is_manual: boolean
  status: string
}

function emptyForm(): AssetForm {
  return {
    name: '', symbol: '', asset_behavior: 'MANUAL', category: 'securities',
    asset_type: '', currency: 'ILS', exchange: '', country: '',
    sector: '', current_price: '', pricing_mode: 'manual_valuation',
    is_manual: true, status: 'active',
  }
}

function formatQty(n: number | null | undefined): string {
  if (n == null) return '—'
  const isWhole = Math.abs(n - Math.round(n)) < 0.0001
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: isWhole ? 0 : 4,
  }).format(n)
}

export default function AssetsPage() {
  const qc = useQueryClient()
  const categoryFilter = useCategoryFilter()

  const [searchParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterBehavior, setFilterBehavior] = useState('')

  // Apply URL-driven filters on mount (drill-down from dashboard)
  useEffect(() => {
    const cat = searchParams.get('category')
    if (cat) setFilterCategory(cat)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isLoading } = useQuery({
    queryKey: ['assets'],
    queryFn: () => getAssets({ limit: 500 }),
  })

  const assets = data?.items ?? []

  // Client-side filter — chip bar + search + dropdowns
  const filtered = useMemo(() => {
    return assets.filter((a) => {
      // Global category chips (from sidebar/topbar)
      if (categoryFilter.length > 0 && !categoryFilter.includes(a.category ?? '')) return false
      // Local search
      if (search && !a.name.toLowerCase().includes(search.toLowerCase()) &&
          !a.symbol.toLowerCase().includes(search.toLowerCase())) return false
      // Local category dropdown (more specific than chips)
      if (filterCategory && a.category !== filterCategory) return false
      if (filterBehavior && a.asset_behavior !== filterBehavior) return false
      return true
    })
  }, [assets, categoryFilter, search, filterCategory, filterBehavior])

  const createMut = useMutation({
    mutationFn: (payload: Record<string, unknown>) => createAsset(payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['assets'] }); closeModal() },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => updateAsset(id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['assets'] }); closeModal() },
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteAsset(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['assets'] }); setDeleteTarget(null) },
  })

  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Asset | null>(null)
  const [form, setForm] = useState<AssetForm>(emptyForm())
  const [metaPairs, setMetaPairs] = useState<MetaPair[]>([])
  const [deleteTarget, setDeleteTarget] = useState<Asset | null>(null)
  const [deleteError, setDeleteError] = useState('')
  const [importText, setImportText] = useState('')
  const [importError, setImportError] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [showOpeningData, setShowOpeningData] = useState(false)
  const [openingValue, setOpeningValue] = useState('')
  const [openingCost, setOpeningCost] = useState('')
  const [openingDate, setOpeningDate] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  function openAdd() {
    setEditTarget(null); setForm(emptyForm()); setMetaPairs([])
    setErrors({}); setShowImport(false); setShowOpeningData(false)
    setOpeningValue(''); setOpeningCost(''); setOpeningDate('')
    setModalOpen(true)
  }

  function openEdit(asset: Asset) {
    setEditTarget(asset)
    setForm({
      name: asset.name, symbol: asset.symbol,
      asset_behavior: asset.asset_behavior, category: asset.category ?? '',
      asset_type: asset.asset_type ?? '', currency: asset.currency,
      exchange: asset.exchange ?? '', country: asset.country ?? '',
      sector: asset.sector ?? '',
      current_price: asset.current_price?.toString() ?? '',
      pricing_mode: asset.pricing_mode, is_manual: asset.is_manual,
      status: asset.status,
    })
    setMetaPairs(jsonToPairs(asset.extra_data ?? undefined))
    setErrors({}); setShowImport(false); setShowOpeningData(false)
    setModalOpen(true)
  }

  function closeModal() { setModalOpen(false); setEditTarget(null); setImportError('') }

  const { t } = useTranslation('assets')
  const { t: tc } = useTranslation('common')

  function handleImportJson() {
    try {
      const parsed = JSON.parse(importText) as Record<string, unknown>
      const known: Partial<AssetForm> = {}
      const extra: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(parsed)) {
        if (KNOWN_FIELDS.has(k)) (known as Record<string, unknown>)[k] = v
        else extra[k] = v
      }
      setForm((f) => ({ ...f, ...known }))
      setMetaPairs(jsonToPairs(extra))
      setImportError(''); setShowImport(false); setImportText('')
    } catch {
      setImportError(t('invalid_json'))
    }
  }

  function validate() {
    const e: Record<string, string> = {}
    if (!form.name.trim()) e.name = t('error_name_required')
    if (!form.symbol.trim()) e.symbol = t('error_symbol_required')
    if (!form.asset_behavior) e.asset_behavior = t('error_behavior_required')
    setErrors(e)
    return Object.keys(e).length === 0
  }

  function handleSubmit() {
    if (!validate()) return
    const metadata = pairsToJson(metaPairs)
    const payload: Record<string, unknown> = {
      ...form,
      current_price: form.current_price ? parseFloat(form.current_price) : null,
      ...(Object.keys(metadata).length ? { extra_data: metadata } : {}),
    }
    // Opening data — only on create
    if (!editTarget && isEnabled('asset_opening_data') && showOpeningData && openingValue) {
      payload._opening_value = parseFloat(openingValue)
      payload._opening_cost = openingCost ? parseFloat(openingCost) : parseFloat(openingValue)
      payload._opening_date = openingDate || new Date().toISOString().split('T')[0]
    }
    if (editTarget) {
      updateMut.mutate({ id: editTarget.id, payload })
    } else {
      createMut.mutate(payload)
    }
  }

  const isSaving = createMut.isPending || updateMut.isPending

  return (
    <div className="p-6 pb-20 md:pb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-[16px] font-semibold text-gray-900">{t('title')}</h2>
          <p className="text-[12px] text-gray-400 mt-0.5">
            {filtered.length !== assets.length
              ? t('count_of', { filtered: filtered.length, total: assets.length })
              : t('count', { count: filtered.length })}
          </p>
        </div>
        <button onClick={openAdd}
          className="flex items-center gap-2 px-4 py-2 bg-[#0d9488] hover:bg-teal-700 text-white text-[13px] font-medium rounded-lg transition-colors">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round"><path d="M6 1v10M1 6h10"/></svg>
          {t('new_asset')}
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="6" cy="6" r="4"/><path d="M10 10l3 3"/></svg>
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder={t('search_placeholder')}
            className="w-full pl-8 pr-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 bg-white" />
        </div>
        <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}
          className="px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 bg-white">
          <option value="">{t('all_categories')}</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{categoryLabel(c, tc)}</option>)}
        </select>
        <select value={filterBehavior} onChange={(e) => setFilterBehavior(e.target.value)}
          className="px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 bg-white">
          <option value="">{t('all_behaviors')}</option>
          {BEHAVIORS.map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
        {(search || filterCategory || filterBehavior) && (
          <button onClick={() => { setSearch(''); setFilterCategory(''); setFilterBehavior('') }}
            className="px-3 py-2 text-[12px] text-gray-400 hover:text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
            Clear
          </button>
        )}
      </div>

      {/* Asset list */}
      {isLoading ? <LoadingRows /> : filtered.length === 0 ? <EmptyState onAdd={openAdd} /> : (
        <>
          {/* Mobile card view */}
          <div className="md:hidden space-y-2">
            {filtered.map((asset) => {
              const isMarket = asset.asset_behavior === 'MARKET'
              const retPct = asset.snapshot_total_return_pct != null
                ? asset.snapshot_total_return_pct * 100
                : null
              return (
                <div key={asset.id} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0 pr-3">
                      <div className="font-semibold text-gray-900 truncate">{asset.name}</div>
                      {isMarket ? (
                        <div className="text-[11px] font-mono text-gray-400 mt-1" dir="ltr">
                          {formatQty(asset.net_quantity)} shares
                          {asset.current_price != null && (
                            <> · ${asset.current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</>
                          )}
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-[11px] font-mono text-gray-400" dir="ltr">{asset.symbol}</span>
                          <CategoryBadge cat={asset.category ?? ''} />
                        </div>
                      )}
                    </div>
                    <div className="text-right flex-shrink-0">
                      <div className="font-mono font-semibold text-gray-800 text-[14px]" dir="ltr">
                        {asset.snapshot_current_value != null ? formatILSShort(asset.snapshot_current_value) : '—'}
                      </div>
                      <div className={clsx('font-mono text-[12px] mt-0.5 font-semibold', gainClass(retPct))} dir="ltr">
                        {retPct != null ? formatPct(retPct) : '—'}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-gray-50">
                    <BehaviorBadge behavior={asset.asset_behavior} />
                    <div className="flex items-center gap-1">
                      <ActionBtn onClick={() => openEdit(asset)} icon="edit" title="Edit" />
                      <ActionBtn
                        onClick={() => { setDeleteTarget(asset); setDeleteError('') }}
                        icon="delete" title="Delete" danger />
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
                    {[t('col_asset'), 'Qty', 'Price', t('col_current_value'), 'Invested', t('col_return'), t('col_behavior'), ''].map((h) => (
                      <th key={h} className="text-left px-4 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((asset) => {
                    const isMarket = asset.asset_behavior === 'MARKET'
                    const retPct = asset.snapshot_total_return_pct != null
                      ? asset.snapshot_total_return_pct * 100
                      : null
                    return (
                      <tr key={asset.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                        <td className="px-4 py-3">
                          <div className="font-semibold text-gray-900">{asset.name}</div>
                          <div className="text-[11px] text-gray-400 font-mono mt-0.5" dir="ltr">{asset.symbol}</div>
                        </td>
                        <td className="px-4 py-3 font-mono text-gray-700" dir="ltr">
                          {isMarket ? formatQty(asset.net_quantity) : '—'}
                        </td>
                        <td className="px-4 py-3 font-mono text-gray-700">
                          {isMarket && asset.current_price != null ? (
                            <span dir="ltr">
                              ${asset.current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                            </span>
                          ) : '—'}
                        </td>
                        <td className="px-4 py-3 font-mono font-semibold text-gray-800" dir="ltr">
                          {asset.snapshot_current_value != null ? formatILS(asset.snapshot_current_value) : '—'}
                        </td>
                        <td className="px-4 py-3 font-mono text-gray-600" dir="ltr">
                          {asset.snapshot_invested_capital != null ? formatILS(asset.snapshot_invested_capital) : '—'}
                        </td>
                        <td className={clsx('px-4 py-3 font-mono font-semibold', gainClass(retPct))} dir="ltr">
                          {retPct != null ? formatPct(retPct) : '—'}
                        </td>
                        <td className="px-4 py-3"><BehaviorBadge behavior={asset.asset_behavior} /></td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1 justify-end">
                            <ActionBtn onClick={() => openEdit(asset)} icon="edit" title="Edit" />
                            <ActionBtn
                              onClick={() => { setDeleteTarget(asset); setDeleteError('') }}
                              icon="delete" title="Delete" danger />
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

      {/* Add / Edit Modal */}
      <Modal open={modalOpen} onClose={closeModal}
        title={editTarget ? t('edit_asset', { name: editTarget.name }) : t('new_asset')}
        width="max-w-2xl">
        <div className="space-y-5">

          {/* JSON Import */}
          {isEnabled('asset_json_import') && (
            <div>
              <button type="button" onClick={() => setShowImport((v) => !v)}
                className="flex items-center gap-1.5 text-[12px] text-teal-600 hover:text-teal-700 font-medium">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M2 9v2h9V9M6.5 1v7M4 5l2.5 3L9 5"/></svg>
                {t('import_from_json')}
              </button>
              {showImport && (
                <div className="mt-2 space-y-2">
                  <Textarea rows={4} placeholder={'{\n  "name": "Apple Inc.",\n  "symbol": "AAPL",\n  "category": "securities"\n}'}
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
          )}

          <Divider />

          {/* Identity */}
          <FormSection title={t('section_identity')}>
            <FormGrid>
              <Field label={t('field_name')} required error={errors.name}>
                <Input value={form.name}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. Apple Inc." error={!!errors.name} />
              </Field>
              <Field label={t('field_symbol')} required error={errors.symbol} hint={t('field_symbol_hint')}>
                <Input value={form.symbol}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
                  placeholder="e.g. AAPL" error={!!errors.symbol} className="font-mono" />
              </Field>
            </FormGrid>
            <FormGrid>
              <Field label={t('field_category')}>
                <Select value={form.category}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, category: e.target.value })}>
                  <option value="">— none —</option>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{categoryLabel(c, tc)}</option>)}
                </Select>
              </Field>
              <Field label={t('field_asset_type')}>
                <Input value={form.asset_type}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, asset_type: e.target.value })}
                  placeholder={t('field_asset_type_placeholder')} />
              </Field>
            </FormGrid>
          </FormSection>

          <Divider />

          {/* Behavior & Pricing */}
          <FormSection title={t('section_behavior')}>
            <FormGrid>
              <Field label={t('field_behavior')} required error={errors.asset_behavior}>
                <Select value={form.asset_behavior}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, asset_behavior: e.target.value })}
                  error={!!errors.asset_behavior}>
                  {BEHAVIORS.map((b) => <option key={b} value={b}>{b}</option>)}
                </Select>
              </Field>
              <Field label={t('field_pricing_mode')}>
                <Select value={form.pricing_mode}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, pricing_mode: e.target.value })}>
                  {PRICING_MODES.map((p) => <option key={p} value={p}>{p.replace(/_/g, ' ')}</option>)}
                </Select>
              </Field>
            </FormGrid>
            <FormGrid>
              <Field label={t('field_currency')} required>
                <Select value={form.currency}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, currency: e.target.value })}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </Field>
              <Field label={t('field_current_price')} hint={t('field_current_price_hint')}>
                <Input type="number" value={form.current_price}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, current_price: e.target.value })}
                  placeholder="0.00" className="font-mono" />
              </Field>
            </FormGrid>
          </FormSection>

          <Divider />

          {/* Market data */}
          <FormSection title={t('section_market_data')}>
            <FormGrid>
              <Field label={t('field_exchange')}>
                <Input value={form.exchange}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, exchange: e.target.value })}
                  placeholder={t('field_exchange_placeholder')} />
              </Field>
              <Field label={t('field_country')}>
                <Input value={form.country}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, country: e.target.value })}
                  placeholder={t('field_country_placeholder')} />
              </Field>
            </FormGrid>
            <Field label={t('field_sector')}>
              <Input value={form.sector}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, sector: e.target.value })}
                placeholder={t('field_sector_placeholder')} />
            </Field>
          </FormSection>

          <Divider />

          {/* Status */}
          <FormSection title={t('section_status')}>
            <FormGrid>
              <Field label={t('field_status')}>
                <Select value={form.status}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, status: e.target.value })}>
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </Field>
            </FormGrid>
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input type="checkbox" checked={form.is_manual}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, is_manual: e.target.checked })}
                className="w-4 h-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
              <span className="text-[13px] text-gray-700">{t('field_manual')}</span>
            </label>
          </FormSection>

          {/* Opening data — only on create */}
          {!editTarget && isEnabled('asset_opening_data') && (
            <>
              <Divider />
              <div>
                <button type="button"
                  onClick={() => setShowOpeningData((v) => !v)}
                  className="flex items-center gap-2 text-[13px] font-medium text-gray-600 hover:text-teal-600 transition-colors">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
                    style={{ transform: showOpeningData ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s' }}>
                    <path d="M5 3l4 4-4 4"/>
                  </svg>
                  {t('opening_data')}
                </button>
                <p className="text-[11px] text-gray-400 mt-0.5 ml-5">
                  {t('opening_data_hint')}
                </p>
                {showOpeningData && (
                  <div className="mt-3 ml-5 space-y-3">
                    <FormGrid>
                      <Field label={t('field_opening_value')} hint={t('field_opening_value_hint')}>
                        <Input type="number" value={openingValue}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOpeningValue(e.target.value)}
                          placeholder="120,000" className="font-mono" />
                      </Field>
                      <Field label={t('field_opening_cost')} hint={t('field_opening_cost_hint')}>
                        <Input type="number" value={openingCost}
                          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOpeningCost(e.target.value)}
                          placeholder="100,000" className="font-mono" />
                      </Field>
                    </FormGrid>
                    <Field label={t('field_opening_date')} hint={t('field_opening_date_hint')}>
                      <Input type="date" value={openingDate}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOpeningDate(e.target.value)} />
                    </Field>
                  </div>
                )}
              </div>
            </>
          )}

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
                {isSaving ? 'Saving…' : editTarget ? 'Save changes' : t('add_asset')}
              </button>
            </div>
          </div>
        </div>
      </Modal>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title={deleteTarget ? t('delete_title', { name: deleteTarget.name }) : ''}
        message={deleteError || t('delete_message')}
        confirmLabel="Delete" danger
        onConfirm={() => {
          if (!deleteTarget) return
          setDeleteError('')
          deleteMut.mutate(deleteTarget.id, {
            onError: (err: unknown) => {
              const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
              setDeleteError(detail ?? t('cannot_delete'))
            },
          })
        }}
        onCancel={() => { setDeleteTarget(null); setDeleteError('') }}
      />
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

const CAT_COLORS: Record<string, string> = {
  real_estate: 'bg-blue-50 text-blue-700', pension: 'bg-purple-50 text-purple-700',
  securities: 'bg-emerald-50 text-emerald-700', alternatives: 'bg-amber-50 text-amber-700',
  cash: 'bg-gray-100 text-gray-500', crypto: 'bg-orange-50 text-orange-700',
  etf: 'bg-lime-50 text-lime-700', mutual_fund: 'bg-cyan-50 text-cyan-700',
  energy_income: 'bg-red-50 text-red-700',
}

const BEH_COLORS: Record<string, string> = {
  MARKET: 'bg-blue-50 text-blue-700', MANUAL: 'bg-gray-100 text-gray-600',
  FUND: 'bg-purple-50 text-purple-700', CASH_OR_DEBT: 'bg-teal-50 text-teal-700',
  REAL_ESTATE: 'bg-amber-50 text-amber-700', LOAN: 'bg-rose-50 text-rose-700',
}

function CategoryBadge({ cat }: { cat: string }) {
  const { t } = useTranslation('common')
  return <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold', CAT_COLORS[cat] ?? 'bg-gray-100 text-gray-500')}>{categoryLabel(cat, t) || '—'}</span>
}
function BehaviorBadge({ behavior }: { behavior: string }) {
  return <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold font-mono', BEH_COLORS[behavior] ?? 'bg-gray-100 text-gray-500')}>{behavior}</span>
}
function StatusBadge({ status }: { status: string }) {
  return <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold', status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-400')}>{status}</span>
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
          <div className="h-4 bg-gray-100 rounded w-1/3"/><div className="h-4 bg-gray-100 rounded w-1/6"/>
          <div className="h-4 bg-gray-100 rounded w-1/6"/><div className="h-4 bg-gray-100 rounded w-1/8"/>
        </div>
      ))}
    </div>
  )
}
function EmptyState({ onAdd }: { onAdd: () => void }) {
  const { t } = useTranslation('assets')
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
      <p className="text-[14px] font-medium text-gray-600 mb-1">{t('no_assets_title')}</p>
      <p className="text-[12px] text-gray-400 mb-4">{t('no_assets_sub')}</p>
      <button onClick={onAdd} className="px-4 py-2 bg-[#0d9488] text-white text-[13px] font-medium rounded-lg hover:bg-teal-700">{t('new_asset')}</button>
    </div>
  )
}
