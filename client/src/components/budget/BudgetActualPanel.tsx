import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import { getBudgetActualTransactions } from '../../api/portfolio'
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
  const { t } = useTranslation('budget')

  const { data, isLoading } = useQuery({
    queryKey: ['budget-actual-transactions', actualId],
    queryFn: () => getBudgetActualTransactions(actualId!),
    enabled: isOpen && !!actualId,
  })

  if (!isOpen) return null

  const isIncome = categoryType === 'income'
  const over = planned != null && actual > planned

  function amountColor(tx: BudgetActualTransaction): string {
    if (isIncome) return 'text-emerald-600'
    return 'text-gray-800'
  }

  function amountSign(tx: BudgetActualTransaction): string {
    return isIncome ? '+' : '-'
  }

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
              <span dir="ltr" className={clsx('font-semibold', isIncome ? 'text-emerald-600' : over ? 'text-rose-600' : 'text-gray-900')}>
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
            <span className={clsx(
              'text-[11px] px-2 py-0.5 rounded-full font-medium',
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
            <div className="p-8 text-center text-[13px] text-gray-400">
              {tc('status.loading')}
            </div>
          ) : !data || data.transactions.length === 0 ? (
            <div className="p-8 text-center text-[13px] text-gray-400">
              לא נמצאו תנועות
            </div>
          ) : (
            <div>
              {data.transactions.map((tx: BudgetActualTransaction) => (
                <div key={tx.id}
                  className="flex items-center gap-3 px-5 py-3 border-b border-gray-50 last:border-0 hover:bg-gray-50/60 transition-colors">
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
                  <span dir="ltr" className={clsx('text-[13px] font-medium flex-shrink-0', amountColor(tx))}>
                    {amountSign(tx)}{formatILS(Math.abs(tx.amount))}
                  </span>
                </div>
              ))}
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
