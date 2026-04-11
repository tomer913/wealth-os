import { useState, useRef, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import CategoryFilter from './CategoryFilter'
import PortfolioSelector from './PortfolioSelector'
import { useRebuildSnapshot } from '../../hooks/usePortfolio'
import { useAppStore } from '../../store'
import { formatDateTime } from '../../utils/format'

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/assets': 'Assets',
  '/accounts': 'Accounts',
  '/transactions': 'Transactions',
  '/valuations': 'Valuations',
  '/connectors': 'Connectors',
  '/fx-rates': 'FX Rates',
  '/reports': 'Reports',
}

export default function AppShell() {
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] ?? 'Wealth OS'

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
            <PortfolioSelector />
            <BuildSnapshotButton />
            <div className="md:hidden text-gray-400 text-sm">Wealth OS</div>
          </div>
        </header>
        <CategoryFilter />
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
          {isPending ? 'Building…' : 'Build Snapshot'}
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
            Snapshot date
          </p>

          {/* Today option */}
          <button onClick={runToday}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 text-[13px] font-medium text-gray-700 hover:bg-teal-50 hover:text-teal-700 rounded-lg transition-colors mb-1">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <circle cx="7" cy="7" r="5.5"/>
              <path d="M7 4v3l1.5 1.5"/>
            </svg>
            Today (default)
          </button>

          {/* Custom date */}
          <div className="mt-2 pt-2 border-t border-gray-100">
            <p className="text-[11px] text-gray-400 mb-2">Custom date (historical)</p>
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
              Build for {customDate || '…'}
            </button>
          </div>

          {/* Last built info */}
          {lastBuiltAt && (
            <p className="text-[10px] text-gray-400 text-center mt-3">
              Last built: {formatDateTime(lastBuiltAt)}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function MobileTabBar() {
  const location = useLocation()

  const tabs = [
    { to: '/', label: 'Dashboard', icon: '⊞' },
    { to: '/assets', label: 'Assets', icon: '◈' },
    { to: '/transactions', label: 'Txns', icon: '⇄' },
    { to: '/accounts', label: 'Accounts', icon: '▦' },
  ]

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-[#0f172a] border-t border-white/10 flex z-50">
      {tabs.map(({ to, label, icon }) => {
        const isActive = location.pathname === to
        return (
          <a
            key={to}
            href={to}
            className={`flex-1 flex flex-col items-center py-2.5 gap-0.5 text-[10px] transition-colors ${
              isActive ? 'text-teal-400' : 'text-slate-500'
            }`}
          >
            <span className="text-[18px] leading-none">{icon}</span>
            {label}
          </a>
        )
      })}
    </nav>
  )
}
