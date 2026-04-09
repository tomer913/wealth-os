import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import CategoryFilter from './CategoryFilter'

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/assets': 'Assets',
  '/accounts': 'Accounts',
  '/transactions': 'Transactions',
  '/valuations': 'Valuations',
  '/fx-rates': 'FX Rates',
  '/reports': 'Reports',
}

export default function AppShell() {
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] ?? 'Wealth OS'

  return (
    // Full height shell: sidebar left, main right
    <div className="flex h-screen overflow-hidden bg-gray-50">

      {/* Sidebar — hidden on mobile, shown md+ */}
      <div className="hidden md:flex">
        <Sidebar />
      </div>

      {/* Main content area */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">

        {/* Top bar */}
        <header className="bg-white border-b border-gray-100 px-5 py-3 flex items-center justify-between flex-shrink-0">
          <div>
            <h1 className="text-[18px] font-medium text-gray-900 tracking-tight">{title}</h1>
            <p className="text-[11px] text-gray-400 mt-0.5">Tomer Portfolio</p>
          </div>
          {/* Mobile: hamburger placeholder (future) */}
          <div className="md:hidden text-gray-400 text-sm">Wealth OS</div>
        </header>

        {/* Category filter chips */}
        <CategoryFilter />

        {/* Page content — scrollable */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>

      </div>

      {/* Mobile bottom tab bar */}
      <MobileTabBar />
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
