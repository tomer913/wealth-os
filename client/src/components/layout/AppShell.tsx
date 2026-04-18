import { useState, useRef, useEffect } from 'react'
import { Outlet, useLocation, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Sidebar from './Sidebar'
import CategoryFilter from './CategoryFilter'
import PortfolioSelector from './PortfolioSelector'
import LanguageSwitcher from './LanguageSwitcher'
import { useRebuildSnapshot } from '../../hooks/usePortfolio'
import { useAppStore } from '../../store'
import { formatDateTime } from '../../utils/format'

const PAGE_TITLE_KEYS: Record<string, string> = {
  '/': 'nav.dashboard',
  '/assets': 'nav.assets',
  '/accounts': 'nav.accounts',
  '/transactions': 'nav.transactions',
  '/valuations': 'nav.valuations',
  '/connectors': 'nav.connectors',
  '/fx-rates': 'nav.fx_rates',
  '/reports': 'nav.reports',
  '/budget': 'nav.budget_dashboard',
  '/budget/manage': 'nav.budget_manage',
  '/budget/rules': 'nav.budget_rules',
  '/pipeline': 'nav.pipeline',
}

const SHOW_BUILD_SNAPSHOT = new Set(['/connectors'])
const SHOW_CATEGORY_FILTER = new Set(['/', '/assets', '/accounts', '/transactions', '/valuations', '/fx-rates', '/reports'])

export default function AppShell() {
  const location = useLocation()
  const { t: tc } = useTranslation('common')
  const titleKey = PAGE_TITLE_KEYS[location.pathname] ?? 'app_name'
  const title = tc(titleKey)
  const showBuild = SHOW_BUILD_SNAPSHOT.has(location.pathname)
  const showFilter = SHOW_CATEGORY_FILTER.has(location.pathname)

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <div className="hidden md:flex">
        <Sidebar />
      </div>
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <header className="bg-white border-b border-gray-100 px-5 py-3 flex items-center justify-between flex-shrink-0">
          <div>
            <h1 className="text-[18px] font-medium text-gray-900 tracking-tight">{title}</h1>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-3">
              <LanguageSwitcher />
              <PortfolioSelector />
            </div>
            {showBuild && <BuildSnapshotButton />}
          </div>
        </header>
        {showFilter && <CategoryFilter />}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <MobileTabBar />
    </div>
  )
}

// ─── Build Snapshot Button ────────────────────────────────────────────────────
function BuildSnapshotButton() {
  const { mutate: rebuild, isPending } = useRebuildSnapshot()
  const lastBuiltAt = useAppStore((s) => s.lastBuiltAt)
  const { t: tc } = useTranslation('common')
  const [open, setOpen] = useState(false)
  const [customDate, setCustomDate] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  function runToday() {
    rebuild(undefined)
    setOpen(false)
  }

  function runCustomDate() {
    if (!customDate) return
    rebuild(customDate)
    setOpen(false)
    setCustomDate('')
  }

  return (
    <div ref={ref} className="relative">
      <div className="flex items-center">
        {/* Main button */}
        <button
          onClick={runToday}
          disabled={isPending}
          className="flex items-center gap-1.5 pl-3 pr-2 py-1.5 bg-[#0d9488] hover:bg-teal-700 disabled:opacity-60 text-white text-[12px] font-medium rounded-l-lg transition-colors border-r border-teal-600"
        >
          <svg viewBox="0 0 13 13" width="12" height="12" fill="none" stroke="white" strokeWidth="2"
            style={isPending ? { animation: 'spin 1s linear infinite' } : undefined}>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            <path d="M11 6.5A4.5 4.5 0 1 1 6.5 2" strokeLinecap="round"/>
            <polyline points="6.5,2 9,2 9,4.5"/>
          </svg>
          {isPending ? tc('building') : tc('build_snapshot')}
        </button>
        {/* Dropdown arrow */}
        <button
          onClick={() => setOpen(v => !v)}
          disabled={isPending}
          className="px-2 py-1.5 bg-[#0d9488] hover:bg-teal-700 disabled:opacity-60 text-white rounded-r-lg transition-colors"
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
            <path d="M2 3.5l3 3 3-3"/>
          </svg>
        </button>
      </div>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-64 bg-white border border-gray-200 rounded-xl shadow-lg z-50 p-4">
          <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-3">
            {tc('snapshot_date')}
          </p>

          {/* Today option */}
          <button onClick={runToday}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 text-[13px] font-medium text-gray-700 hover:bg-teal-50 hover:text-teal-700 rounded-lg transition-colors mb-1">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <circle cx="7" cy="7" r="5.5"/>
              <path d="M7 4v3l1.5 1.5"/>
            </svg>
            {tc('today')}
          </button>

          {/* Custom date */}
          <div className="mt-2 pt-2 border-t border-gray-100">
            <p className="text-[11px] text-gray-400 mb-2">{tc('custom_date')}</p>
            <input
              type="date"
              value={customDate}
              max={new Date().toISOString().split('T')[0]}
              onChange={(e) => setCustomDate(e.target.value)}
              className="w-full px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 mb-2"
            />
            <button
              onClick={runCustomDate}
              disabled={!customDate}
              className="w-full px-3 py-2 text-[12px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-40 transition-colors">
              {tc('build_for', { date: customDate || '…' })}
            </button>
          </div>

          {/* Last built info */}
          {lastBuiltAt && (
            <p className="text-[10px] text-gray-400 text-center mt-3">
              {tc('last_built')}: {formatDateTime(lastBuiltAt)}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Tab Icons ───────────────────────────────────────────────────────────────
function TabDashboardIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2.5" y="2.5" width="6" height="6" rx="1.5"/>
      <rect x="11.5" y="2.5" width="6" height="6" rx="1.5"/>
      <rect x="2.5" y="11.5" width="6" height="6" rx="1.5"/>
      <rect x="11.5" y="11.5" width="6" height="6" rx="1.5"/>
    </svg>
  )
}
function TabAssetsIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 14.5l4.5-5 3 2.5 4-5.5 3 2"/>
      <path d="M2.5 17h15"/>
    </svg>
  )
}
function TabTxnsIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 7h12M4 7l3-3M4 7l3 3"/>
      <path d="M16 13H4m12 0l-3-3m3 3l-3 3"/>
    </svg>
  )
}
function TabBudgetIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="10" cy="10" r="7.5"/>
      <path d="M10 2.5v7.5l4.5 2.5"/>
    </svg>
  )
}
function TabMoreIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
      <circle cx="4" cy="10" r="1.5"/>
      <circle cx="10" cy="10" r="1.5"/>
      <circle cx="16" cy="10" r="1.5"/>
    </svg>
  )
}

// ─── Bottom Tab Bar ───────────────────────────────────────────────────────────
function MobileTabBar() {
  const location = useLocation()
  const { t: tc } = useTranslation('common')
  const [moreOpen, setMoreOpen] = useState(false)

  // Close drawer on navigation
  useEffect(() => {
    setMoreOpen(false)
  }, [location.pathname])

  const primaryTabs = [
    { to: '/', label: tc('nav.dashboard'), icon: <TabDashboardIcon />, exact: true },
    { to: '/assets', label: tc('nav.assets'), icon: <TabAssetsIcon />, exact: true },
    { to: '/transactions', label: tc('nav.transactions'), icon: <TabTxnsIcon />, exact: true },
    { to: '/budget', label: tc('nav.budget'), icon: <TabBudgetIcon />, exact: false },
  ]

  const moreTabs = [
    { to: '/accounts', label: tc('nav.accounts') },
    { to: '/valuations', label: tc('nav.valuations') },
  ]

  return (
    <>
      <nav dir="ltr" className="md:hidden fixed bottom-0 left-0 right-0 bg-[#0f172a] border-t border-white/10 flex z-50">
        {primaryTabs.map(({ to, label, icon, exact }) => {
          const isActive = exact
            ? location.pathname === to
            : location.pathname === to || location.pathname.startsWith(to + '/')
          return (
            <Link
              key={to}
              to={to}
              className={`flex-1 flex flex-col items-center justify-center py-2.5 gap-0.5 text-[10px] font-medium transition-colors min-h-[56px] ${
                isActive ? 'text-teal-400' : 'text-slate-500'
              }`}
            >
              {icon}
              <span>{label}</span>
            </Link>
          )
        })}
        <button
          onClick={() => setMoreOpen(v => !v)}
          className={`flex-1 flex flex-col items-center justify-center py-2.5 gap-0.5 text-[10px] font-medium transition-colors min-h-[56px] ${
            moreOpen ? 'text-teal-400' : 'text-slate-500'
          }`}
        >
          <TabMoreIcon />
          <span>More</span>
        </button>
      </nav>

      {/* Overlay */}
      {moreOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/40 z-40"
          onClick={() => setMoreOpen(false)}
        />
      )}

      {/* More drawer */}
      {moreOpen && (
        <div className="md:hidden fixed bottom-14 left-0 right-0 bg-[#0f172a] z-40 border-t border-white/10 rounded-t-2xl">
          <div className="px-4 pt-3 pb-4">
            <div className="w-8 h-0.5 bg-white/20 rounded-full mx-auto mb-4" />
            <div className="space-y-0.5">
              {moreTabs.map(({ to, label }) => (
                <Link
                  key={to}
                  to={to}
                  className={`flex items-center px-4 py-3.5 rounded-xl text-[14px] font-medium transition-colors ${
                    location.pathname === to
                      ? 'bg-teal-400/15 text-teal-400'
                      : 'text-slate-300 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
