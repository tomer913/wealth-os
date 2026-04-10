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
  symbol: string
  asset_behavior: string
  category: string | null
  asset_type: string | null
  sub_type: string | null
  status: string
  lifecycle_stage: string
  exchange: string | null
  currency: string
  country: string | null
  sector: string | null
  current_price: number | null
  price_updated_at: string | null
  pricing_mode: string
  is_manual: boolean
  extra_data: Record<string, unknown> | null
  portfolio_id: string
  account_id: string | null
  created_at: string
  updated_at: string
}

export interface AssetListResponse {
  items: Asset[]
  total: number
  page: number
  limit: number
  pages: number
}

export interface Account {
  id: string
  name: string
  symbol: string
  institution: string | null
  custodian: string | null
  account_type: string | null
  category: string | null
  currency: string
  is_liquid: boolean
  is_income_generating: boolean
  include_in_portfolio: boolean
  status: string
  cash_balance: number
  opening_balance: number | null
  extra_data: Record<string, unknown> | null
  notes: string | null
  portfolio_id: string
  created_at: string
  updated_at: string
  position_count: number  // server-computed via LEFT JOIN on assets
}

export interface Transaction {
  id: string
  portfolio_id: string
  account_id: string | null
  asset_id: string | null
  transaction_date: string
  effective_date: string | null
  type: string
  economic_type: string | null
  domain: string | null
  subtype: string | null
  total_amount: number | null
  cashflow_amount: number | null
  currency: string
  fees: number
  tax: number
  quantity: number | null
  price_per_unit: number | null
  units_delta: number
  from_account_id: string | null
  to_account_id: string | null
  is_internal_transfer: boolean
  status: string
  source: string
  notes: string | null
  external_reference_id: string | null
  created_at: string
  updated_at: string
}

export interface ManualValuation {
  id: string
  portfolio_id: string
  asset_id: string
  account_id: string | null
  valuation_date: string
  market_value: number
  currency: string
  fx_rate_to_ils: number
  value_ils: number | null
  valuation_method: string
  confidence_level: string
  valuation_source: string | null
  is_estimated: boolean
  notes: string | null
  source: string
  created_at: string
  updated_at: string
}

export interface ValuationListResponse {
  items: ManualValuation[]
  total: number
  page: number
  limit: number
  pages: number
}

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
