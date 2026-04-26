import { useEffect, useRef, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getPortfolios, selectPortfolio } from '../../api/portfolio'
import { useAppStore } from '../../store'
import { isEnabled } from '../../config/features'
import clsx from 'clsx'

export default function PortfolioSelector() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { t } = useTranslation('settings')
  const activeId = useAppStore((s) => s.activePortfolioId)
  const setActivePortfolioId = useAppStore((s) => s.setActivePortfolioId)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data: portfolios = [], isSuccess } = useQuery({
    queryKey: ['portfolios'],
    queryFn: getPortfolios,
    staleTime: 10 * 60 * 1000,
  })

  // Auto-select portfolio from localStorage or first returned
  useEffect(() => {
    if (!isSuccess || portfolios.length === 0) return

    // New user with no portfolios → redirect to setup
    if (portfolios.length === 0 && isEnabled('auth_enabled')) {
      navigate('/setup')
      return
    }

    const stored = localStorage.getItem('last_portfolio_id')
    const defaultPortfolio =
      portfolios.find((p) => p.is_default) ||
      portfolios.find((p) => p.id === stored) ||
      portfolios[0]

    if (defaultPortfolio && defaultPortfolio.id !== activeId) {
      setActivePortfolioId(defaultPortfolio.id)
      localStorage.setItem('last_portfolio_id', defaultPortfolio.id)
    }
  }, [isSuccess, portfolios.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const active = portfolios.find((p) => p.id === activeId)

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  async function select(id: string) {
    if (id === activeId) { setOpen(false); return }
    setActivePortfolioId(id)
    localStorage.setItem('last_portfolio_id', id)
    // Notify backend of last-accessed for session restore
    try { await selectPortfolio(id) } catch { /* non-critical */ }
    // Invalidate all data queries so they refetch with new portfolio_id
    qc.invalidateQueries({ queryKey: ['snapshot'] })
    qc.invalidateQueries({ queryKey: ['assets'] })
    qc.invalidateQueries({ queryKey: ['accounts'] })
    qc.invalidateQueries({ queryKey: ['transactions'] })
    qc.invalidateQueries({ queryKey: ['valuations'] })
    setOpen(false)
  }

  if (portfolios.length <= 1 && !open) {
    // If only one portfolio, show as static label — no need for dropdown
    return (
      <span className="text-[13px] font-medium text-gray-700">
        {active?.name ?? 'Loading…'}
      </span>
    )
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[13px] font-medium transition-colors',
          open
            ? 'border-teal-400 bg-teal-50 text-teal-700'
            : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300',
        )}
      >
        <span className="w-2 h-2 rounded-full bg-teal-500 flex-shrink-0" />
        <span className="max-w-[160px] truncate">{active?.name ?? 'Select portfolio'}</span>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8"
          strokeLinecap="round" strokeLinejoin="round"
          style={{ transform: open ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.15s' }}>
          <path d="M2 4l4 4 4-4"/>
        </svg>
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-white border border-gray-200 rounded-xl shadow-lg z-50 overflow-hidden">
          {portfolios.map((p) => (
            <button
              key={p.id}
              onClick={() => select(p.id)}
              className={clsx(
                'w-full flex items-center gap-2.5 px-4 py-3 text-left transition-colors border-b border-gray-50 last:border-0',
                p.id === activeId
                  ? 'bg-teal-50 text-teal-700'
                  : 'text-gray-700 hover:bg-gray-50',
              )}
            >
              <span className={clsx('w-2 h-2 rounded-full flex-shrink-0',
                p.id === activeId ? 'bg-teal-500' : 'bg-gray-300')} />
              <div className="flex-1 min-w-0">
                <div className="text-[13px] font-medium truncate">{p.name}</div>
                {p.description && (
                  <div className="text-[11px] text-gray-400 truncate">{p.description}</div>
                )}
                <div className="text-[11px] text-gray-400">{p.base_currency}</div>
              </div>
              {p.id === activeId && (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#0d9488" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2 7l3.5 3.5L12 3"/>
                </svg>
              )}
            </button>
          ))}
          <div className="border-t border-gray-100 px-4 py-2">
            <Link
              to="/settings"
              onClick={() => setOpen(false)}
              className="text-[12px] text-teal-600 hover:text-teal-700 font-medium transition-colors"
            >
              {t('manage_link')}
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
