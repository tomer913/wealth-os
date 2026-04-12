import { useQuery } from '@tanstack/react-query'
import { getBudgetSummary, getBudgetReviewQueue } from '../api/portfolio'
import { useAppStore } from '../store'
import type { BudgetSummaryRow } from '../types'
import clsx from 'clsx'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const MONTHS = [
  '', 'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
  'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר',
]
const MONTHS_EN = [
  '', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

function fmtILS(n: number | null | undefined) {
  if (n == null) return '–'
  return new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS', maximumFractionDigits: 0 }).format(n)
}

function fmtPct(n: number | null | undefined) {
  if (n == null) return '–'
  return `${(n * 100).toFixed(0)}%`
}

const TYPE_LABELS: Record<string, string> = {
  income: 'הכנסות',
  expense: 'הוצאות',
  saving: 'חיסכון',
  investment: 'השקעות',
}

const TYPE_COLORS: Record<string, string> = {
  income: '#10b981',
  expense: '#ef4444',
  saving: '#8b5cf6',
  investment: '#3b82f6',
}

export default function BudgetDashboardPage() {
  const { activeBudgetYear, activeBudgetMonth, budgetViewMode, setActiveBudgetYear, setActiveBudgetMonth, setBudgetViewMode } = useAppStore()

  const { data: summary = [], isLoading } = useQuery({
    queryKey: ['budget-summary', activeBudgetYear, activeBudgetMonth],
    queryFn: () => getBudgetSummary(activeBudgetYear, activeBudgetMonth),
  })

  const { data: reviewQueue = [] } = useQuery({
    queryKey: ['budget-review'],
    queryFn: getBudgetReviewQueue,
  })

  // KPI computations
  const income = summary.filter((r: BudgetSummaryRow) => r.category_type === 'income')
  const expenses = summary.filter((r: BudgetSummaryRow) => r.category_type === 'expense')
  const savings = summary.filter((r: BudgetSummaryRow) => r.category_type === 'saving')

  const totalPlanIncome = income.reduce((s: number, r: BudgetSummaryRow) => s + (r.plan_amount ?? 0), 0)
  const totalActualIncome = income.reduce((s: number, r: BudgetSummaryRow) => s + r.actual_amount, 0)
  const totalPlanExpense = expenses.reduce((s: number, r: BudgetSummaryRow) => s + (r.plan_amount ?? 0), 0)
  const totalActualExpense = expenses.reduce((s: number, r: BudgetSummaryRow) => s + r.actual_amount, 0)
  const totalPlanSaving = savings.reduce((s: number, r: BudgetSummaryRow) => s + (r.plan_amount ?? 0), 0)
  const totalActualSaving = savings.reduce((s: number, r: BudgetSummaryRow) => s + r.actual_amount, 0)
  const cashflow = totalActualIncome - totalActualExpense

  // Chart data: group by category_type
  const chartData = Object.entries(
    summary.reduce((acc: Record<string, { plan: number; actual: number }>, r: BudgetSummaryRow) => {
      if (!acc[r.category_type]) acc[r.category_type] = { plan: 0, actual: 0 }
      acc[r.category_type].plan += r.plan_amount ?? 0
      acc[r.category_type].actual += r.actual_amount
      return acc
    }, {})
  ).map(([type, vals]) => ({
    name: TYPE_LABELS[type] ?? type,
    type,
    plan: Math.round((vals as { plan: number; actual: number }).plan),
    actual: Math.round((vals as { plan: number; actual: number }).actual),
  }))

  if (isLoading) {
    return <div className="p-6 text-gray-400 text-sm">טוען נתוני תקציב…</div>
  }

  return (
    <div className="p-6 space-y-5 pb-20 md:pb-6 bg-gray-50 min-h-full" dir="rtl">

      {/* Header controls */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <select
            value={activeBudgetMonth}
            onChange={(e) => setActiveBudgetMonth(Number(e.target.value))}
            className="px-3 py-1.5 text-[13px] border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-teal-400"
          >
            {MONTHS_EN.slice(1).map((m, i) => (
              <option key={i + 1} value={i + 1}>{MONTHS[i + 1]} ({m})</option>
            ))}
          </select>
          <select
            value={activeBudgetYear}
            onChange={(e) => setActiveBudgetYear(Number(e.target.value))}
            className="px-3 py-1.5 text-[13px] border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-teal-400"
          >
            {[2023, 2024, 2025, 2026].map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1 bg-white border border-gray-200 rounded-lg p-0.5">
          {(['monthly', 'annual'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setBudgetViewMode(mode)}
              className={clsx(
                'px-3 py-1 text-[12px] rounded-md font-medium transition-colors',
                budgetViewMode === mode
                  ? 'bg-teal-600 text-white'
                  : 'text-gray-500 hover:text-gray-700',
              )}
            >
              {mode === 'monthly' ? 'חודשי' : 'שנתי'}
            </button>
          ))}
        </div>
      </div>

      {/* Review queue alert */}
      {reviewQueue.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-amber-500">⚠</span>
            <span className="text-[13px] text-amber-800 font-medium">
              {reviewQueue.length} עסקאות ממתינות לסיווג ידני
            </span>
          </div>
          <a href="/budget/rules" className="text-[12px] text-amber-700 underline">עבור לתור בדיקה</a>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="הכנסות" plan={totalPlanIncome} actual={totalActualIncome} type="income" />
        <KpiCard label="הוצאות" plan={totalPlanExpense} actual={totalActualExpense} type="expense" />
        <KpiCard label="חיסכון" plan={totalPlanSaving} actual={totalActualSaving} type="saving" />
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <p className="text-[11px] text-gray-500 uppercase tracking-wide mb-1">תזרים נטו</p>
          <p className={clsx('text-[22px] font-semibold', cashflow >= 0 ? 'text-emerald-600' : 'text-red-500')}>
            {fmtILS(cashflow)}
          </p>
          <p className="text-[11px] text-gray-400 mt-1">הכנסות פחות הוצאות</p>
        </div>
      </div>

      {/* Chart + Table */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Bar chart */}
        <div className="bg-white rounded-xl border border-gray-100 p-4 lg:col-span-1">
          <p className="text-[12px] font-semibold text-gray-700 mb-3">תכנון מול ביצוע</p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData} barGap={2}>
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} width={40} />
              <Tooltip formatter={(v: number) => fmtILS(v)} />
              <Bar dataKey="plan" name="תכנון" fill="#94a3b8" radius={[3, 3, 0, 0]} />
              <Bar dataKey="actual" name="ביצוע" radius={[3, 3, 0, 0]}>
                {chartData.map((entry, i) => (
                  <Cell key={i} fill={TYPE_COLORS[entry.type] ?? '#6b7280'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Category breakdown table */}
        <div className="bg-white rounded-xl border border-gray-100 lg:col-span-2 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100">
            <p className="text-[12px] font-semibold text-gray-700">פירוט קטגוריות — {MONTHS[activeBudgetMonth]} {activeBudgetYear}</p>
          </div>
          {summary.length === 0 ? (
            <div className="p-6 text-center text-gray-400 text-sm">אין נתוני תקציב לחודש זה</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-gray-100 text-gray-400 text-[10px] uppercase tracking-wide">
                    <th className="px-4 py-2 text-right">קטגוריה</th>
                    <th className="px-4 py-2 text-left">תכנון</th>
                    <th className="px-4 py-2 text-left">ביצוע</th>
                    <th className="px-4 py-2 text-left">סטייה</th>
                    <th className="px-4 py-2 text-left w-32">התקדמות</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.map((row: BudgetSummaryRow) => {
                    const pct = row.plan_amount ? Math.min(row.actual_amount / row.plan_amount, 1) : 0
                    const over = row.plan_amount != null && row.actual_amount > row.plan_amount
                    return (
                      <tr key={row.category_id} className="border-b border-gray-50 hover:bg-gray-50/50">
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2">
                            <span className={clsx(
                              'inline-block w-1.5 h-1.5 rounded-full',
                              row.category_type === 'income' ? 'bg-emerald-500' :
                              row.category_type === 'expense' ? 'bg-red-400' :
                              row.category_type === 'saving' ? 'bg-purple-400' : 'bg-blue-400'
                            )} />
                            <span className="text-gray-800 font-medium">{row.category_name}</span>
                            {row.has_override && <span className="text-[9px] text-orange-400">✱</span>}
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-gray-600" dir="ltr">{fmtILS(row.plan_amount)}</td>
                        <td className="px-4 py-2.5 text-gray-800 font-medium" dir="ltr">{fmtILS(row.actual_amount)}</td>
                        <td className={clsx('px-4 py-2.5 font-medium', over ? 'text-red-500' : 'text-emerald-600')} dir="ltr">
                          {row.variance != null ? (over ? '-' : '+') + fmtILS(Math.abs(row.variance)) : '–'}
                        </td>
                        <td className="px-4 py-2.5">
                          {row.plan_amount != null ? (
                            <div className="flex items-center gap-1.5">
                              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div
                                  className={clsx('h-full rounded-full', over ? 'bg-red-400' : 'bg-teal-400')}
                                  style={{ width: `${pct * 100}%` }}
                                />
                              </div>
                              <span className="text-[10px] text-gray-400 w-8">{fmtPct(pct)}</span>
                            </div>
                          ) : <span className="text-gray-300">–</span>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {summary.length === 0 && (
        <div className="bg-white rounded-xl border border-dashed border-gray-200 p-8 text-center">
          <p className="text-gray-400 text-sm mb-2">אין תכנון תקציב לתקופה זו</p>
          <a href="/budget/manage" className="text-teal-600 text-[13px] underline">לחץ כאן להגדרת תקציב</a>
        </div>
      )}
    </div>
  )
}

function KpiCard({ label, plan, actual, type }: { label: string; plan: number; actual: number; type: string }) {
  const color = TYPE_COLORS[type] ?? '#6b7280'
  const pct = plan > 0 ? actual / plan : 0
  const over = plan > 0 && actual > plan

  return (
    <div className="bg-white rounded-xl border border-gray-100 p-4">
      <p className="text-[11px] text-gray-500 uppercase tracking-wide mb-1">{label}</p>
      <p className="text-[22px] font-semibold text-gray-900">{fmtILS(actual)}</p>
      {plan > 0 ? (
        <>
          <p className="text-[11px] text-gray-400 mt-0.5">מתוך {fmtILS(plan)} מתוכנן</p>
          <div className="mt-2 h-1 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${Math.min(pct * 100, 100)}%`, backgroundColor: over ? '#ef4444' : color }}
            />
          </div>
        </>
      ) : (
        <p className="text-[11px] text-gray-300 mt-0.5">ללא תכנון</p>
      )}
    </div>
  )
}
