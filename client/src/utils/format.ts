// ─── Number formatting ─────────────────────────────────────────────────────────

const ILS_NUM = new Intl.NumberFormat('en-IL', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

const ILS_NUM_SHORT = new Intl.NumberFormat('en-IL', {
  notation: 'compact',
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

// Formats as "₪ 16,088,735" — symbol prefix with space, like Base44
export function formatILS(n: number): string {
  const abs = ILS_NUM.format(Math.abs(Math.round(n)))
  return n < 0 ? `-₪ ${abs}` : `₪ ${abs}`
}

export function formatILSShort(n: number): string {
  const abs = ILS_NUM_SHORT.format(Math.abs(n))
  return n < 0 ? `-₪ ${abs}` : `₪ ${abs}`
}

export function formatPct(n: number | null, decimals = 1): string {
  if (n == null) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(decimals)}%`
}

export function formatPctPlain(n: number, decimals = 1): string {
  return `${n.toFixed(decimals)}%`
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat('en-US').format(Math.round(n))
}

// ─── Date formatting ───────────────────────────────────────────────────────────

export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-IL', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('en-IL', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ─── Category display helpers ─────────────────────────────────────────────────

export function categoryLabel(raw: string): string {
  const map: Record<string, string> = {
    real_estate:   'Real Estate',
    pension:       'Pension',
    securities:    'Stocks',
    alternatives:  'Alternatives',
    cash:          'Cash',
    crypto:        'Crypto',
    mutual_fund:   'Mutual Fund',
    etf:           'ETF',
    energy_income: 'Energy Income',
  }
  return map[raw.toLowerCase()] ?? raw
}

// ─── Class helpers ─────────────────────────────────────────────────────────────

export function gainClass(n: number | null): string {
  if (n == null) return 'text-gray-400'
  return n >= 0 ? 'text-emerald-600' : 'text-rose-600'
}
