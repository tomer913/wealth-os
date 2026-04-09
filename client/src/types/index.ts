// Snapshot (matches actual POST /api/v1/snapshots/rebuild response)

export interface SnapshotSummary {
  total_value_ils: number
  total_invested_ils: number
  total_return_ils: number
  total_return_pct: number
  total_debt_ils: number
  net_equity_ils: number
  asset_count: number
  warnings: number
}

export interface CategorySummary {
  category: string
  current_value_ils: number
  gross_invested_ils: number
  total_return_ils: number
  total_return_pct: number | null
  asset_count: number
}

export interface AssetResult {
  symbol: string
  name: string
  category: string
  model: string
  current_value_ils: number
  cost_basis_ils?: number
  total_return_ils?: number
  total_return_pct: number | null
  xirr_pct: number | null
  confidence: string
  warnings: string[]
}

export interface PortfolioSnapshot {
  status: string
  mode: string
  snapshot_date: string
  portfolio_id: string
  summary: SnapshotSummary
  categories: CategorySummary[]
  assets: AssetResult[]
  built_at?: string
}

export interface Asset {
  id: string
  name: string
  ticker: string | null
  category: string
  account_id: string | null
  currency: string
  data_source: string | null
  is_active: boolean
  created_at: string
}

export interface Account {
  id: string
  name: string
  institution: string | null
  account_type: string | null
  currency: string
  is_active: boolean
}

export interface Transaction {
  id: string
  asset_id: string
  account_id: string | null
  transaction_type: string
  date: string
  quantity: number | null
  price: number | null
  amount: number
  currency: string
  notes: string | null
}

export type CategoryFilter = string[]

export const CATEGORY_COLORS: Record<string, string> = {
  real_estate:   '#3b82f6',
  pension:       '#8b5cf6',
  securities:    '#10b981',
  alternatives:  '#f59e0b',
  cash:          '#94a3b8',
  crypto:        '#ef4444',
  mutual_fund:   '#06b6d4',
  etf:           '#84cc16',
  energy_income: '#f97316',
}
