import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  getBudgetCategories, createBudgetPlan, updateBudgetPlan,
  generatePlansFromHistory, importPlansFromYear,
  createBudgetCategory, updateBudgetCategory, deleteBudgetCategory,
} from '../api/portfolio'
import { ConfirmDialog } from '../components/shared/Modal'
import { useAppStore } from '../store'
import type { BudgetCategory, BudgetPlan } from '../types'
import clsx from 'clsx'

const TYPE_COLORS: Record<string, string> = {
  income: 'text-emerald-600 bg-emerald-50',
  expense: 'text-red-500 bg-red-50',
  saving: 'text-purple-600 bg-purple-50',
  investment: 'text-blue-600 bg-blue-50',
}

const TYPE_ORDER = ['income', 'expense', 'saving', 'investment'] as const

function fmtILS(n: number | null | undefined) {
  if (n == null) return '–'
  return new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS', maximumFractionDigits: 0 }).format(n)
}

export default function BudgetManagementPage() {
  const { t } = useTranslation('budget')
  const { t: tc } = useTranslation('common')
  const { activeBudgetYear, setActiveBudgetYear } = useAppStore()
  const qc = useQueryClient()

  const [managementTab, setManagementTab] = useState<'plans' | 'categories'>('plans')
  const [selectedCatId, setSelectedCatId] = useState<string | null>(null)
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set(['expense', 'income', 'saving']))

  const { data: categories = [], isLoading, isError, error } = useQuery({
    queryKey: ['budget-categories', activeBudgetYear],
    queryFn: async () => {
      console.log('[BudgetManage] fetching categories, year=', activeBudgetYear)
      const data = await getBudgetCategories(activeBudgetYear)
      console.log('[BudgetManage] categories response:', data?.length, 'items', data)
      return data
    },
  })

  // Build planMap from embedded plan in each category
  const planMap: Record<string, BudgetPlan> = {}
  const walkForPlans = (cats: BudgetCategory[]) => {
    for (const cat of cats) {
      if (cat.plan) planMap[cat.id] = cat.plan as BudgetPlan
      walkForPlans(cat.children ?? [])
    }
  }
  walkForPlans(categories)

  if (isError) {
    console.error('[BudgetManage] categories query failed:', error)
  }

  const selectedCat = selectedCatId ? findCat(categories, selectedCatId) : null

  const generateMutation = useMutation({
    mutationFn: () => generatePlansFromHistory(activeBudgetYear, 6),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-categories', activeBudgetYear] }),
  })

  const importMutation = useMutation({
    mutationFn: () => importPlansFromYear(activeBudgetYear - 1, activeBudgetYear),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-categories', activeBudgetYear] }),
  })

  function toggleType(type: string) {
    setExpandedTypes(prev => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  const byType: Record<string, BudgetCategory[]> = {}
  for (const cat of categories) {
    if (!cat.parent_id) {
      if (!byType[cat.category_type]) byType[cat.category_type] = []
      byType[cat.category_type].push(cat)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab switcher */}
      <div className="flex border-b border-gray-100 bg-white px-4 flex-shrink-0">
        {(['plans', 'categories'] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setManagementTab(tab)}
            className={clsx(
              'px-5 py-3 text-[13px] font-medium transition-colors relative',
              managementTab === tab
                ? 'text-teal-700 border-b-2 border-teal-600 -mb-px'
                : 'text-gray-500 hover:text-gray-700',
            )}
          >
            {tab === 'plans' ? t('rules.plans_tab') : t('rules.categories_tab')}
          </button>
        ))}
      </div>

      {managementTab === 'plans' ? (
        <div className="flex flex-1 min-h-0 overflow-hidden" dir="rtl">
          {/* Left: category tree */}
          <div className="w-64 min-w-[240px] border-l border-gray-100 bg-white flex flex-col overflow-hidden">
            {/* Year selector */}
            <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
              <span className="text-[12px] text-gray-500">{t('manage.year_label')}</span>
              <select
                value={activeBudgetYear}
                onChange={(e) => setActiveBudgetYear(Number(e.target.value))}
                className="flex-1 px-2 py-1 text-[12px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400"
              >
                {[2024, 2025, 2026].map(y => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>

            {/* Tree */}
            <div className="flex-1 overflow-y-auto py-2">
              {isLoading && (
                <p className="px-4 py-3 text-[12px] text-gray-400">{tc('status.loading')}</p>
              )}
              {isError && (
                <p className="px-4 py-3 text-[11px] text-red-500">
                  Failed to load categories. Check browser console.
                </p>
              )}
              {!isLoading && !isError && categories.length === 0 && (
                <p className="px-4 py-3 text-[12px] text-gray-400">No categories found</p>
              )}
              {TYPE_ORDER.map((type) => {
                const cats = byType[type] ?? []
                if (cats.length === 0) return null
                return (
                  <div key={type}>
                    <button
                      type="button"
                      onClick={() => toggleType(type)}
                      className="w-full flex items-center justify-between px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500 hover:bg-gray-50"
                    >
                      {t(`category_types.${type}`)}
                      <span className={clsx('transition-transform', expandedTypes.has(type) ? 'rotate-90' : '')}>›</span>
                    </button>
                    {expandedTypes.has(type) && cats.map(cat => (
                      <CategoryTreeNode
                        key={cat.id}
                        cat={cat}
                        level={0}
                        selectedId={selectedCatId}
                        planMap={planMap}
                        hasPlanLabel={t('manage.has_plan')}
                        noPlanLabel={t('manage.no_plan')}
                        onSelect={setSelectedCatId}
                      />
                    ))}
                  </div>
                )
              })}
            </div>

            {/* Bulk actions */}
            <div className="border-t border-gray-100 p-3 space-y-2">
              <button
                type="button"
                onClick={() => generateMutation.mutate()}
                disabled={generateMutation.isPending}
                className="w-full px-3 py-2 text-[11px] bg-teal-50 text-teal-700 border border-teal-200 rounded-lg hover:bg-teal-100 disabled:opacity-50 transition-colors"
              >
                {generateMutation.isPending
                  ? t('manage.generating')
                  : t('manage.generate_from_history_btn', { year: activeBudgetYear })}
              </button>
              <button
                type="button"
                onClick={() => importMutation.mutate()}
                disabled={importMutation.isPending}
                className="w-full px-3 py-2 text-[11px] bg-gray-50 text-gray-700 border border-gray-200 rounded-lg hover:bg-gray-100 disabled:opacity-50 transition-colors"
              >
                {importMutation.isPending
                  ? t('manage.importing')
                  : t('manage.import_from_year_btn', { year: activeBudgetYear - 1 })}
              </button>
            </div>
          </div>

          {/* Right: plan editor */}
          <div className="flex-1 overflow-y-auto bg-gray-50 p-6">
            {selectedCat ? (
              <PlanEditor
                key={`${selectedCat.id}-${activeBudgetYear}`}
                category={selectedCat}
                year={activeBudgetYear}
                existingPlan={planMap[selectedCat.id] ?? null}
                onSaved={() => qc.invalidateQueries({ queryKey: ['budget-categories', activeBudgetYear] })}
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <div className="text-4xl mb-3">{t('manage.select_category_arrow')}</div>
                <p className="text-[14px]">{t('manage.select_category')}</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto bg-gray-50 p-6" dir="rtl">
          <CategoriesPanel
            categories={categories}
            onRefresh={() => qc.invalidateQueries({ queryKey: ['budget-categories', activeBudgetYear] })}
          />
        </div>
      )}
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function findCat(cats: BudgetCategory[], id: string): BudgetCategory | null {
  for (const c of cats) {
    if (c.id === id) return c
    const found = findCat(c.children ?? [], id)
    if (found) return found
  }
  return null
}

function flattenCats(cats: BudgetCategory[]): BudgetCategory[] {
  const out: BudgetCategory[] = []
  function walk(list: BudgetCategory[]) {
    for (const c of list) { out.push(c); walk(c.children ?? []) }
  }
  walk(cats)
  return out
}

// ─── Categories Panel ─────────────────────────────────────────────────────────

function CategoriesPanel({ categories, onRefresh }: {
  categories: BudgetCategory[]
  onRefresh: () => void
}) {
  const { t } = useTranslation('budget')
  const qc = useQueryClient()

  const flat = flattenCats(categories)

  // Create form
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newNameEn, setNewNameEn] = useState('')
  const [newType, setNewType] = useState('expense')

  // Inline edit
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [editNameEn, setEditNameEn] = useState('')

  // Delete
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null)
  const [deleteConflict, setDeleteConflict] = useState<number | null>(null)

  const createMut = useMutation({
    mutationFn: (payload: Record<string, unknown>) => createBudgetCategory(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budget-categories'] })
      setShowCreate(false)
      setNewName('')
      setNewNameEn('')
      setNewType('expense')
    },
  })

  function submitCreate() {
    if (!newName.trim() || createMut.isPending) return
    createMut.mutate({
      name: newName.trim(),
      name_en: newNameEn.trim() || null,
      category_type: newType,
      sort_order: 99,
    })
  }

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      updateBudgetCategory(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budget-categories'] })
      setEditingId(null)
    },
  })

  const deleteMut = useMutation({
    mutationFn: ({ id, force }: { id: string; force: boolean }) => deleteBudgetCategory(id, force),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budget-categories'] })
      setDeleteTarget(null)
      setDeleteConflict(null)
      onRefresh()
    },
    onError: (err: unknown) => {
      const e = err as { response?: { status?: number; data?: { detail?: string } } }
      if (e?.response?.status === 409) {
        const match = e?.response?.data?.detail?.match(/\d+/)
        setDeleteConflict(match ? parseInt(match[0]) : 0)
      }
    },
  })

  function startEdit(cat: BudgetCategory) {
    setEditingId(cat.id)
    setEditName(cat.name)
    setEditNameEn(cat.name_en ?? '')
  }

  // Group root cats by type
  const rootByType: Record<string, BudgetCategory[]> = {}
  for (const cat of flat.filter(c => !c.parent_id)) {
    if (!rootByType[cat.category_type]) rootByType[cat.category_type] = []
    rootByType[cat.category_type].push(cat)
  }

  const inputCls = 'px-2.5 py-1.5 text-[12px] border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-teal-400'

  return (
    <div className="max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-[18px] font-semibold text-gray-900">{t('rules.categories_tab')}</h2>
        <button
          type="button"
          onClick={() => setShowCreate(v => !v)}
          className="px-3 py-1.5 text-[12px] font-medium bg-teal-600 hover:bg-teal-700 text-white rounded-lg transition-colors"
        >
          {t('rules.new_category')}
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="mb-5 p-4 bg-white rounded-xl border border-gray-200 shadow-sm space-y-3">
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
                {t('rules.category_name_he')}
              </label>
              <input
                autoFocus
                type="text"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder={t('rules.category_name_placeholder')}
                className={clsx(inputCls, 'w-full')}
                onKeyDown={e => { if (e.key === 'Enter') submitCreate() }}
                dir="rtl"
              />
            </div>
            <div className="flex-1">
              <label className="block text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
                {t('rules.category_name_en')}
              </label>
              <input
                type="text"
                value={newNameEn}
                onChange={e => setNewNameEn(e.target.value)}
                placeholder="English name (optional)"
                className={clsx(inputCls, 'w-full')}
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">
              {t('rules.category_type_label')}
            </label>
            {TYPE_ORDER.map(type => (
              <button
                key={type}
                type="button"
                onClick={() => setNewType(type)}
                className={clsx(
                  'px-2.5 py-1 text-[11px] font-medium rounded-md border transition-colors',
                  newType === type
                    ? 'bg-teal-600 text-white border-teal-600'
                    : 'bg-white text-gray-500 border-gray-200 hover:border-teal-300',
                )}
              >
                {t(`category_types.${type}`)}
              </button>
            ))}
            <div className="flex gap-2 mr-auto">
              <button
                type="button"
                disabled={!newName.trim() || createMut.isPending}
                onClick={submitCreate}
                className="px-3 py-1.5 text-[12px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50 transition-colors"
              >
                {createMut.isPending ? '…' : t('rules.btn_create')}
              </button>
              <button type="button" onClick={() => setShowCreate(false)}
                className="px-3 py-1.5 text-[12px] text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Category list */}
      {flat.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-[13px] text-gray-400">
          {t('rules.no_categories')}
        </div>
      ) : (
        TYPE_ORDER.map(type => {
          const typeCats = rootByType[type] ?? []
          if (typeCats.length === 0) return null
          return (
            <div key={type} className="mb-6">
              <div className="flex items-center gap-2 mb-2">
                <span className={clsx('text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded', TYPE_COLORS[type])}>
                  {t(`category_types.${type}`)}
                </span>
                <div className="flex-1 h-px bg-gray-100" />
              </div>
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm divide-y divide-gray-50">
                {typeCats.map(cat => (
                  <CategoryRow
                    key={cat.id}
                    cat={cat}
                    isEditing={editingId === cat.id}
                    editName={editName}
                    editNameEn={editNameEn}
                    onEditName={setEditName}
                    onEditNameEn={setEditNameEn}
                    onStartEdit={() => startEdit(cat)}
                    onCancelEdit={() => setEditingId(null)}
                    onSaveEdit={() => updateMut.mutate({ id: cat.id, payload: { name: editName.trim(), name_en: editNameEn.trim() || null } })}
                    savePending={updateMut.isPending}
                    onDelete={() => { setDeleteTarget({ id: cat.id, name: cat.name }); setDeleteConflict(null) }}
                    inputCls={inputCls}
                  />
                ))}
              </div>
            </div>
          )
        })
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <ConfirmDialog
          open={!!deleteTarget && deleteConflict === null}
          title={t('rules.delete_rule_title')}
          message={t('rules.delete_rule_msg', { name: deleteTarget.name })}
          confirmLabel={t('rules.btn_delete')}
          danger
          onConfirm={() => deleteMut.mutate({ id: deleteTarget.id, force: false })}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {/* Delete conflict — category has transactions */}
      {deleteTarget && deleteConflict !== null && (
        <ConfirmDialog
          open={true}
          title={t('rules.edit_category')}
          message={t('rules.delete_category_warning', { count: deleteConflict })}
          confirmLabel={t('rules.delete_anyway')}
          danger
          onConfirm={() => deleteMut.mutate({ id: deleteTarget.id, force: true })}
          onCancel={() => { setDeleteTarget(null); setDeleteConflict(null) }}
        />
      )}
    </div>
  )
}

function CategoryRow({
  cat, isEditing, editName, editNameEn,
  onEditName, onEditNameEn, onStartEdit, onCancelEdit, onSaveEdit,
  savePending, onDelete, inputCls,
}: {
  cat: BudgetCategory
  isEditing: boolean
  editName: string
  editNameEn: string
  onEditName: (v: string) => void
  onEditNameEn: (v: string) => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => void
  savePending: boolean
  onDelete: () => void
  inputCls: string
}) {
  const { t } = useTranslation('budget')

  if (isEditing) {
    return (
      <div className="px-4 py-3 flex items-center gap-3">
        <input
          autoFocus
          type="text"
          value={editName}
          onChange={e => onEditName(e.target.value)}
          className={clsx(inputCls, 'flex-1')}
          dir="rtl"
          onKeyDown={e => { if (e.key === 'Enter') onSaveEdit(); if (e.key === 'Escape') onCancelEdit() }}
        />
        <input
          type="text"
          value={editNameEn}
          onChange={e => onEditNameEn(e.target.value)}
          placeholder="English"
          className={clsx(inputCls, 'w-32')}
          onKeyDown={e => { if (e.key === 'Enter') onSaveEdit(); if (e.key === 'Escape') onCancelEdit() }}
        />
        <button type="button" disabled={!editName.trim() || savePending}
          onClick={onSaveEdit}
          className="px-2.5 py-1.5 text-[11px] bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50">
          {savePending ? '…' : t('manage.update_plan')}
        </button>
        <button type="button" onClick={onCancelEdit}
          className="px-2.5 py-1.5 text-[11px] text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50">
          Cancel
        </button>
      </div>
    )
  }

  return (
    <div className="px-4 py-3 flex items-center gap-3 group">
      <span className="flex-1 text-[13px] text-gray-800 truncate" dir="rtl">{cat.name}</span>
      {cat.name_en && (
        <span className="text-[11px] text-gray-400 truncate max-w-[120px]">{cat.name_en}</span>
      )}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button type="button" onClick={onStartEdit}
          title={t('rules.btn_edit')}
          className="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-teal-600 hover:bg-teal-50 transition-colors">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 2l2 2-6 6H3V8l6-6z"/></svg>
        </button>
        <button type="button" onClick={onDelete}
          title={t('rules.btn_delete')}
          className="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-rose-500 hover:bg-rose-50 transition-colors">
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M2 4h9M5 4V3h3v1M4 4l.5 6h4l.5-6"/></svg>
        </button>
      </div>
    </div>
  )
}

// ─── Category Tree Node (Plans tab) ───────────────────────────────────────────

function CategoryTreeNode({
  cat, level, selectedId, planMap, hasPlanLabel, noPlanLabel, onSelect,
}: {
  cat: BudgetCategory
  level: number
  selectedId: string | null
  planMap: Record<string, BudgetPlan>
  hasPlanLabel: string
  noPlanLabel: string
  onSelect: (id: string) => void
}) {
  const hasPlan = !!planMap[cat.id]
  const isSelected = selectedId === cat.id

  return (
    <>
      <button
        type="button"
        onClick={() => onSelect(cat.id)}
        className={clsx(
          'w-full flex items-center gap-2 py-2 text-[12px] transition-colors border-r-2',
          isSelected
            ? 'bg-teal-50 text-teal-700 border-teal-400'
            : 'text-gray-700 hover:bg-gray-50 border-transparent',
        )}
        style={{ paddingRight: `${16 + level * 16}px`, paddingLeft: '12px' }}
      >
        <span className="truncate flex-1 text-right">{cat.name}</span>
        {hasPlan ? (
          <span className="text-[9px] text-teal-500 flex-shrink-0">{hasPlanLabel}</span>
        ) : (
          <span className="text-[9px] text-gray-300 flex-shrink-0">{noPlanLabel}</span>
        )}
      </button>
      {(cat.children ?? []).map(child => (
        <CategoryTreeNode
          key={child.id}
          cat={child}
          level={level + 1}
          selectedId={selectedId}
          planMap={planMap}
          hasPlanLabel={hasPlanLabel}
          noPlanLabel={noPlanLabel}
          onSelect={onSelect}
        />
      ))}
    </>
  )
}

// ─── Plan Editor ──────────────────────────────────────────────────────────────

function PlanEditor({
  category, year, existingPlan, onSaved,
}: {
  category: BudgetCategory
  year: number
  existingPlan: BudgetPlan | null
  onSaved: () => void
}) {
  const { t } = useTranslation('budget')
  const { t: tc } = useTranslation('common')
  const [planType, setPlanType] = useState<'fixed_monthly' | 'annual_pool' | 'one_time'>(
    existingPlan?.plan_type ?? 'fixed_monthly'
  )
  const [monthlyAmount, setMonthlyAmount] = useState<string>(
    existingPlan?.monthly_amount != null ? String(existingPlan.monthly_amount) : ''
  )
  const [annualAmount, setAnnualAmount] = useState<string>(
    existingPlan?.annual_amount != null ? String(existingPlan.annual_amount) : ''
  )
  const [notes, setNotes] = useState(existingPlan?.notes ?? '')
  const [overrides, setOverrides] = useState<Record<string, string>>(
    Object.fromEntries(
      Object.entries(existingPlan?.monthly_overrides ?? {}).map(([k, v]) => [k, String(v)])
    )
  )
  const [saved, setSaved] = useState(false)

  const createMut = useMutation({ mutationFn: createBudgetPlan })
  const updateMut = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => updateBudgetPlan(id, payload) })
  const isPending = createMut.isPending || updateMut.isPending

  async function handleSave() {
    const payload: Record<string, unknown> = {
      category_id: category.id,
      year,
      plan_type: planType,
      notes: notes || null,
      monthly_amount: planType === 'fixed_monthly' && monthlyAmount ? Number(monthlyAmount) : null,
      annual_amount: (planType === 'annual_pool' || planType === 'one_time') && annualAmount ? Number(annualAmount) : null,
      monthly_overrides: planType === 'fixed_monthly' && Object.keys(overrides).length > 0
        ? Object.fromEntries(Object.entries(overrides).filter(([, v]) => v !== '').map(([k, v]) => [k, Number(v)]))
        : null,
    }

    if (existingPlan) {
      await updateMut.mutateAsync({ id: existingPlan.id, payload })
    } else {
      await createMut.mutateAsync(payload)
    }
    onSaved()
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="max-w-xl">
      <div className="flex items-center gap-3 mb-5">
        <div>
          <h2 className="text-[18px] font-semibold text-gray-900">{category.name}</h2>
          {category.name_en && <p className="text-[12px] text-gray-400">{category.name_en}</p>}
        </div>
        <span className={clsx('text-[11px] px-2 py-0.5 rounded-full font-medium', TYPE_COLORS[category.category_type])}>
          {t(`category_types.${category.category_type}`)}
        </span>
        <span className="text-[12px] text-gray-400 mr-auto">{year}</span>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 p-5 space-y-5">
        <div>
          <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-2">
            {t('manage.plan_type_label')}
          </label>
          <div className="flex gap-2">
            {(['fixed_monthly', 'annual_pool', 'one_time'] as const).map((pt) => (
              <button
                key={pt}
                type="button"
                onClick={() => setPlanType(pt)}
                className={clsx(
                  'flex-1 py-2 px-3 text-[12px] rounded-lg border font-medium transition-colors',
                  planType === pt
                    ? 'bg-teal-600 text-white border-teal-600'
                    : 'border-gray-200 text-gray-600 hover:border-teal-300',
                )}
              >
                {t(`manage.plan_types.${pt}`)}
              </button>
            ))}
          </div>
        </div>

        {planType === 'fixed_monthly' && (
          <div>
            <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-2">
              {t('manage.fields.monthly_amount')}
            </label>
            <input
              type="number"
              value={monthlyAmount}
              onChange={(e) => setMonthlyAmount(e.target.value)}
              placeholder="0"
              className="w-full px-3 py-2 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400"
              dir="ltr"
            />
            {monthlyAmount && (
              <p className="text-[11px] text-gray-400 mt-1">
                {t('manage.fields.annual_equivalent', { amount: fmtILS(Number(monthlyAmount) * 12) })}
              </p>
            )}
          </div>
        )}

        {(planType === 'annual_pool' || planType === 'one_time') && (
          <div>
            <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-2">
              {t('manage.fields.annual_amount')}
            </label>
            <input
              type="number"
              value={annualAmount}
              onChange={(e) => setAnnualAmount(e.target.value)}
              placeholder="0"
              className="w-full px-3 py-2 text-[14px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400"
              dir="ltr"
            />
            {planType === 'annual_pool' && annualAmount && (
              <p className="text-[11px] text-gray-400 mt-1">
                {t('manage.fields.monthly_avg', { amount: fmtILS(Number(annualAmount) / 12) })}
              </p>
            )}
          </div>
        )}

        {planType === 'fixed_monthly' && (
          <div>
            <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-2">
              {t('manage.fields.monthly_overrides')}
            </label>
            <div className="grid grid-cols-3 gap-2">
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <div key={m} className="flex items-center gap-1">
                  <span className="text-[10px] text-gray-400 w-8 flex-shrink-0">{tc(`time.months_short.${m}`)}</span>
                  <input
                    type="number"
                    value={overrides[String(m)] ?? ''}
                    onChange={(e) => {
                      const val = e.target.value
                      setOverrides(prev => {
                        const next = { ...prev }
                        if (val) next[String(m)] = val
                        else delete next[String(m)]
                        return next
                      })
                    }}
                    placeholder={monthlyAmount || '–'}
                    className="w-full px-2 py-1 text-[11px] border border-gray-200 rounded focus:outline-none focus:border-teal-300"
                    dir="ltr"
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-2">
            {t('manage.fields.notes')}
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 resize-none"
            placeholder={t('manage.fields.notes_placeholder')}
          />
        </div>

        <div className="flex items-center gap-3 pt-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={isPending}
            className="flex-1 py-2.5 bg-teal-600 text-white text-[13px] font-medium rounded-lg hover:bg-teal-700 disabled:opacity-50 transition-colors"
          >
            {isPending ? t('manage.saving') : existingPlan ? t('manage.update_plan') : t('manage.create_plan')}
          </button>
          {saved && <span className="text-[12px] text-emerald-600">{t('manage.saved')}</span>}
        </div>
      </div>
    </div>
  )
}
