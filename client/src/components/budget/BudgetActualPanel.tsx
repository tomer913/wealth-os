import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import {
  getBudgetActualTransactions,
  getBudgetCategories,
  excludeBudgetTransaction,
  recategorizeBudgetTransaction,
} from '../../api/portfolio'
import { formatILS } from '../../utils/format'
import type { BudgetActualTransaction } from '../../types'

interface BudgetActualPanelProps {
  isOpen: boolean
  onClose: () => void
  actualId: string | null
  categoryName: string
  month: number
  year: number
  actual: number
  planned: number | null
  categoryType: string
}

export function BudgetActualPanel({
  isOpen,
  onClose,
  actualId,
  categoryName,
  month,
  year,
  actual,
  planned,
  categoryType,
}: BudgetActualPanelProps) {
  const { t: tc } = useTranslation('common')
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['budget-actual-transactions', actualId],
    queryFn: () => getBudgetActualTransactions(actualId!),
    enabled: isOpen && !!actualId,
  })

  const { data: categoriesData } = useQuery({
    queryKey: ['budget-categories'],
    queryFn: () => getBudgetCategories(),
    enabled: isOpen,
  })
  const allCategories = categoriesData ?? []

  const excludeMut = useMutation({
    mutationFn: (logId: string) => excludeBudgetTransaction(logId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budget-actual-transactions', actualId] })
      qc.invalidateQueries({ queryKey: ['budget-summary'] })
    },
  })

  const recatMut = useMutation({
    mutationFn: ({ logId, categoryId }: { logId: string; categoryId: string }) =>
      recategorizeBudgetTransaction(logId, categoryId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budget-actual-transactions', actualId] })
      qc.invalidateQueries({ queryKey: ['budget-summary'] })
      setRecatTarget(null)
    },
  })

  // Per-row action state
  const [confirmExclude, setConfirmExclude] = useState<string | null>(null)  // log_id
  const [recatTarget, setRecatTarget] = useState<{ logId: string; selectedCatId: string } | null>(null)

  if (!isOpen) return null

  const isIncome = categoryType === 'income'
  const over = planned != null && actual > planned

  function formatDate(dateStr: string | null): string {
    if (!dateStr) return '—'
    const d = new Date(dateStr)
    return d.toLocaleDateString('he-IL', { day: 'numeric', month: 'short' })
  }

  const monthName = tc(`time.months.${month}`)

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/25" onClick={onClose} />

      {/* Panel */}
      <div className="relative bg-white w-full max-w-md shadow-2xl flex flex-col" dir="rtl">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <h3 className="text-[15px] font-semibold text-gray-900">{categoryName}</h3>
            <p className="text-[12px] text-gray-400 mt-0.5">
              <span dir="ltr">{monthName} {year}</span>
            </p>
          </div>
          <button type="button" onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 transition-colors">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M2 2l10 10M12 2L2 12"/>
            </svg>
          </button>
        </div>

        {/* Summary row */}
        <div className="px-5 py-3 bg-gray-50 border-b border-gray-100 flex items-center justify-between text-[13px]">
          <div className="flex items-center gap-3">
            <div>
              <span className="text-gray-500">ביצוע: </span>
              <span dir="ltr" className={clsx('font-semibold',
                isIncome ? 'text-emerald-600' : over ? 'text-rose-600' : 'text-gray-900')}>
                {formatILS(actual)}
              </span>
            </div>
            {planned != null && (
              <div>
                <span className="text-gray-400">/ </span>
                <span dir="ltr" className="text-gray-500">{formatILS(planned)}</span>
                <span className="text-gray-400"> תכנון</span>
              </div>
            )}
          </div>
          {planned != null && (
            <span className={clsx('text-[11px] px-2 py-0.5 rounded-full font-medium',
              isIncome
                ? (over ? 'bg-blue-50 text-blue-600' : 'bg-amber-50 text-amber-600')
                : (over ? 'bg-rose-50 text-rose-600' : 'bg-emerald-50 text-emerald-600'),
            )}>
              {isIncome
                ? (over ? tc('budget.abovePlan') : tc('budget.belowPlan'))
                : (over ? tc('budget.overBudget') : tc('budget.underBudget'))}
            </span>
          )}
        </div>

        {/* Transaction list */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="p-8 text-center text-[13px] text-gray-400">{tc('status.loading')}</div>
          ) : !data || data.transactions.length === 0 ? (
            <div className="p-8 text-center text-[13px] text-gray-400">לא נמצאו תנועות</div>
          ) : (
            <div>
              {data.transactions.map((tx: BudgetActualTransaction) => {
                const isConfirmingExclude = confirmExclude === tx.log_id
                const isRecatting = recatTarget?.logId === tx.log_id
                const isMutating = (excludeMut.isPending && excludeMut.variables === tx.log_id) ||
                  (recatMut.isPending && recatMut.variables?.logId === tx.log_id)

                return (
                  <div key={tx.id} className="border-b border-gray-50 last:border-0">
                    {/* Main row */}
                    <div className="group flex items-center gap-3 px-5 py-3 hover:bg-gray-50/60 transition-colors">
                      {/* Date */}
                      <span dir="ltr" className="text-[11px] text-gray-400 flex-shrink-0 w-14 text-left">
                        {formatDate(tx.date)}
                      </span>

                      {/* Description */}
                      <span dir="rtl" className="flex-1 text-[13px] text-gray-800 truncate">
                        {tx.description}
                      </span>

                      {/* Badges */}
                      <div className="flex items-center gap-1 flex-shrink-0">
                        {tx.needs_review && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 font-medium">
                            לבדיקה
                          </span>
                        )}
                        {tx.reviewed && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-600 font-medium">
                            ✓
                          </span>
                        )}
                      </div>

                      {/* Amount */}
                      <span dir="ltr" className={clsx('text-[13px] font-medium flex-shrink-0',
                        isIncome ? 'text-emerald-600' : 'text-gray-800')}>
                        {isIncome ? '+' : '-'}{formatILS(Math.abs(tx.amount))}
                      </span>

                      {/* Action buttons — shown on hover when log_id exists */}
                      {tx.log_id && !isMutating && (
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                          <button type="button"
                            onClick={() => { setRecatTarget({ logId: tx.log_id!, selectedCatId: '' }); setConfirmExclude(null) }}
                            title={tc('budgetPanel.changeCategory')}
                            className="w-6 h-6 flex items-center justify-center rounded text-gray-400 hover:text-teal-600 hover:bg-teal-50 transition-colors">
                            <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M8 1l2 2-6 6H2V7l6-6z"/></svg>
                          </button>
                          <button type="button"
                            onClick={() => { setConfirmExclude(tx.log_id); setRecatTarget(null) }}
                            title={tc('budgetPanel.removeTransaction')}
                            className="w-6 h-6 flex items-center justify-center rounded text-gray-400 hover:text-rose-500 hover:bg-rose-50 transition-colors">
                            <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M1 3h9M4 3V2h3v1M3 3l.5 6h4L8 3"/></svg>
                          </button>
                        </div>
                      )}
                      {isMutating && (
                        <svg className="animate-spin text-gray-400 flex-shrink-0" width="12" height="12" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6.5 1v2M6.5 10v2M1 6.5h2M10 6.5h2" strokeLinecap="round"/></svg>
                      )}
                    </div>

                    {/* Inline remove confirm */}
                    {isConfirmingExclude && (
                      <div className="px-5 pb-3 flex items-center gap-2 bg-rose-50/60">
                        <span className="text-[12px] text-rose-700 flex-1">
                          {tc('budgetPanel.removeConfirm', { category: categoryName })}
                        </span>
                        <button type="button"
                          onClick={() => { excludeMut.mutate(tx.log_id!); setConfirmExclude(null) }}
                          className="px-2.5 py-1 text-[11px] font-medium bg-rose-500 text-white rounded-lg hover:bg-rose-600">
                          {tc('budgetPanel.confirmRemove')}
                        </button>
                        <button type="button"
                          onClick={() => setConfirmExclude(null)}
                          className="px-2.5 py-1 text-[11px] font-medium border border-gray-200 rounded-lg hover:bg-white">
                          {tc('budgetPanel.cancel')}
                        </button>
                      </div>
                    )}

                    {/* Inline recategorize */}
                    {isRecatting && recatTarget && (
                      <div className="px-5 pb-3 space-y-2 bg-teal-50/40">
                        <select
                          value={recatTarget.selectedCatId}
                          onChange={e => setRecatTarget({ ...recatTarget, selectedCatId: e.target.value })}
                          className="w-full px-2 py-1.5 text-[12px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 bg-white">
                          <option value="">— {tc('budgetPanel.changeCategory')} —</option>
                          {allCategories.map((c: { id: string; name: string; category_type: string }) => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                          ))}
                        </select>
                        {recatTarget.selectedCatId && (
                          <div className="flex items-center gap-2">
                            <button type="button"
                              onClick={() => recatMut.mutate({ logId: tx.log_id!, categoryId: recatTarget.selectedCatId })}
                              className="px-2.5 py-1 text-[11px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700">
                              {tc('budgetPanel.confirmMove')}
                            </button>
                            <button type="button"
                              onClick={() => setRecatTarget(null)}
                              className="px-2.5 py-1 text-[11px] font-medium border border-gray-200 rounded-lg hover:bg-white">
                              {tc('budgetPanel.cancel')}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer summary */}
        {data && data.count > 0 && (
          <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-between text-[12px] text-gray-500">
            <span>{data.count} תנועות</span>
            <span dir="ltr" className="font-semibold text-gray-800">{formatILS(data.total)}</span>
          </div>
        )}
      </div>
    </div>
  )
}
