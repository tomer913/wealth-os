import { useState } from 'react'
import { useSnapshot } from '../hooks/usePortfolio'
import { useFilteredSummary, useFilteredAssets, useFilteredCategories, useAppStore } from '../store'
import {
  AreaChart, Area, PieChart, Pie, Cell,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { formatILS, formatILSShort, formatPct, gainClass, categoryLabel } from '../utils/format'
import { CATEGORY_COLORS } from '../types'
import clsx from 'clsx'

export default function DashboardPage() {
  const { isLoading, isError } = useSnapshot()
  const summary = useFilteredSummary()
  const assets = useFilteredAssets()
  const categories = useFilteredCategories()
  const lastBuiltAt = useAppStore((s) => s.lastBuiltAt)

  if (isLoading) return <LoadingState />
  if (isError) return <ErrorState />
  if (!summary) return <EmptyState />

  const totalValue = summary.total_value_ils
  // API returns decimal (0.209) — multiply ×100 for percentage display
  const returnPct = summary.total_return_pct * 100

  const topHoldings = [...assets]
    .sort((a, b) => b.current_value_ils - a.current_value_ils)
    .slice(0, 6)

  const withReturn = assets.filter((a) => a.total_return_pct != null)
  const gainers = [...withReturn]
    .sort((a, b) => (b.total_return_pct ?? 0) - (a.total_return_pct ?? 0))
    .slice(0, 5)
  const losers = [...withReturn]
    .sort((a, b) => (a.total_return_pct ?? 0) - (b.total_return_pct ?? 0))
    .slice(0, 5)

  const donutData = categories.map((c) => ({
    name: categoryLabel(c.category),
    value: c.current_value_ils,
    color: CATEGORY_COLORS[c.category] ?? '#94a3b8',
  }))

  const chartData = categories.map((c) => ({
    name: categoryLabel(c.category),
    value: c.current_value_ils,
  }))

  return (
    <div className="p-6 space-y-5 pb-20 md:pb-6 bg-gray-50 min-h-full">

      {lastBuiltAt && (
        <p className="text-[12px] text-gray-400 flex items-center gap-1.5">
          <ClockIcon />
          Last updated: {new Date(lastBuiltAt).toLocaleString('en-IL')}
        </p>
      )}

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="PORTFOLIO VALUE"
          value={formatILS(totalValue)}
          sub={`${summary.asset_count} assets`}
          icon="$" iconColor="bg-blue-50 text-blue-500"
          tooltip="Total current market value of all assets in your portfolio, converted to ILS. Calculated by the snapshot engine using latest valuations, prices × quantities, and FX rates."
        />
        <KpiCard
          label="TOTAL PROFIT / LOSS"
          value={formatILS(summary.total_return_ils)}
          sub={formatPct(returnPct) + ' total return'}
          subPositive={summary.total_return_ils >= 0}
          icon="↗" iconColor="bg-emerald-50 text-emerald-500"
          tooltip="Total gain or loss in ILS: current portfolio value minus total invested capital (cost basis). The percentage is return ÷ total invested."
        />
        <KpiCard
          label="NET EQUITY"
          value={formatILS(summary.net_equity_ils)}
          sub={`Debt: ${formatILSShort(summary.total_debt_ils)}`}
          icon="%" iconColor="bg-violet-50 text-violet-500"
          tooltip="Portfolio value minus all liabilities (mortgages, loans). This is your actual net worth from this portfolio. Debt shown is the outstanding loan balance on leveraged assets like real estate."
        />
        <KpiCard
          label="TOTAL INVESTED"
          value={formatILS(summary.total_invested_ils)}
          sub="Cost basis"
          icon="◎" iconColor="bg-teal-50 text-teal-500"
          tooltip="Total capital you have invested — the sum of all purchase costs, deposits, and BUY transactions across all assets. This is your cost basis used to calculate P&L."
        />
      </div>

      {/* ── Chart + Donut ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="mb-1">
            <p className="text-[15px] font-semibold text-gray-900">Portfolio Value Over Time</p>
            <p className="text-[12px] font-semibold mt-0.5" style={{ color: returnPct >= 0 ? '#059669' : '#dc2626' }}>
              {formatPct(returnPct)} total return · {formatILS(summary.total_return_ils)} gain
            </p>
          </div>
          <div className="mt-4">
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -8, bottom: 0 }}>
                <defs>
                  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.12} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
                <YAxis tickFormatter={(v) => formatILSShort(v)} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} axisLine={false} width={62} />
                <Tooltip
                  contentStyle={{ fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}
                  formatter={(v: number) => [formatILS(v), 'Value']}
                />
                <Area type="monotone" dataKey="value" stroke="#3b82f6" fill="url(#areaGrad)" strokeWidth={2.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-[15px] font-semibold text-gray-900 mb-4">Portfolio Allocation</p>
          <div className="flex flex-col items-center">
            <div style={{ width: 130, height: 130 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={donutData} cx="50%" cy="50%" innerRadius={38} outerRadius={60} dataKey="value" strokeWidth={0}>
                    {donutData.map((d, i) => <Cell key={i} fill={d.color} />)}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="w-full mt-3 space-y-2.5">
              {donutData.map((d) => (
                <div key={d.name} className="flex items-center gap-2 text-[12px]">
                  <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: d.color }} />
                  <span className="text-gray-700 flex-1 font-medium">{d.name}</span>
                  <span className="text-gray-400 font-mono text-[11px]">
                    {totalValue > 0 ? ((d.value / totalValue) * 100).toFixed(1) : '0.0'}%
                  </span>
                  <span className="text-gray-500 font-mono text-[11px] w-16 text-right">
                    {formatILSShort(d.value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Holdings + Gainers/Losers ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-[15px] font-semibold text-gray-900 mb-4">Top Holdings</p>
          <div>
            <div className="grid grid-cols-[1fr_64px_52px_76px] gap-2 pb-2 border-b border-gray-100">
              {['Asset', 'Return %', 'Weight', 'Value'].map((h, i) => (
                <span key={h} className={clsx('text-[11px] text-gray-400 font-medium', i > 0 && 'text-right')}>{h}</span>
              ))}
            </div>
            {topHoldings.map((a) => {
              const weight = totalValue > 0 ? (a.current_value_ils / totalValue) * 100 : 0
              const ret = a.total_return_pct != null ? a.total_return_pct * 100 : null
              return (
                <div key={a.symbol} className="grid grid-cols-[1fr_64px_52px_76px] gap-2 py-2.5 border-b border-gray-50 last:border-0 items-center">
                  <div>
                    <div className="text-[13px] font-semibold text-gray-900 truncate">{a.name}</div>
                    <CategoryBadge cat={a.category} />
                  </div>
                  <span className={clsx('text-[12px] font-mono font-semibold text-right', gainClass(ret))}>{formatPct(ret)}</span>
                  <span className="text-[12px] font-mono text-right text-gray-400">{weight.toFixed(1)}%</span>
                  <span className="text-[13px] font-mono font-semibold text-right text-gray-800">{formatILSShort(a.current_value_ils)}</span>
                </div>
              )
            })}
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm space-y-4">
          <div>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-emerald-500 font-bold text-[15px]">↗</span>
              <p className="text-[15px] font-semibold text-gray-900">Top Gainers</p>
            </div>
            {gainers.map((a) => (
              <div key={a.symbol} className="flex items-center gap-3 py-2.5 border-b border-gray-50 last:border-0">
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-semibold text-gray-900 truncate">{a.name}</div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <CategoryBadge cat={a.category} />
                    <span className="text-[11px] text-gray-400 font-mono">{formatILSShort(a.current_value_ils)}</span>
                  </div>
                </div>
                <span className={clsx('text-[14px] font-bold font-mono flex-shrink-0', gainClass(a.total_return_pct))}>
                  {formatPct(a.total_return_pct != null ? a.total_return_pct * 100 : null)}
                </span>
              </div>
            ))}
          </div>

          <div className="border-t border-gray-100 pt-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-rose-500 font-bold text-[15px]">↘</span>
              <p className="text-[15px] font-semibold text-gray-900">Top Losers</p>
            </div>
            {losers.map((a) => (
              <div key={a.symbol} className="flex items-center gap-3 py-2.5 border-b border-gray-50 last:border-0">
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-semibold text-gray-900 truncate">{a.name}</div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <CategoryBadge cat={a.category} />
                    <span className="text-[11px] text-gray-400 font-mono">{formatILSShort(a.current_value_ils)}</span>
                  </div>
                </div>
                <span className={clsx('text-[14px] font-bold font-mono flex-shrink-0', gainClass(a.total_return_pct))}>
                  {formatPct(a.total_return_pct != null ? a.total_return_pct * 100 : null)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── KPI Card ──────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, subPositive, icon, iconColor, tooltip }: {
  label: string; value: string; sub: string
  subPositive?: boolean; icon: string; iconColor: string
  tooltip?: string
}) {
  const [showTip, setShowTip] = useState(false)

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm relative">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] font-semibold tracking-widest text-gray-400">{label}</span>
          {tooltip && (
            <div className="relative"
              onMouseEnter={() => setShowTip(true)}
              onMouseLeave={() => setShowTip(false)}>
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none"
                className="text-gray-300 hover:text-gray-500 cursor-help transition-colors flex-shrink-0"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <circle cx="6.5" cy="6.5" r="5.5"/>
                <path d="M6.5 6v3M6.5 4.5v.5"/>
              </svg>
              {showTip && (
                <div className="absolute left-0 top-5 z-50 w-64 bg-gray-900 text-white text-[11px] leading-relaxed rounded-lg px-3 py-2.5 shadow-xl pointer-events-none">
                  {tooltip}
                  {/* Arrow */}
                  <div className="absolute -top-1.5 left-1.5 w-3 h-3 bg-gray-900 rotate-45 rounded-sm" />
                </div>
              )}
            </div>
          )}
        </div>
        <span className={clsx('w-8 h-8 rounded-full flex items-center justify-center text-[14px] font-bold flex-shrink-0', iconColor)}>
          {icon}
        </span>
      </div>
      <div className="text-[28px] font-bold text-gray-900 num leading-tight tracking-tight">{value}</div>
      <div className={clsx('text-[12px] mt-1.5 font-medium',
        subPositive === true ? 'text-emerald-600' :
        subPositive === false ? 'text-rose-600' : 'text-gray-400'
      )}>
        {sub}
      </div>
    </div>
  )
}

// ─── Category badge ────────────────────────────────────────────────────────────
const CAT_BADGE: Record<string, string> = {
  real_estate:   'bg-blue-50 text-blue-700',
  pension:       'bg-purple-50 text-purple-700',
  securities:    'bg-emerald-50 text-emerald-700',
  alternatives:  'bg-amber-50 text-amber-700',
  cash:          'bg-gray-100 text-gray-500',
  crypto:        'bg-orange-50 text-orange-700',
  etf:           'bg-lime-50 text-lime-700',
  mutual_fund:   'bg-cyan-50 text-cyan-700',
  energy_income: 'bg-red-50 text-red-700',
}

function CategoryBadge({ cat }: { cat: string }) {
  return (
    <span className={clsx('inline-block text-[10px] px-1.5 py-0.5 rounded-sm font-semibold', CAT_BADGE[cat] ?? 'bg-gray-100 text-gray-500')}>
      {categoryLabel(cat)}
    </span>
  )
}

// ─── States ───────────────────────────────────────────────────────────────────
function LoadingState() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-[13px] text-gray-400">Loading portfolio…</p>
      </div>
    </div>
  )
}
function ErrorState() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-center">
        <p className="text-[14px] font-semibold text-gray-700 mb-1">Could not load snapshot</p>
        <p className="text-[12px] text-gray-400">Check that your Railway API is running and VITE_API_URL is set</p>
      </div>
    </div>
  )
}
function EmptyState() {
  return (
    <div className="flex items-center justify-center h-64">
      <p className="text-[13px] text-gray-400">Press "Build Snapshot" in the sidebar to load your portfolio</p>
    </div>
  )
}
function ClockIcon() {
  return <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 5v3l2 2"/></svg>
}
