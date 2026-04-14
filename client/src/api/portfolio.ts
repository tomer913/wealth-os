import apiClient from './client'
import { useAppStore } from '../store'
import { DEFAULT_PORTFOLIO_ID } from '../config/constants'
import type { PortfolioSnapshot, Asset, AssetListResponse, Account, Transaction, ManualValuation, ValuationListResponse, Portfolio } from '../types'

export { DEFAULT_PORTFOLIO_ID }

// Get active portfolio ID from store at call time (no circular dep — store doesn't import api)
function pid(): string {
  return useAppStore.getState().activePortfolioId || DEFAULT_PORTFOLIO_ID
}

// ─── Portfolios ───────────────────────────────────────────────────────────────

export async function getPortfolios(): Promise<Portfolio[]> {
  const { data } = await apiClient.get(`/api/v1/portfolios/`)
  return Array.isArray(data) ? data : []
}

// ─── Snapshot ──────────────────────────────────────────────────────────────────

export async function rebuildSnapshot(asOfDate?: string): Promise<PortfolioSnapshot> {
  const { data } = await apiClient.post(`/api/v1/snapshots/rebuild`, {
    portfolio_id: pid(),
    ...(asOfDate ? { as_of_date: asOfDate } : {}),
  })
  return data
}

export async function getLatestSnapshot(): Promise<PortfolioSnapshot> {
  const { data } = await apiClient.get(`/api/v1/snapshots/latest`, {
    params: { portfolio_id: pid() },
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

// ─── Budget ───────────────────────────────────────────────────────────────────

export async function getBudgetCategories(year?: number) {
  const { data } = await apiClient.get('/api/v1/budget/categories/', {
    params: { portfolio_id: pid(), ...(year ? { year } : {}) },
  })
  return Array.isArray(data) ? data : []
}

export async function getBudgetRules(statusFilter?: string) {
  const { data } = await apiClient.get('/api/v1/budget/rules/', {
    params: { portfolio_id: pid(), ...(statusFilter ? { status: statusFilter } : {}) },
  })
  return Array.isArray(data) ? data : []
}

export async function createBudgetRule(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/api/v1/budget/rules/', payload, {
    params: { portfolio_id: pid() },
  })
  return data
}

export async function updateBudgetRule(id: string, payload: Record<string, unknown>) {
  const { data } = await apiClient.patch(`/api/v1/budget/rules/${id}/`, payload)
  return data
}

export async function deleteBudgetRule(id: string) {
  await apiClient.delete(`/api/v1/budget/rules/${id}/`)
}

export async function approveBudgetRule(id: string) {
  const { data } = await apiClient.post(`/api/v1/budget/rules/${id}/approve/`)
  return data
}

export async function testBudgetRule(id: string) {
  const { data } = await apiClient.post(`/api/v1/budget/rules/${id}/test/`, null, {
    params: { portfolio_id: pid() },
  })
  return data
}

export async function testBudgetConditions(conditions: Record<string, unknown>) {
  const { data } = await apiClient.post('/api/v1/budget/rules/test-conditions/', conditions, {
    params: { portfolio_id: pid() },
  })
  return data
}

export async function getBudgetReviewQueue() {
  const { data } = await apiClient.get('/api/v1/budget/review/', {
    params: { portfolio_id: pid() },
  })
  return Array.isArray(data) ? data : []
}

export async function categorizePendingTx(
  logId: string,
  categoryId: string | null,
  generateRule: boolean,
  excluded = false,
) {
  const body = excluded
    ? { excluded: true }
    : { category_id: categoryId, generate_rule: generateRule }
  const { data } = await apiClient.post(
    `/api/v1/budget/review/${logId}/categorize/`,
    body,
    { params: { portfolio_id: pid() } },
  )
  return data
}

export async function getBudgetSummary(year: number, month?: number) {
  const { data } = await apiClient.get('/api/v1/budget/summary/', {
    params: { portfolio_id: pid(), year, ...(month != null ? { month } : {}) },
  })
  return Array.isArray(data) ? data : []
}

export async function getBudgetPlans(year?: number) {
  const { data } = await apiClient.get('/api/v1/budget/plans/', {
    params: { portfolio_id: pid(), ...(year ? { year } : {}) },
  })
  return Array.isArray(data) ? data : []
}

export async function createBudgetPlan(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/api/v1/budget/plans/', payload, {
    params: { portfolio_id: pid() },
  })
  return data
}

export async function updateBudgetPlan(id: string, payload: Record<string, unknown>) {
  const { data } = await apiClient.patch(`/api/v1/budget/plans/${id}/`, payload)
  return data
}

export async function deleteBudgetPlan(id: string) {
  await apiClient.delete(`/api/v1/budget/plans/${id}/`)
}

export async function generatePlansFromHistory(targetYear: number, sourceMonths = 6) {
  const { data } = await apiClient.post(
    '/api/v1/budget/plans/generate-from-history/',
    { target_year: targetYear, source_months: sourceMonths },
    { params: { portfolio_id: pid() } },
  )
  return data
}

export async function importPlansFromYear(sourceYear: number, targetYear: number) {
  const { data } = await apiClient.post(
    '/api/v1/budget/plans/import-from-year/',
    { source_year: sourceYear, target_year: targetYear },
    { params: { portfolio_id: pid() } },
  )
  return data
}

export async function createBudgetCategory(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/api/v1/budget/categories/', payload, {
    params: { portfolio_id: pid() },
  })
  return data
}

export async function updateBudgetCategory(id: string, payload: Record<string, unknown>) {
  const { data } = await apiClient.patch(`/api/v1/budget/categories/${id}/`, payload)
  return data
}

export async function deleteBudgetCategory(id: string) {
  await apiClient.delete(`/api/v1/budget/categories/${id}/`)
}

// ─── Processors ───────────────────────────────────────────────────────────────

export async function getProcessorRuns(processorName?: string, limit = 50) {
  const { data } = await apiClient.get('/api/v1/processors/runs/', {
    params: { portfolio_id: pid(), ...(processorName ? { processor_name: processorName } : {}), limit },
  })
  return Array.isArray(data) ? data : []
}

export async function triggerProcessorRun(processorName: string): Promise<{ run_id: string; status: string; processor: string }> {
  const { data } = await apiClient.post('/api/v1/processors/run', null, {
    params: { processor_name: processorName, portfolio_id: pid() },
  })
  return data
}

export async function getProcessorRun(runId: string): Promise<{
  id: string; status: string; rows_read: number | null; rows_written: number | null;
  rows_skipped: number | null; error_message: string | null; finished_at: string | null;
}> {
  const { data } = await apiClient.get(`/api/v1/processors/runs/${runId}`)
  return data
}

export async function getRecentSnapshots(limit = 5): Promise<{
  snapshot_date: string; asset_count: number; built_at: string | null;
}[]> {
  const { data } = await apiClient.get('/api/v1/snapshots/recent', {
    params: { portfolio_id: pid(), limit },
  })
  return Array.isArray(data) ? data : []
}

export async function resetProcessorCheckpoint(processorName: string) {
  const { data } = await apiClient.post('/api/v1/processors/reset-checkpoint', null, {
    params: { processor_name: processorName, portfolio_id: pid() },
  })
  return data
}

export async function triggerSnapshotRebuild() {
  const { data } = await apiClient.post('/api/v1/snapshots/rebuild', {
    portfolio_id: pid(),
  })
  return data
}

export async function uploadBankStatement(
  connectorType: string,
  portfolioId: string,
  file: File,
): Promise<{ created: number; skipped: number; total: number; connector_name: string; source: string }> {
  const form = new FormData()
  form.append('connector_type', connectorType)
  form.append('portfolio_id', portfolioId)
  form.append('file', file)
  const { data } = await apiClient.post('/api/v1/connectors/upload/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return data
}
