// Feature flags — control which features/screens are visible
// v1: simple config file
// v2: fetch from backend per portfolio/plan (drop-in replacement, no component changes needed)

export const FEATURES = {
  // Pages
  dashboard:        true,
  assets_page:      true,
  accounts_page:    true,
  transactions_page: true,
  valuations_page:  false,
  fx_rates_page:    false,
  reports_page:     false,

  // Dashboard widgets
  widget_kpi_cards:     true,
  widget_chart:         true,
  widget_donut:         true,
  widget_top_holdings:  true,
  widget_gainers_losers: true,

  // Features within pages
  asset_json_import:    true,
  asset_opening_data:   true,   // creates ManualValuation + BUY transaction on create
  account_json_import:  true,
  pagination:           true,

  // Future / SaaS
  portfolio_selector:   false,
  multi_user:           false,
  export_reports:       false,
  ai_recommendations:   false,
} as const

export type FeatureKey = keyof typeof FEATURES

// Helper — use this in components: if (!isEnabled('reports_page')) return null
export function isEnabled(key: FeatureKey): boolean {
  return FEATURES[key]
}
