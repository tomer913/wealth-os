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

// Formats as "₪ 16,088,735" — always ILS (for portfolio values)
export function formatILS(n: number): string {
  const abs = ILS_NUM.format(Math.abs(Math.round(n)))
  return n < 0 ? `-₪ ${abs}` : `₪ ${abs}`
}

export function formatILSShort(n: number): string {
  const abs = ILS_NUM_SHORT.format(Math.abs(n))
  return n < 0 ? `-₪ ${abs}` : `₪ ${abs}`
}

// Currency-aware formatter — use for asset/transaction amounts in native currency
const CURRENCY_SYMBOLS: Record<string, string> = {
  ILS: '₪', USD: '$', EUR: '€', GBP: '£',
  JPY: '¥', CHF: 'Fr', CAD: 'CA$', AUD: 'A$',
}

export function formatCurrency(n: number, currency = 'ILS'): string {
  const symbol = CURRENCY_SYMBOLS[currency.toUpperCase()] ?? currency
  const fmt = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })
  const abs = fmt.format(Math.abs(n))
  return n < 0 ? `-${symbol} ${abs}` : `${symbol} ${abs}`
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

export function categoryLabel(raw: string, t: (key: string, defaultValue: string) => string): string {
  return t(`categories.${raw.toLowerCase()}`, raw)
}

// ─── Class helpers ─────────────────────────────────────────────────────────────

export function gainClass(n: number | null): string {
  if (n == null) return 'text-gray-400'
  return n >= 0 ? 'text-emerald-600' : 'text-rose-600'
}
