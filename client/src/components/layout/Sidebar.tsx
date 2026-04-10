import { NavLink } from 'react-router-dom'
import clsx from 'clsx'
import { useRebuildSnapshot } from '../../hooks/usePortfolio'
import { useAppStore } from '../../store'
import { formatDateTime } from '../../utils/format'
import { isEnabled } from '../../config/features'

const NAV_MAIN = [
  { to: '/',             label: 'Dashboard',    icon: IconDashboard,    flag: 'dashboard'         },
  { to: '/assets',       label: 'Assets',       icon: IconAssets,       flag: 'assets_page'       },
  { to: '/accounts',     label: 'Accounts',     icon: IconAccounts,     flag: 'accounts_page'     },
  { to: '/transactions', label: 'Transactions', icon: IconTransactions, flag: 'transactions_page' },
] as const

const NAV_ANALYSIS = [
  { to: '/valuations', label: 'Valuations', icon: IconChart,   flag: 'valuations_page' },
  { to: '/fx-rates',   label: 'FX Rates',   icon: IconFX,      flag: 'fx_rates_page'   },
  { to: '/reports',    label: 'Reports',    icon: IconReports, flag: 'reports_page'    },
] as const

export default function Sidebar() {
  const { mutate: rebuild, isPending } = useRebuildSnapshot()
  const lastBuiltAt = useAppStore((s) => s.lastBuiltAt)

  return (
    <aside className="flex flex-col w-[200px] min-w-[200px] bg-sidebar-bg h-full">
      {/* Logo */}
      <div className="px-4 pt-5 pb-4 border-b border-sidebar-border">
        <div className="w-8 h-8 rounded-lg bg-brand flex items-center justify-center mb-3">
          <IconLogo />
        </div>
        <div className="text-[15px] font-medium text-slate-100 tracking-tight">Wealth OS</div>
        <div className="text-[11px] text-slate-500 mt-0.5">Portfolio Intelligence</div>
      </div>

      {/* Main nav */}
      <nav className="flex-1 py-2">
        <SectionLabel>Main</SectionLabel>
        {NAV_MAIN.filter(n => isEnabled(n.flag)).map(({ to, label, icon: Icon }) => (
          <NavItem key={to} to={to} label={label} Icon={Icon} end={to === '/'} />
        ))}

        <SectionLabel className="mt-3">Analysis</SectionLabel>
        {NAV_ANALYSIS.filter(n => isEnabled(n.flag)).map(({ to, label, icon: Icon }) => (
          <NavItem key={to} to={to} label={label} Icon={Icon} />
        ))}
      </nav>

      {/* Bottom: rebuild button */}
      <div className="p-4 border-t border-sidebar-border">
        <button
          onClick={() => rebuild()}
          disabled={isPending}
          className={clsx(
            'w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-[12px] font-medium transition-colors',
            isPending
              ? 'bg-brand/50 text-white cursor-wait'
              : 'bg-brand hover:bg-brand-light text-white',
          )}
        >
          <IconRebuild spinning={isPending} />
          {isPending ? 'Building…' : 'Build Snapshot'}
        </button>
        <p className="text-[10px] text-slate-500 text-center mt-1.5">
          {lastBuiltAt ? `Built ${formatDateTime(lastBuiltAt)}` : 'Not yet built'}
        </p>
      </div>
    </aside>
  )
}

function SectionLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p className={clsx('px-4 pt-3 pb-1 text-[10px] uppercase tracking-widest text-slate-600', className)}>
      {children}
    </p>
  )
}

function NavItem({ to, label, Icon, end }: { to: string; label: string; Icon: React.FC; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-2.5 px-4 py-2 text-[13px] transition-colors border-r-2',
          isActive
            ? 'bg-sidebar-active text-sidebar-text-active border-brand'
            : 'text-sidebar-text hover:bg-sidebar-hover border-transparent',
        )
      }
    >
      <span className="w-4 h-4 flex-shrink-0 opacity-70">
        <Icon />
      </span>
      {label}
    </NavLink>
  )
}

// ─── Icons ─────────────────────────────────────────────────────────────────────
function IconLogo() {
  return (
    <svg viewBox="0 0 16 16" fill="white" width="16" height="16">
      <path d="M8 2L13 5V11L8 14L3 11V5L8 2Z" />
    </svg>
  )
}
function IconDashboard() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor">
      <rect x="1" y="1" width="6" height="6" rx="1" />
      <rect x="9" y="1" width="6" height="6" rx="1" />
      <rect x="1" y="9" width="6" height="6" rx="1" />
      <rect x="9" y="9" width="6" height="6" rx="1" />
    </svg>
  )
}
function IconAssets() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="6" r="3" />
      <path d="M2 14c0-3.3 2.7-6 6-6s6 2.7 6 6" />
    </svg>
  )
}
function IconAccounts() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="3" width="12" height="10" rx="1" />
      <path d="M5 3V2M11 3V2M2 7h12" />
    </svg>
  )
}
function IconTransactions() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 5h12M2 11h12M5 2l-3 3 3 3M11 8l3 3-3 3" />
    </svg>
  )
}
function IconChart() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <polyline points="2,12 6,7 9,10 14,4" />
    </svg>
  )
}
function IconFX() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4v8M5 6h4a1 1 0 010 2H6a1 1 0 000 2h5" />
    </svg>
  )
}
function IconReports() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="2" width="12" height="12" rx="1" />
      <path d="M5 6h6M5 9h6M5 12h3" />
    </svg>
  )
}
function IconRebuild({ spinning }: { spinning: boolean }) {
  return (
    <svg
      viewBox="0 0 13 13"
      width="13"
      height="13"
      fill="none"
      stroke="white"
      strokeWidth="2"
      style={spinning ? { animation: 'spin 1s linear infinite' } : undefined}
    >
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <path d="M11 6.5A4.5 4.5 0 1 1 6.5 2" strokeLinecap="round" />
      <polyline points="6.5,2 9,2 9,4.5" />
    </svg>
  )
}
