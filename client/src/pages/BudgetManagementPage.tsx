import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  getBudgetCategories, getBudgetPlans, createBudgetPlan, updateBudgetPlan,
  generatePlansFromHistory, importPlansFromYear,
} from '../api/portfolio'
import { useAppStore } from '../store'
import type { BudgetCategory, BudgetPlan } from '../types'
import clsx from 'clsx'

const TYPE_COLORS: Record<string, string> = {
  income: 'text-emerald-600 bg-emerald-50',
  expense: 'text-red-500 bg-red-50',
  saving: 'text-purple-600 bg-purple-50',
  investment: 'text-blue-600 bg-blue-50',
}

function fmtILS(n: number | null | undefined) {
  if (n == null) return '–'
  return new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS', maximumFractionDigits: 0 }).format(n)
}

export default function BudgetManagementPage() {
  const { t } = useTranslation('budget')
  const { t: tc } = useTranslation('common')
  const { activeBudgetYear, setActiveBudgetYear } = useAppStore()
  const qc = useQueryClient()

  const [selectedCatId, setSelectedCatId] = useState<string | null>(null)
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set(['expense', 'income', 'saving']))

  const { data: categories = [] } = useQuery({
    queryKey: ['budget-categories'],
    queryFn: getBudgetCategories,
  })

  const { data: plans = [] } = useQuery({
    queryKey: ['budget-plans', activeBudgetYear],
    queryFn: () => getBudgetPlans(activeBudgetYear),
  })

  const planMap: Record<string, BudgetPlan> = plans.reduce((acc: Record<string, BudgetPlan>, p: BudgetPlan) => {
    acc[p.category_id] = p
    return acc
  }, {})

  const selectedCat = selectedCatId ? findCat(categories, selectedCatId) : null

  const generateMutation = useMutation({
    mutationFn: () => generatePlansFromHistory(activeBudgetYear, 6),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-plans'] }),
  })

  const importMutation = useMutation({
    mutationFn: () => importPlansFromYear(activeBudgetYear - 1, activeBudgetYear),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-plans'] }),
  })

  function toggleType(type: string) {
    setExpandedTypes(prev => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  // Group flat category list by type (roots only)
  const byType: Record<string, BudgetCategory[]> = {}
  for (const cat of categories) {
    if (!cat.parent_id) {
      if (!byType[cat.category_type]) byType[cat.category_type] = []
      byType[cat.category_type].push(cat)
    }
  }

  return (
    <div className="flex h-full" dir="rtl">
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
          {(['income', 'expense', 'saving', 'investment'] as const).map((type) => {
            const cats = byType[type] ?? []
            if (cats.length === 0) return null
            return (
              <div key={type}>
                <button
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
            onClick={() => generateMutation.mutate()}
            disabled={generateMutation.isPending}
            className="w-full px-3 py-2 text-[11px] bg-teal-50 text-teal-700 border border-teal-200 rounded-lg hover:bg-teal-100 disabled:opacity-50 transition-colors"
          >
            {generateMutation.isPending
              ? t('manage.generating')
              : t('manage.generate_from_history_btn', { year: activeBudgetYear })}
          </button>
          <button
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
            onSaved={() => qc.invalidateQueries({ queryKey: ['budget-plans'] })}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="text-4xl mb-3">{t('manage.select_category_arrow')}</div>
            <p className="text-[14px]">{t('manage.select_category')}</p>
          </div>
        )}
      </div>
    </div>
  )
}

function findCat(cats: BudgetCategory[], id: string): BudgetCategory | null {
  for (const c of cats) {
    if (c.id === id) return c
    const found = findCat(c.children ?? [], id)
    if (found) return found
  }
  return null
}

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
      {/* Category header */}
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
        {/* Plan type */}
        <div>
          <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-2">
            {t('manage.plan_type_label')}
          </label>
          <div className="flex gap-2">
            {(['fixed_monthly', 'annual_pool', 'one_time'] as const).map((pt) => (
              <button
                key={pt}
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

        {/* Monthly amount */}
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

        {/* Annual amount */}
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

        {/* Monthly overrides */}
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

        {/* Notes */}
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

        {/* Save */}
        <div className="flex items-center gap-3 pt-2">
          <button
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
