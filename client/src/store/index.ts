import { create } from 'zustand'
import type { PortfolioSnapshot } from '../types'

interface AppStore {
  selectedCategories: string[]
  setCategories: (cats: string[]) => void
  toggleCategory: (cat: string) => void
  clearFilter: () => void
  snapshot: PortfolioSnapshot | null
  setSnapshot: (s: PortfolioSnapshot) => void
  lastBuiltAt: string | null
}

export const useAppStore = create<AppStore>((set, get) => ({
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

    const filtered = s.snapshot.assets.filter((a) =>
      s.selectedCategories.includes(a.category),
    )

    const total_value_ils = filtered.reduce((sum, a) => sum + (a.current_value_ils ?? 0), 0)
    const total_invested_ils = filtered.reduce((sum, a) => sum + (a.cost_basis_ils ?? 0), 0)
    const total_return_ils = total_value_ils - total_invested_ils
    const total_return_pct = total_invested_ils > 0 ? total_return_ils / total_invested_ils : 0

    return {
      ...s.snapshot.summary,
      total_value_ils,
      total_invested_ils,
      total_return_ils,
      total_return_pct,
    }
  })
}
