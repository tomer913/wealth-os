import apiClient from './client'
import type { PortfolioSnapshot, Asset, AssetListResponse, Account, Transaction } from '../types'

// Your portfolio UUID — move to .env if you add multi-user later
const PORTFOLIO_ID = (import.meta.env.VITE_PORTFOLIO_ID || '53f8f313-98e8-5de3-bd64-55826cbd82bb').trim()

// ─── Snapshot ──────────────────────────────────────────────────────────────────

export async function rebuildSnapshot(): Promise<PortfolioSnapshot> {
  const { data } = await apiClient.post(`/api/v1/snapshots/rebuild`, {
    portfolio_id: PORTFOLIO_ID,
  })
  return data
}

export async function getLatestSnapshot(): Promise<PortfolioSnapshot> {
  // If you have a GET endpoint for cached snapshot, use it here.
  // For now we call rebuild (you can swap this later without touching components).
  const { data } = await apiClient.post(`/api/v1/snapshots/rebuild`, {
    portfolio_id: PORTFOLIO_ID,
  })
  return data
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
    params: { portfolio_id: PORTFOLIO_ID, limit: 500, ...params },
  })
  return data
}

export async function createAsset(payload: Record<string, unknown>): Promise<Asset> {
  const { data } = await apiClient.post(`/api/v1/assets/`, {
    ...payload,
    portfolio_id: PORTFOLIO_ID,
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
    params: { portfolio_id: PORTFOLIO_ID },
  })
  return Array.isArray(data) ? data : (data.items ?? data.accounts ?? [])
}

export async function createAccount(payload: Record<string, unknown>): Promise<Account> {
  const { data } = await apiClient.post(`/api/v1/accounts/`, {
    ...payload,
    portfolio_id: PORTFOLIO_ID,
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

// ─── Transactions ─────────────────────────────────────────────────────────────

export async function getTransactions(params?: {
  asset_id?: string
  account_id?: string
  limit?: number
  offset?: number
}): Promise<Transaction[]> {
  const { data } = await apiClient.get(`/api/v1/transactions`, {
    params: { portfolio_id: PORTFOLIO_ID, ...params },
  })
  return data
}
