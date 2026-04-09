import { create } from 'zustand'
import type { PortfolioSnapshot } from '../types'

interface AppStore {
  // Category filter — empty array means "All"
  selectedCategories: string[]
  setCategories: (cats: string[]) => void
  toggleCategory: (cat: string) => void
  clearFilter: () => void

  // Last built snapshot (cached in memory)
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
  setSnapshot: (s) => set({ snapshot: s, lastBuiltAt: s.built_at }),
  lastBuiltAt: null,
}))

// ─── Selector helpers (use these in components) ────────────────────────────────

// Returns filtered assets based on selected categories
export function useFilteredAssets() {
  return useAppStore((s) => {
    if (!s.snapshot) return []
    if (s.selectedCategories.length === 0) return s.snapshot.assets
    return s.snapshot.assets.filter((a) =>
      s.selectedCategories.includes(a.category),
    )
  })
}

// Returns filtered categories
export function useFilteredCategories() {
  return useAppStore((s) => {
    if (!s.snapshot) return []
    if (s.selectedCategories.length === 0) return s.snapshot.categories
    return s.snapshot.categories.filter((c) =>
      s.selectedCategories.includes(c.category),
    )
  })
}

// Returns summary — recalculated when filter is active
export function useFilteredSummary() {
  return useAppStore((s) => {
    if (!s.snapshot) return null
    if (s.selectedCategories.length === 0) return s.snapshot.summary

    const filtered = s.snapshot.assets.filter((a) =>
      s.selectedCategories.includes(a.category),
    )

    const total_value = filtered.reduce((sum, a) => sum + a.current_value, 0)
    const total_cost = filtered.reduce((sum, a) => sum + a.cost_basis, 0)
    const total_gain = total_value - total_cost
    const return_pct = total_cost > 0 ? (total_gain / total_cost) * 100 : 0

    return {
      ...s.snapshot.summary,
      total_value,
      total_cost_basis: total_cost,
      total_gain_loss: total_gain,
      total_return_pct: return_pct,
      xirr: null, // can't recalculate XIRR client-side
    }
  })
}
