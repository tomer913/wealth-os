import apiClient from './client'
import type { PortfolioSnapshot, Asset, AssetListResponse, Account, Transaction, ManualValuation, ValuationListResponse, Portfolio } from '../types'

// Default portfolio from env var
export const DEFAULT_PORTFOLIO_ID = (import.meta.env.VITE_PORTFOLIO_ID || '53f8f313-98e8-5de3-bd64-55826cbd82bb').trim()

// Late-binding getter — avoids circular dependency with store
// The store module is fully initialized by the time any API function is called
function pid(): string {
  // Dynamically access store state without importing at module level
  const store = (window as unknown as { __wealthOsStore?: { getState: () => { activePortfolioId: string } } }).__wealthOsStore
  return store?.getState().activePortfolioId || DEFAULT_PORTFOLIO_ID
}

// ─── Portfolios ───────────────────────────────────────────────────────────────

export async function getPortfolios(): Promise<Portfolio[]> {
  const { data } = await apiClient.get(`/api/v1/portfolios/`)
  return Array.isArray(data) ? data : []
}

// ─── Snapshot ──────────────────────────────────────────────────────────────────

export async function rebuildSnapshot(): Promise<PortfolioSnapshot> {
  const { data } = await apiClient.post(`/api/v1/snapshots/rebuild`, {
    portfolio_id: pid(),
  })
  return data
}

export async function getLatestSnapshot(): Promise<PortfolioSnapshot | null> {
  // Reads from DB — fast, no engine computation
  const { data } = await apiClient.get(`/api/v1/snapshots/latest`, {
    params: { portfolio_id: pid() },
  })
  return data  // null if no snapshot built yet
}

// ─── Assets ───────────────────────────────────────────────────────────────────

export async function getAssets(params?: {
  page?: number
  limit?: number
  search?: string
  category?: string
  status?: string
}): Promise<AssetListResponse> {
  const { data } = await apiClient.get(`/api/v1/assets/`, {
    params: { portfolio_id: pid(), limit: 500, ...params },
  })
  return data
}

export async function createAsset(payload: Record<string, unknown>): Promise<Asset> {
  const { data } = await apiClient.post(`/api/v1/assets/`, {
    ...payload,
    portfolio_id: pid(),
  })
  return data
}

export async function updateAsset(id: string, payload: Record<string, unknown>): Promise<Asset> {
  const { data } = await apiClient.patch(`/api/v1/assets/${id}`, payload)
  return data
}

export async function deleteAsset(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/assets/${id}`)
}

// ─── Accounts ─────────────────────────────────────────────────────────────────

export async function getAccounts(): Promise<Account[]> {
  const { data } = await apiClient.get(`/api/v1/accounts/`, {
    params: { portfolio_id: pid() },
  })
  return Array.isArray(data) ? data : (data.items ?? data.accounts ?? [])
}

export async function createAccount(payload: Record<string, unknown>): Promise<Account> {
  const { data } = await apiClient.post(`/api/v1/accounts/`, {
    ...payload,
    portfolio_id: pid(),
  })
  return data
}

export async function updateAccount(id: string, payload: Record<string, unknown>): Promise<Account> {
  const { data } = await apiClient.patch(`/api/v1/accounts/${id}`, payload)
  return data
}

export async function deleteAccount(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/accounts/${id}`)
}

// ─── Valuations ───────────────────────────────────────────────────────────────

export async function getValuations(params?: {
  asset_id?: string
  account_id?: string
  date_from?: string
  date_to?: string
  page?: number
  limit?: number
}): Promise<ValuationListResponse> {
  const { data } = await apiClient.get(`/api/v1/valuations/`, {
    params: { portfolio_id: pid(), limit: 50, ...params },
  })
  return data
}

export async function createValuation(payload: Record<string, unknown>): Promise<ManualValuation> {
  const { data } = await apiClient.post(`/api/v1/valuations/`, {
    ...payload,
    portfolio_id: pid(),
  })
  return data
}

export async function updateValuation(id: string, payload: Record<string, unknown>): Promise<ManualValuation> {
  const { data } = await apiClient.patch(`/api/v1/valuations/${id}`, payload)
  return data
}

export async function deleteValuation(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/valuations/${id}`)
}

export async function getTransactions(params?: {
  asset_id?: string
  account_id?: string
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
}): Promise<Transaction[]> {
  const { data } = await apiClient.get(`/api/v1/transactions/`, {
    params: { portfolio_id: pid(), limit: 500, ...params },
  })
  return Array.isArray(data) ? data : []
}

export async function createTransaction(payload: Record<string, unknown>): Promise<Transaction> {
  const { data } = await apiClient.post(`/api/v1/transactions/`, {
    ...payload,
    portfolio_id: pid(),
  })
  return data
}

export async function updateTransaction(id: string, payload: Record<string, unknown>): Promise<Transaction> {
  const { data } = await apiClient.patch(`/api/v1/transactions/${id}`, payload)
  return data
}

export async function deleteTransaction(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/transactions/${id}`)
}
