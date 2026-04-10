import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getTransactions, createTransaction, updateTransaction, deleteTransaction, getAssets, getAccounts } from '../api/portfolio'
import { useCategoryFilter } from '../hooks/usePortfolio'
import type { Transaction } from '../types'
import { Modal, ConfirmDialog } from '../components/shared/Modal'
import { Field, Input, Select, Textarea, FormGrid, FormSection, Divider } from '../components/shared/Form'
import { formatILS, formatDate, gainClass } from '../utils/format'
import clsx from 'clsx'

// ─── Enum values from backend ─────────────────────────────────────────────────
const TXN_TYPES = ['buy','sell','deposit','withdrawal','dividend','income','expense',
  'allocation','vest','bonus','loan_in','loan_payment','interest_payment',
  'external_deposit','external_withdrawal','swap_in','swap_out']

const ECONOMIC_TYPES = ['BUY','SELL','DEPOSIT','WITHDRAWAL','INCOME','EXPENSE',
  'FINANCING_INFLOW','FINANCING_OUTFLOW','INVESTMENT_INFLOW','INVESTMENT_OUTFLOW','REVALUATION']

const DOMAINS = ['real_estate','securities','crypto','pension','solar','whisky','btb','general']
const STATUSES = ['confirmed','pending','cancelled']
const CURRENCIES = ['ILS','USD','EUR','GBP']

interface TxnForm {
  transaction_date: string
  effective_date: string
  type: string
  economic_type: string
  domain: string
  currency: string
  total_amount: string
  cashflow_amount: string
  quantity: string
  price_per_unit: string
  units_delta: string
  fees: string
  tax: string
  is_internal_transfer: boolean
  status: string
  notes: string
  external_reference_id: string
  asset_id: string
  account_id: string
}

function emptyForm(): TxnForm {
  return {
    transaction_date: new Date().toISOString().split('T')[0],
    effective_date: '', type: 'buy', economic_type: 'BUY',
    domain: '', currency: 'ILS', total_amount: '', cashflow_amount: '',
    quantity: '', price_per_unit: '', units_delta: '0',
    fees: '0', tax: '0', is_internal_transfer: false,
    status: 'confirmed', notes: '', external_reference_id: '',
    asset_id: '', account_id: '',
  }
}

// Positive economic types (inflows)
const INFLOWS = new Set(['SELL','DEPOSIT','INCOME','FINANCING_INFLOW','INVESTMENT_INFLOW'])

export default function TransactionsPage() {
  const qc = useQueryClient()

  const categoryFilter = useCategoryFilter()

  // Filters
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState('')
  const [filterEconomic, setFilterEconomic] = useState('')
  const [filterAsset, setFilterAsset] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  // Pagination
  const PAGE_SIZE = 50
  const [page, setPage] = useState(1)

  const { data: txnData = [], isLoading } = useQuery({
    queryKey: ['transactions', { filterType, filterEconomic, filterAsset, dateFrom, dateTo }],
    queryFn: () => getTransactions({
      limit: 500,
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

  // Build lookup maps
  const assetMap = useMemo(() =>
    Object.fromEntries(assetList.map((a) => [a.id, a])), [assetList])
  const accountMap = useMemo(() =>
    Object.fromEntries(accountsData.map((a) => [a.id, a])), [accountsData])

  // Client-side filter — category chips + search + type filters
  const filtered = useMemo(() => {
    return txnData.filter((t) => {
      // Global category chips — join through asset
      if (categoryFilter.length > 0) {
        const asset = assetMap[t.asset_id ?? '']
        if (!asset || !categoryFilter.includes(asset.category ?? '')) return false
      }
      if (filterType && t.type !== filterType) return false
      if (filterEconomic && t.economic_type !== filterEconomic) return false
      if (search) {
        const asset = assetMap[t.asset_id ?? '']
        const term = search.toLowerCase()
        if (!asset?.symbol.toLowerCase().includes(term) &&
            !asset?.name.toLowerCase().includes(term) &&
            !(t.external_reference_id ?? '').toLowerCase().includes(term)) return false
      }
      return true
    })
  }, [txnData, categoryFilter, filterType, filterEconomic, search, assetMap])

  // Paginated slice
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const transactions = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  const createMut = useMutation({
    mutationFn: (p: Record<string, unknown>) => createTransaction(p),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['transactions'] }); closeModal() },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      updateTransaction(id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['transactions'] }); closeModal() },
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteTransaction(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['transactions'] }); setDeleteTarget(null) },
  })

  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Transaction | null>(null)
  const [form, setForm] = useState<TxnForm>(emptyForm())
  const [deleteTarget, setDeleteTarget] = useState<Transaction | null>(null)
  const [deleteError, setDeleteError] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})

  function openAdd() {
    setEditTarget(null); setForm(emptyForm()); setErrors({}); setModalOpen(true)
  }

  function openEdit(t: Transaction) {
    setEditTarget(t)
    setForm({
      transaction_date: t.transaction_date ?? '',
      effective_date: t.effective_date ?? '',
      type: t.type, economic_type: t.economic_type ?? '',
      domain: t.domain ?? '', currency: t.currency,
      total_amount: t.total_amount?.toString() ?? '',
      cashflow_amount: t.cashflow_amount?.toString() ?? '',
      quantity: t.quantity?.toString() ?? '',
      price_per_unit: t.price_per_unit?.toString() ?? '',
      units_delta: t.units_delta?.toString() ?? '0',
      fees: t.fees?.toString() ?? '0',
      tax: t.tax?.toString() ?? '0',
      is_internal_transfer: t.is_internal_transfer ?? false,
      status: t.status, notes: t.notes ?? '',
      external_reference_id: t.external_reference_id ?? '',
      asset_id: t.asset_id ?? '', account_id: t.account_id ?? '',
    })
    setErrors({}); setModalOpen(true)
  }

  function closeModal() { setModalOpen(false); setEditTarget(null) }

  function validate() {
    const e: Record<string, string> = {}
    if (!form.transaction_date) e.transaction_date = 'Date is required'
    if (!form.type) e.type = 'Type is required'
    if (!form.currency) e.currency = 'Currency is required'
    if (!form.total_amount && !form.cashflow_amount) e.total_amount = 'Amount or cashflow amount required'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  function toDecimal(v: string) { return v ? parseFloat(v) : null }

  function handleSubmit() {
    if (!validate()) return
    const payload: Record<string, unknown> = {
      transaction_date: form.transaction_date,
      type: form.type,
      currency: form.currency,
      status: form.status,
      fees: parseFloat(form.fees || '0'),
      tax: parseFloat(form.tax || '0'),
      units_delta: parseFloat(form.units_delta || '0'),
      is_internal_transfer: form.is_internal_transfer,
      ...(form.effective_date ? { effective_date: form.effective_date } : {}),
      ...(form.economic_type ? { economic_type: form.economic_type } : {}),
      ...(form.domain ? { domain: form.domain } : {}),
      ...(form.notes ? { notes: form.notes } : {}),
      ...(form.external_reference_id ? { external_reference_id: form.external_reference_id } : {}),
      ...(form.asset_id ? { asset_id: form.asset_id } : {}),
      ...(form.account_id ? { account_id: form.account_id } : {}),
      total_amount: toDecimal(form.total_amount),
      cashflow_amount: toDecimal(form.cashflow_amount),
      quantity: toDecimal(form.quantity),
      price_per_unit: toDecimal(form.price_per_unit),
    }
    if (editTarget) updateMut.mutate({ id: editTarget.id, payload })
    else createMut.mutate(payload)
  }

  const isSaving = createMut.isPending || updateMut.isPending

  const clearFilters = () => {
    setSearch(''); setFilterType(''); setFilterEconomic('')
    setFilterAsset(''); setDateFrom(''); setDateTo('')
    setPage(1)
  }
  const hasFilters = search || filterType || filterEconomic || filterAsset || dateFrom || dateTo

  return (
    <div className="p-6 pb-20 md:pb-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-[16px] font-semibold text-gray-900">Transactions</h2>
          <p className="text-[12px] text-gray-400 mt-0.5">
            {filtered.length}{filtered.length !== txnData.length ? ` of ${txnData.length}` : ''} transactions
            {totalPages > 1 && ` · page ${safePage} of ${totalPages}`}
          </p>
        </div>
        <button onClick={openAdd}
          className="flex items-center gap-2 px-4 py-2 bg-[#0d9488] hover:bg-teal-700 text-white text-[13px] font-medium rounded-lg transition-colors">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round"><path d="M6 1v10M1 6h10"/></svg>
          Add transaction
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4 flex-wrap">
        <div className="relative min-w-[180px] flex-1">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-300" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="6" cy="6" r="4"/><path d="M10 10l3 3"/></svg>
          <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            placeholder="Search symbol or ref…"
            className="w-full pl-8 pr-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 bg-white"/>
        </div>
        <select value={filterType} onChange={(e) => { setFilterType(e.target.value); setPage(1) }}
          className="px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none bg-white">
          <option value="">All types</option>
          {TXN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={filterEconomic} onChange={(e) => { setFilterEconomic(e.target.value); setPage(1) }}
          className="px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none bg-white">
          <option value="">All economic types</option>
          {ECONOMIC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={filterAsset} onChange={(e) => { setFilterAsset(e.target.value); setPage(1) }}
          className="px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none bg-white max-w-[180px]">
          <option value="">All assets</option>
          {assetList.map((a) => <option key={a.id} value={a.id}>{a.symbol}</option>)}
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

      {/* Table */}
      {isLoading ? <LoadingRows /> : transactions.length === 0 ? <EmptyState onAdd={openAdd} hasFilters={!!hasFilters} /> : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {['Date','Asset','Account','Type','Economic type','Amount','Currency','Cashflow','Status',''].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-[11px] font-semibold text-gray-400 uppercase tracking-wide whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => {
                  const asset = assetMap[t.asset_id ?? '']
                  const account = accountMap[t.account_id ?? '']
                  const isInflow = INFLOWS.has(t.economic_type ?? '')
                  return (
                    <tr key={t.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap font-mono text-[12px]">
                        {formatDate(t.transaction_date)}
                      </td>
                      <td className="px-4 py-3">
                        {asset ? (
                          <>
                            <div className="font-semibold text-gray-900">{asset.symbol}</div>
                            <div className="text-[11px] text-gray-400 truncate max-w-[120px]">{asset.name}</div>
                          </>
                        ) : <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-4 py-3 text-gray-600 text-[12px]">
                        {account?.name ?? <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-4 py-3"><TypeBadge type={t.type} /></td>
                      <td className="px-4 py-3">
                        {t.economic_type
                          ? <EconomicBadge type={t.economic_type} positive={isInflow} />
                          : <span className="text-gray-300">—</span>}
                      </td>
                      <td className={clsx('px-4 py-3 font-mono font-semibold text-[12px]', isInflow ? 'text-emerald-600' : 'text-gray-800')}>
                        {t.total_amount != null ? `${isInflow ? '+' : ''}${formatILS(Number(t.total_amount))}` : '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-gray-500 text-[12px]">{t.currency}</td>
                      <td className={clsx('px-4 py-3 font-mono text-[12px]', gainClass(t.cashflow_amount != null ? (isInflow ? 1 : -1) : null))}>
                        {t.cashflow_amount != null ? formatILS(Number(t.cashflow_amount)) : '—'}
                      </td>
                      <td className="px-4 py-3"><StatusBadge status={t.status} /></td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1 justify-end">
                          <ActionBtn onClick={() => openEdit(t)} icon="edit" title="Edit" />
                          <ActionBtn onClick={() => { setDeleteTarget(t); setDeleteError('') }} icon="delete" title="Delete" danger />
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-[12px] text-gray-400">
            Showing {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, filtered.length)} of {filtered.length}
          </p>
          <div className="flex items-center gap-1">
            <PagBtn onClick={() => setPage(1)} disabled={safePage === 1} label="«" />
            <PagBtn onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage === 1} label="‹" />
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const start = Math.max(1, Math.min(safePage - 2, totalPages - 4))
              const p = start + i
              return (
                <button key={p} onClick={() => setPage(p)}
                  className={clsx('w-8 h-8 rounded-lg text-[12px] font-medium transition-colors',
                    p === safePage
                      ? 'bg-[#0d9488] text-white'
                      : 'text-gray-500 hover:bg-gray-100')}>
                  {p}
                </button>
              )
            })}
            <PagBtn onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={safePage === totalPages} label="›" />
            <PagBtn onClick={() => setPage(totalPages)} disabled={safePage === totalPages} label="»" />
          </div>
        </div>
      )}
      <Modal open={modalOpen} onClose={closeModal}
        title={editTarget ? 'Edit transaction' : 'Add transaction'}
        width="max-w-2xl">
        <div className="space-y-5">

          <FormSection title="Core details">
            <FormGrid>
              <Field label="Type" required error={errors.type}>
                <Select value={form.type}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, type: e.target.value })}
                  error={!!errors.type}>
                  {TXN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </Select>
              </Field>
              <Field label="Date" required error={errors.transaction_date}>
                <Input type="date" value={form.transaction_date}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, transaction_date: e.target.value })}
                  error={!!errors.transaction_date} />
              </Field>
            </FormGrid>
            <FormGrid>
              <Field label="Asset">
                <Select value={form.asset_id}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, asset_id: e.target.value })}>
                  <option value="">— None —</option>
                  {assetList.map((a) => <option key={a.id} value={a.id}>{a.symbol} — {a.name}</option>)}
                </Select>
              </Field>
              <Field label="Account">
                <Select value={form.account_id}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, account_id: e.target.value })}>
                  <option value="">— None —</option>
                  {accountsData.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </Select>
              </Field>
            </FormGrid>
            <Field label="Effective date" hint="If different from transaction date">
              <Input type="date" value={form.effective_date}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, effective_date: e.target.value })} />
            </Field>
          </FormSection>

          <Divider />

          <FormSection title="Amounts">
            <FormGrid>
              <Field label="Currency" required>
                <Select value={form.currency}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, currency: e.target.value })}>
                  {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </Field>
              <Field label="Total amount" error={errors.total_amount} hint="Required if no cashflow amount">
                <Input type="number" value={form.total_amount}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, total_amount: e.target.value })}
                  placeholder="0.00" className="font-mono" error={!!errors.total_amount} />
              </Field>
            </FormGrid>
            <FormGrid>
              <Field label="Quantity">
                <Input type="number" value={form.quantity}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, quantity: e.target.value })}
                  placeholder="0" className="font-mono" />
              </Field>
              <Field label="Price per unit">
                <Input type="number" value={form.price_per_unit}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, price_per_unit: e.target.value })}
                  placeholder="0.00" className="font-mono" />
              </Field>
            </FormGrid>
            <FormGrid>
              <Field label="Fees">
                <Input type="number" value={form.fees}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, fees: e.target.value })}
                  placeholder="0" className="font-mono" />
              </Field>
              <Field label="Tax">
                <Input type="number" value={form.tax}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, tax: e.target.value })}
                  placeholder="0" className="font-mono" />
              </Field>
            </FormGrid>
          </FormSection>

          <Divider />

          <FormSection title="Normalized fields">
            <FormGrid>
              <Field label="Economic type" hint="Critical for XIRR calculation">
                <Select value={form.economic_type}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, economic_type: e.target.value })}>
                  <option value="">— Not set —</option>
                  {ECONOMIC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </Select>
              </Field>
              <Field label="Status">
                <Select value={form.status}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, status: e.target.value })}>
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </Field>
            </FormGrid>
            <FormGrid>
              <Field label="Domain">
                <Select value={form.domain}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setForm({ ...form, domain: e.target.value })}>
                  <option value="">— Not set —</option>
                  {DOMAINS.map((d) => <option key={d} value={d}>{d.replace('_', ' ')}</option>)}
                </Select>
              </Field>
              <Field label="Cashflow amount" hint="Normalized cashflow for XIRR">
                <Input type="number" value={form.cashflow_amount}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, cashflow_amount: e.target.value })}
                  placeholder="0.00" className="font-mono" />
              </Field>
            </FormGrid>
            <FormGrid>
              <Field label="Units delta (Δ)" hint="Change in units held">
                <Input type="number" value={form.units_delta}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, units_delta: e.target.value })}
                  placeholder="0" className="font-mono" />
              </Field>
              <Field label="External reference ID">
                <Input value={form.external_reference_id}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, external_reference_id: e.target.value })}
                  placeholder="e.g. broker ref number" className="font-mono text-[12px]" />
              </Field>
            </FormGrid>
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input type="checkbox" checked={form.is_internal_transfer}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, is_internal_transfer: e.target.checked })}
                className="w-4 h-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
              <span className="text-[13px] text-gray-700">Internal transfer (between accounts)</span>
            </label>
          </FormSection>

          <Divider />

          <FormSection title="Notes">
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
              {isSaving ? 'Saving…' : editTarget ? 'Save changes' : 'Add transaction'}
            </button>
          </div>
        </div>
      </Modal>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete transaction?"
        message={deleteError || 'This cannot be undone.'}
        confirmLabel="Delete" danger
        onConfirm={() => {
          if (!deleteTarget) return
          setDeleteError('')
          deleteMut.mutate(deleteTarget.id, {
            onError: (err: unknown) => {
              const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
              setDeleteError(detail ?? 'Could not delete transaction')
            },
          })
        }}
        onCancel={() => { setDeleteTarget(null); setDeleteError('') }}
      />
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  buy: 'bg-blue-50 text-blue-700', sell: 'bg-emerald-50 text-emerald-700',
  income: 'bg-green-50 text-green-700', dividend: 'bg-green-50 text-green-700',
  expense: 'bg-rose-50 text-rose-700', deposit: 'bg-teal-50 text-teal-700',
  withdrawal: 'bg-orange-50 text-orange-700',
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold',
      TYPE_COLORS[type] ?? 'bg-gray-100 text-gray-500')}>
      {type}
    </span>
  )
}

function EconomicBadge({ type, positive }: { type: string; positive: boolean }) {
  return (
    <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold font-mono',
      positive ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700')}>
      {type}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    confirmed: 'bg-emerald-50 text-emerald-700',
    pending: 'bg-amber-50 text-amber-700',
    cancelled: 'bg-gray-100 text-gray-400',
  }
  return (
    <span className={clsx('text-[11px] px-2 py-0.5 rounded font-semibold',
      colors[status] ?? 'bg-gray-100 text-gray-500')}>
      {status}
    </span>
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

function PagBtn({ onClick, disabled, label }: { onClick: () => void; disabled: boolean; label: string }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={clsx('w-8 h-8 rounded-lg text-[12px] font-medium transition-colors',
        disabled ? 'text-gray-200 cursor-not-allowed' : 'text-gray-500 hover:bg-gray-100')}>
      {label}
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
          <div className="h-4 bg-gray-100 rounded w-28"/>
        </div>
      ))}
    </div>
  )
}

function EmptyState({ onAdd, hasFilters }: { onAdd: () => void; hasFilters: boolean }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
      <p className="text-[14px] font-medium text-gray-600 mb-1">
        {hasFilters ? 'No transactions match your filters' : 'No transactions yet'}
      </p>
      {!hasFilters && (
        <button onClick={onAdd} className="mt-4 px-4 py-2 bg-[#0d9488] text-white text-[13px] font-medium rounded-lg hover:bg-teal-700">
          Add transaction
        </button>
      )}
    </div>
  )
}
