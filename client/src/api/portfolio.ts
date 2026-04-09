import apiClient from './client'
import type { PortfolioSnapshot, Asset, Account, Transaction } from '../types'

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

export async function getAssets(): Promise<Asset[]> {
  const { data } = await apiClient.get(`/api/v1/assets`, {
    params: { portfolio_id: PORTFOLIO_ID },
  })
  return data
}

// ─── Accounts ─────────────────────────────────────────────────────────────────

export async function getAccounts(): Promise<Account[]> {
  const { data } = await apiClient.get(`/api/v1/accounts`, {
    params: { portfolio_id: PORTFOLIO_ID },
  })
  return data
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
