import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getLatestSnapshot, rebuildSnapshot, getAssets, getAccounts, getTransactions } from '../api/portfolio'
import { useAppStore } from '../store'

// ─── Query keys ────────────────────────────────────────────────────────────────
export const queryKeys = {
  snapshot: ['snapshot'] as const,
  assets: ['assets'] as const,
  accounts: ['accounts'] as const,
  transactions: (params?: object) => ['transactions', params] as const,
}

// ─── Category filter helper ────────────────────────────────────────────────────
// Returns selected categories — empty array means "All" (no filter)
export function useCategoryFilter() {
  return useAppStore((s) => s.selectedCategories)
}

// ─── Snapshot ──────────────────────────────────────────────────────────────────
export function useSnapshot() {
  const setSnapshot = useAppStore((s) => s.setSnapshot)
  const activePortfolioId = useAppStore((s) => s.activePortfolioId)

  return useQuery({
    queryKey: [...queryKeys.snapshot, activePortfolioId],
    queryFn: async () => {
      const data = await getLatestSnapshot()
      if (data) setSnapshot(data)
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useRebuildSnapshot() {
  const queryClient = useQueryClient()
  const setSnapshot = useAppStore((s) => s.setSnapshot)
  const activePortfolioId = useAppStore((s) => s.activePortfolioId)

  return useMutation({
    mutationFn: rebuildSnapshot,
    onSuccess: (data) => {
      if (data) {
        setSnapshot(data)
        // Update cache so navigation away+back shows fresh data
        queryClient.setQueryData([...queryKeys.snapshot, activePortfolioId], data)
        // Also invalidate so next background fetch uses GET /latest
        queryClient.invalidateQueries({ queryKey: queryKeys.snapshot })
      }
    },
  })
}

// ─── Assets ───────────────────────────────────────────────────────────────────
export function useAssets() {
  return useQuery({
    queryKey: queryKeys.assets,
    queryFn: () => getAssets({ limit: 500 }),
    staleTime: 10 * 60 * 1000,
  })
}

// ─── Accounts ─────────────────────────────────────────────────────────────────
export function useAccounts() {
  return useQuery({
    queryKey: queryKeys.accounts,
    queryFn: getAccounts,
    staleTime: 10 * 60 * 1000,
  })
}

// ─── Transactions ─────────────────────────────────────────────────────────────
export function useTransactions(params?: { asset_id?: string; limit?: number }) {
  return useQuery({
    queryKey: queryKeys.transactions(params),
    queryFn: () => getTransactions(params),
    staleTime: 5 * 60 * 1000,
  })
}
