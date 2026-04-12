import { create } from 'zustand'
import type { PortfolioSnapshot } from '../types'
import { DEFAULT_PORTFOLIO_ID } from '../config/constants'

interface AppStore {
  // Active portfolio
  activePortfolioId: string
  setActivePortfolioId: (id: string) => void

  // Category filter — empty array means "All"
  selectedCategories: string[]
  setCategories: (cats: string[]) => void
  toggleCategory: (cat: string) => void
  clearFilter: () => void

  // Last built snapshot (cached in memory)
  snapshot: PortfolioSnapshot | null
  setSnapshot: (s: PortfolioSnapshot) => void
  lastBuiltAt: string | null

  // Budget view state
  activeBudgetYear: number
  activeBudgetMonth: number
  budgetViewMode: 'monthly' | 'annual'
  setActiveBudgetYear: (year: number) => void
  setActiveBudgetMonth: (month: number) => void
  setBudgetViewMode: (mode: 'monthly' | 'annual') => void
}

const now = new Date()

export const useAppStore = create<AppStore>((set, get) => ({
  activePortfolioId: DEFAULT_PORTFOLIO_ID,
  setActivePortfolioId: (id) => set({ activePortfolioId: id, snapshot: null, lastBuiltAt: null }),

  selectedCategories: [],
  setCategories: (cats) => set({ selectedCategories: cats }),
  toggleCategory: (cat) => {
    const current = get().selectedCategories
    if (current.includes(cat)) {
      set({ selectedCategories: current.filter((c) => c !== cat) })
    } else {
      set({ selectedCategories: [...current, cat] })
    }
  },
  clearFilter: () => set({ selectedCategories: [] }),

  snapshot: null,
  setSnapshot: (s) => set({ snapshot: s, lastBuiltAt: s.built_at ?? new Date().toISOString() }),
  lastBuiltAt: null,

  // Budget
  activeBudgetYear: now.getFullYear(),
  activeBudgetMonth: now.getMonth() + 1,
  budgetViewMode: 'monthly',
  setActiveBudgetYear: (year) => set({ activeBudgetYear: year }),
  setActiveBudgetMonth: (month) => set({ activeBudgetMonth: month }),
  setBudgetViewMode: (mode) => set({ budgetViewMode: mode }),
}))

// ─── Selector helpers ─────────────────────────────────────────────────────────

export function useFilteredAssets() {
  return useAppStore((s) => {
    if (!s.snapshot) return []
    if (s.selectedCategories.length === 0) return s.snapshot.assets
    return s.snapshot.assets.filter((a) => s.selectedCategories.includes(a.category))
  })
}

export function useFilteredCategories() {
  return useAppStore((s) => {
    if (!s.snapshot) return []
    if (s.selectedCategories.length === 0) return s.snapshot.categories
    return s.snapshot.categories.filter((c) => s.selectedCategories.includes(c.category))
  })
}

export function useFilteredSummary() {
  return useAppStore((s) => {
    if (!s.snapshot) return null
    if (s.selectedCategories.length === 0) return s.snapshot.summary

    // Filter categories and sum from category data (has gross_invested_ils)
    const filteredCats = s.snapshot.categories.filter((c) =>
      s.selectedCategories.includes(c.category)
    )

    const total_value_ils = filteredCats.reduce((sum, c) => sum + (c.current_value_ils ?? 0), 0)
    const total_invested_ils = filteredCats.reduce((sum, c) => sum + (c.gross_invested_ils ?? 0), 0)
    const total_return_ils = filteredCats.reduce((sum, c) => sum + (c.total_return_ils ?? 0), 0)
    const total_return_pct = total_invested_ils > 0 ? total_return_ils / total_invested_ils : 0

    // Debt only applies to real_estate — preserve from full summary if not filtering RE
    const includesRealEstate = s.selectedCategories.includes('real_estate')
    const total_debt_ils = includesRealEstate ? s.snapshot.summary.total_debt_ils : 0

    return {
      ...s.snapshot.summary,
      total_value_ils,
      total_invested_ils,
      total_return_ils,
      total_return_pct,
      total_debt_ils,
      net_equity_ils: total_value_ils - total_debt_ils,
      asset_count: filteredCats.reduce((sum, c) => sum + c.asset_count, 0),
    }
  })
}
