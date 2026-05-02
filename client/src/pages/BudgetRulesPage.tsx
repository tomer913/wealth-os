import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'
import { Modal, ConfirmDialog } from '../components/shared/Modal'
import { Field, Input, Select, FormGrid, FormSection, Divider } from '../components/shared/Form'
import {
  getBudgetRules, getBudgetCategories, getBudgetReviewQueue, getBudgetSummary,
  createBudgetRule, updateBudgetRule, deleteBudgetRule,
  approveBudgetRule, testBudgetRule, testBudgetConditions,
  categorizePendingTx, createBudgetCategory, approveBulkReview,
} from '../api/portfolio'

// ─── Types ────────────────────────────────────────────────────────────────────

interface BudgetCategory {
  id: string
  name: string
  name_en: string | null
  category_type: string
  is_active: boolean
  children: BudgetCategory[]
}

interface Condition {
  field: string
  op: string
  value: string | number | [number, number]
}

interface Conditions {
  operator: 'AND' | 'OR'
  rules: Condition[]
}

interface BudgetRule {
  id: string
  category_id: string
  category_name: string
  name: string
  priority: number
  status: string
  conditions: Conditions
  confidence: number
  source: string
  ai_reasoning: string | null
  match_count: number
  last_matched_at: string | null
}

interface ReviewItem {
  id: string
  raw_transaction_id: string
  category_id: string | null
  method: string
  needs_review: boolean
  confidence: number
  raw_description: string | null
  raw_amount: number | null
  raw_date: string | null
  raw_source: string | null
  category_name: string | null
}

interface TestResult {
  count: number
  sample: { id: string; date: string; description: string; amount: number; currency: string; source: string }[]
}

// ─── Constants ─────────────────────────────────────────────────────────────────

const TABS = ['Active', 'Suggested', 'Review Queue', 'Conflicts'] as const
type Tab = typeof TABS[number]

const FIELDS = ['description', 'amount', 'source', 'economic_type', 'domain', 'currency']
const STRING_OPS = ['contains', 'not_contains', 'starts_with', 'regex', 'eq', 'neq']
const NUMBER_OPS = ['gt', 'lt', 'between']
const ALL_OPS = [...STRING_OPS, 'gt', 'lt', 'between']

const CATEGORY_TYPE_LABELS: Record<string, string> = {
  income: 'Income',
  expense: 'Expense',
  saving: 'Savings',
  investment: 'Investment',
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function flattenCategories(cats: BudgetCategory[]): BudgetCategory[] {
  const result: BudgetCategory[] = []
  function walk(list: BudgetCategory[]) {
    for (const c of list) {
      result.push(c)
      if (c.children?.length) walk(c.children)
    }
  }
  walk(cats)
  return result
}

function emptyConditions(): Conditions {
  return { operator: 'AND', rules: [{ field: 'description', op: 'contains', value: '' }] }
}

function emptyRuleForm() {
  return {
    name: '',
    category_id: '',
    priority: 100,
    status: 'active',
    conditions: emptyConditions(),
  }
}

const FIELD_LABELS: Record<string, string> = {
  description: 'Description', amount: 'Amount', source: 'Source',
  economic_type: 'Type', domain: 'Domain', currency: 'Currency',
}
const OP_LABELS: Record<string, string> = {
  contains: 'contains', not_contains: 'not contains', starts_with: 'starts with',
  regex: 'matches', eq: '=', neq: '≠', equals: '=',
  gt: '>', lt: '<', between: 'between',
}

function conditionSummary(cond: Conditions): string {
  if (!cond?.rules?.length) return '—'
  // Handle both 'op' (UI-created) and 'operator' (AI-generated) field names
  const parts = cond.rules.map((r: Condition & { operator?: string }) => {
    const op = r.op || r.operator || '?'
    const val = Array.isArray(r.value) ? `${r.value[0]}–${r.value[1]}` : String(r.value)
    return `${FIELD_LABELS[r.field] ?? r.field} ${OP_LABELS[op] ?? op} "${val}"`
  })
  return parts.join(` ${cond.operator} `)
}

function formatDate(dt: string | null) {
  if (!dt) return '—'
  return new Date(dt).toLocaleDateString('en-IL')
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: 'bg-emerald-50 text-emerald-700',
    suggested: 'bg-amber-50 text-amber-700',
    inactive: 'bg-gray-100 text-gray-500',
    conflict: 'bg-rose-50 text-rose-700',
    deleted: 'bg-gray-100 text-gray-400',
  }
  return (
    <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-semibold', colors[status] ?? 'bg-gray-100 text-gray-500')}>
      {status}
    </span>
  )
}

// ─── Condition Row ─────────────────────────────────────────────────────────────
// Inline styled with plain <select>/<input> to avoid the Select wrapper's
// w-full base class collapsing the flex layout.

interface CondRow {
  id: string
  field: string
  op: string
  value: string
}

const SEL_CLS = 'px-2 py-1.5 text-[12px] border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-teal-400 focus:ring-1 focus:ring-teal-50 transition-colors'
const IN_CLS  = 'flex-1 px-2 py-1.5 text-[12px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 focus:ring-1 focus:ring-teal-50 transition-colors min-w-0'

function ConditionRows({ rows, op, onRowsChange, onOpChange }: {
  rows: CondRow[]
  op: 'AND' | 'OR'
  onRowsChange: (rows: CondRow[]) => void
  onOpChange: (op: 'AND' | 'OR') => void
}) {
  function update(id: string, patch: Partial<CondRow>) {
    onRowsChange(rows.map(r => r.id === id ? { ...r, ...patch } : r))
  }
  function remove(id: string) {
    const next = rows.filter(r => r.id !== id)
    onRowsChange(next.length ? next : [{ id: crypto.randomUUID(), field: 'description', op: 'contains', value: '' }])
  }
  function add() {
    onRowsChange([...rows, { id: crypto.randomUUID(), field: 'description', op: 'contains', value: '' }])
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[12px] text-gray-500">Match</span>
        {(['AND', 'OR'] as const).map((o) => (
          <button key={o} type="button" onClick={() => onOpChange(o)}
            className={clsx('px-2.5 py-1 text-[11px] font-semibold rounded transition-colors',
              op === o ? 'bg-teal-600 text-white' : 'bg-gray-100 text-gray-500 hover:bg-gray-200')}>
            {o}
          </button>
        ))}
        <span className="text-[12px] text-gray-500">conditions</span>
      </div>

      {rows.map((row) => (
        <div key={row.id} className="flex items-center gap-2">
          {/* Field */}
          <select value={row.field} onChange={e => update(row.id, { field: e.target.value })}
            className={clsx(SEL_CLS, 'w-36 flex-shrink-0')}>
            {FIELDS.map(f => <option key={f} value={f}>{FIELD_LABELS[f] ?? f}</option>)}
          </select>

          {/* Operator */}
          <select value={row.op} onChange={e => update(row.id, { op: e.target.value })}
            className={clsx(SEL_CLS, 'w-32 flex-shrink-0')}>
            {STRING_OPS.map(o => <option key={o} value={o}>{OP_LABELS[o] ?? o}</option>)}
            <optgroup label="Numeric">
              {NUMBER_OPS.map(o => <option key={o} value={o}>{OP_LABELS[o] ?? o}</option>)}
            </optgroup>
          </select>

          {/* Value — always visible */}
          {row.op === 'between' ? (
            <div className="flex items-center gap-1 flex-1 min-w-0">
              <input type="number" value={row.value.split(',')[0] ?? ''}
                onChange={e => update(row.id, { value: `${e.target.value},${row.value.split(',')[1] ?? ''}` })}
                className={clsx(IN_CLS, 'flex-none w-24')} placeholder="min" />
              <span className="text-[11px] text-gray-400 flex-shrink-0">–</span>
              <input type="number" value={row.value.split(',')[1] ?? ''}
                onChange={e => update(row.id, { value: `${row.value.split(',')[0] ?? ''},${e.target.value}` })}
                className={clsx(IN_CLS, 'flex-none w-24')} placeholder="max" />
            </div>
          ) : (
            <input
              type={NUMBER_OPS.includes(row.op) ? 'number' : 'text'}
              value={row.value}
              onChange={e => update(row.id, { value: e.target.value })}
              placeholder="value…"
              dir="rtl"
              className={IN_CLS}
            />
          )}

          {/* Remove */}
          <button type="button" onClick={() => remove(row.id)}
            className="text-gray-300 hover:text-rose-500 transition-colors flex-shrink-0">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M1 1l12 12M13 1L1 13"/>
            </svg>
          </button>
        </div>
      ))}

      <button type="button" onClick={add}
        className="text-[12px] text-teal-600 hover:text-teal-700 font-medium">
        + Add condition
      </button>
    </div>
  )
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function parseCondRows(conditions: Conditions | null | undefined): CondRow[] {
  const rules = conditions?.rules ?? []
  if (!rules.length) {
    return [{ id: crypto.randomUUID(), field: 'description', op: 'contains', value: '' }]
  }
  return rules.map((r: Condition & { operator?: string }) => ({
    id: crypto.randomUUID(),
    field: r.field || 'description',
    // handle both 'op' (UI-created) and 'operator' (AI-generated)
    op: r.op || (r as { operator?: string }).operator || 'contains',
    value: Array.isArray(r.value)
      ? `${r.value[0]},${r.value[1]}`
      : r.value !== undefined && r.value !== null ? String(r.value) : '',
  }))
}

function buildConditions(rows: CondRow[], op: 'AND' | 'OR'): Conditions {
  return {
    operator: op,
    rules: rows
      .filter(r => r.value.trim() !== '')
      .map(r => {
        if (r.op === 'between') {
          const [a, b] = r.value.split(',').map(Number)
          return { field: r.field, op: r.op, value: [a || 0, b || 0] as [number, number] }
        }
        if (NUMBER_OPS.includes(r.op)) {
          return { field: r.field, op: r.op, value: Number(r.value) }
        }
        return { field: r.field, op: r.op, value: r.value }
      }),
  }
}

// ─── Rule Form Modal ──────────────────────────────────────────────────────────

function RuleFormModal({ open, onClose, rule, categories }: {
  open: boolean
  onClose: () => void
  rule: BudgetRule | null
  categories: BudgetCategory[]
}) {
  const qc = useQueryClient()
  const { t } = useTranslation('budget')

  const flatCats = flattenCategories(categories)
  const grouped = flatCats.reduce((acc: Record<string, BudgetCategory[]>, c) => {
    if (!acc[c.category_type]) acc[c.category_type] = []
    acc[c.category_type].push(c)
    return acc
  }, {})

  // Core fields — conditions kept separately so the two don't interfere
  const [form, setForm] = useState(() => rule
    ? { name: rule.name, category_id: rule.category_id, priority: rule.priority, status: rule.status }
    : { name: '', category_id: '', priority: 100, status: 'active' }
  )

  // Condition rows — parsed from rule.conditions on mount (key forces remount on edit)
  const [condRows, setCondRows] = useState<CondRow[]>(() => parseCondRows(rule?.conditions))
  const [condOp, setCondOp] = useState<'AND' | 'OR'>(() => rule?.conditions?.operator ?? 'AND')

  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [testing, setTesting] = useState(false)

  const createMut = useMutation({
    mutationFn: (payload: Record<string, unknown>) => createBudgetRule(payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['budget-rules'] }); onClose() },
  })
  const updateMut = useMutation({
    mutationFn: (payload: Record<string, unknown>) => updateBudgetRule(rule!.id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['budget-rules'] }); onClose() },
  })

  async function handleTest() {
    setTesting(true)
    try {
      const result = await testBudgetConditions(buildConditions(condRows, condOp) as unknown as Record<string, unknown>)
      setTestResult(result)
    } catch {
      alert('Test failed')
    } finally {
      setTesting(false)
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const payload = { ...form, conditions: buildConditions(condRows, condOp) }
    if (rule) updateMut.mutate(payload)
    else createMut.mutate(payload)
  }

  const saving = createMut.isPending || updateMut.isPending

  return (
    <Modal open={open} onClose={onClose} title={rule ? t('rules.form_edit_title') : t('rules.form_new_title')} width="max-w-2xl">
      <form onSubmit={handleSubmit} className="space-y-4">
        {rule?.status === 'suggested' && (
          <div className="px-3 py-2 bg-blue-50 border border-blue-100 rounded-lg text-[12px] text-blue-700">
            {t('rules.editing_suggested')}
          </div>
        )}
        <FormGrid>
          <Field label={t('rules.form_name_label')} required>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Supermarket → shopping"
              required
            />
          </Field>
          <Field label={t('rules.form_category_label')} required>
            <Select
              value={form.category_id}
              onChange={(e) => setForm({ ...form, category_id: e.target.value })}
              required
            >
              <option value="">{t('rules.select_category_placeholder')}</option>
              {Object.entries(grouped).map(([type, cats]) => (
                <optgroup key={type} label={CATEGORY_TYPE_LABELS[type] ?? type}>
                  {(cats as BudgetCategory[]).map((c) => (
                    <option key={c.id} value={c.id}>{c.name}{c.name_en ? ` (${c.name_en})` : ''}</option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </Field>
          <Field label={t('rules.form_priority_label')}>
            <Input
              type="number"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
              min={1}
              max={9999}
            />
          </Field>
          <Field label={t('rules.form_status_label')}>
            <Select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="suggested">Suggested</option>
            </Select>
          </Field>
        </FormGrid>

        <Divider />
        <FormSection title={t('rules.form_conditions_label')}>
          <ConditionRows
            rows={condRows}
            op={condOp}
            onRowsChange={setCondRows}
            onOpChange={setCondOp}
          />
        </FormSection>

        {/* Inline test */}
        <div className="pt-2">
          <button
            type="button"
            onClick={handleTest}
            disabled={testing}
            className="text-[12px] text-teal-600 hover:text-teal-700 font-medium underline"
          >
            {testing ? t('rules.form_testing') : t('rules.form_test_btn')}
          </button>
          {testResult && (
            <div className="mt-2 p-3 bg-gray-50 rounded-lg border border-gray-200 text-[12px]">
              <p className="font-semibold text-gray-700 mb-2">
                {t('rules.form_test_matches', { count: testResult.count })}
              </p>
              {testResult.sample.map((tx) => (
                <div key={tx.id} className="flex items-center gap-3 py-1 border-b border-gray-100 last:border-0" dir="rtl">
                  <span className="text-gray-400 w-20 flex-shrink-0">{tx.date?.slice(0, 10)}</span>
                  <span className="flex-1 text-gray-700 truncate">{tx.description}</span>
                  <span className="text-gray-500 font-mono flex-shrink-0">{tx.amount.toLocaleString()} {tx.currency}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-[13px] font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 text-[13px] font-medium bg-teal-600 hover:bg-teal-700 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {saving ? t('rules.form_saving') : rule ? t('rules.form_save_changes') : t('rules.form_create_rule')}
          </button>
        </div>
      </form>
    </Modal>
  )
}

// ─── Test Result Modal ────────────────────────────────────────────────────────

function TestModal({ open, onClose, result, ruleName }: {
  open: boolean; onClose: () => void; result: TestResult | null; ruleName: string
}) {
  const { t } = useTranslation('budget')
  if (!result) return null
  return (
    <Modal open={open} onClose={onClose} title={`Test: ${ruleName}`}>
      <p className="text-[13px] text-gray-600 mb-4">
        {t('rules.test_modal_matches', { count: result.count })}
      </p>
      <div className="space-y-1">
        {result.sample.map((tx) => (
          <div key={tx.id} className="flex items-center gap-3 py-2 border-b border-gray-100 last:border-0 text-[12px]" dir="rtl">
            <span className="text-gray-400 w-20 flex-shrink-0">{tx.date?.slice(0, 10)}</span>
            <span className="flex-1 text-gray-700 truncate">{tx.description}</span>
            <span className="text-gray-500 font-mono flex-shrink-0">{tx.amount.toLocaleString()} {tx.currency}</span>
          </div>
        ))}
        {result.count === 0 && <p className="text-[12px] text-gray-400 text-center py-6">{t('rules.test_no_matches')}</p>}
      </div>
    </Modal>
  )
}

// ─── Active Rules Tab ─────────────────────────────────────────────────────────

function ActiveRulesTab({ rules, categories, onEdit }: {
  rules: BudgetRule[]
  categories: BudgetCategory[]
  onEdit: (r: BudgetRule) => void
}) {
  const { t } = useTranslation('budget')
  const qc = useQueryClient()
  const [deleteTarget, setDeleteTarget] = useState<BudgetRule | null>(null)
  const [testTarget, setTestTarget] = useState<BudgetRule | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteBudgetRule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-rules'] }),
  })

  async function handleTest(rule: BudgetRule) {
    setTestTarget(rule)
    try {
      const result = await testBudgetRule(rule.id)
      setTestResult(result)
    } catch {
      setTestResult({ count: 0, sample: [] })
    }
  }

  const active = rules.filter((r) => r.status === 'active')

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-gray-100">
              {[t('rules.active_cols.priority'),t('rules.active_cols.name'),t('rules.active_cols.category'),t('rules.active_cols.conditions'),t('rules.active_cols.matches'),t('rules.active_cols.status'),t('rules.active_cols.actions')].map((h) => (
                <th key={h} className="py-2.5 px-3 text-left text-[11px] text-gray-400 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {active.length === 0 && (
              <tr><td colSpan={7} className="py-10 text-center text-gray-400">{t('rules.no_active_rules')}</td></tr>
            )}
            {active.map((rule) => (
              <tr key={rule.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                <td className="py-2.5 px-3 font-mono text-gray-500">{rule.priority}</td>
                <td className="py-2.5 px-3 font-medium text-gray-900 max-w-[160px] truncate">{rule.name}</td>
                <td className="py-2.5 px-3 text-gray-600">{rule.category_name}</td>
                <td className="py-2.5 px-3 text-gray-400 max-w-[200px] truncate font-mono text-[11px]">
                  {conditionSummary(rule.conditions)}
                </td>
                <td className="py-2.5 px-3 text-gray-500">{rule.match_count}</td>
                <td className="py-2.5 px-3"><StatusBadge status={rule.status} /></td>
                <td className="py-2.5 px-3">
                  <div className="flex items-center gap-2">
                    <button onClick={() => onEdit(rule)} className="text-teal-600 hover:text-teal-700 font-medium">{t('rules.btn_edit')}</button>
                    <button onClick={() => handleTest(rule)} className="text-blue-600 hover:text-blue-700 font-medium">{t('rules.btn_test')}</button>
                    <button onClick={() => setDeleteTarget(rule)} className="text-rose-500 hover:text-rose-600 font-medium">{t('rules.btn_delete')}</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title={t('rules.delete_rule_title')}
        message={deleteTarget ? t('rules.delete_rule_msg', { name: deleteTarget.name }) : ''}
        confirmLabel={t('rules.btn_delete')}
        danger
        onConfirm={() => { deleteMut.mutate(deleteTarget!.id); setDeleteTarget(null) }}
        onCancel={() => setDeleteTarget(null)}
      />
      <TestModal
        open={!!testTarget}
        onClose={() => { setTestTarget(null); setTestResult(null) }}
        result={testResult}
        ruleName={testTarget?.name ?? ''}
      />
    </>
  )
}

// ─── Suggested Rules Tab ──────────────────────────────────────────────────────

function SuggestedRulesTab({ rules, onEdit }: { rules: BudgetRule[]; onEdit: (r: BudgetRule) => void }) {
  const { t } = useTranslation('budget')
  const qc = useQueryClient()
  const suggested = rules.filter((r) => r.status === 'suggested')

  const approveMut = useMutation({
    mutationFn: (id: string) => approveBudgetRule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-rules'] }),
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteBudgetRule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budget-rules'] }),
  })

  const [approving, setApproving] = useState(false)

  async function handleApproveAll() {
    setApproving(true)
    try {
      // 1. Bulk-approve high-confidence review-queue items (>= 90 %)
      await approveBulkReview(0.9)
      qc.invalidateQueries({ queryKey: ['budget-review'] })
      qc.invalidateQueries({ queryKey: ['budget-actuals'] })
      qc.invalidateQueries({ queryKey: ['budget-summary'] })
      // 2. Also promote any suggested rules with >= 90 % confidence
      const highConf = suggested.filter((r) => r.confidence >= 0.9)
      await Promise.all(highConf.map((r) => approveBudgetRule(r.id)))
      qc.invalidateQueries({ queryKey: ['budget-rules'] })
    } catch (err) {
      console.error('Approve all high confidence failed:', err)
    } finally {
      setApproving(false)
    }
  }

  return (
    <div className="space-y-4">
      {suggested.length > 0 && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={handleApproveAll}
            disabled={approving}
            className="px-3 py-1.5 text-[12px] font-medium bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {approving ? '…' : t('rules.approve_all_high')}
          </button>
        </div>
      )}
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-gray-100">
            {[t('rules.suggested_cols.category'),t('rules.suggested_cols.conditions'),t('rules.suggested_cols.ai_reasoning'),t('rules.suggested_cols.confidence'),t('rules.suggested_cols.actions')].map((h) => (
              <th key={h} className="py-2.5 px-3 text-left text-[11px] text-gray-400 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {suggested.length === 0 && (
            <tr><td colSpan={5} className="py-10 text-center text-gray-400">{t('rules.no_suggested_rules')}</td></tr>
          )}
          {suggested.map((rule) => (
            <tr key={rule.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
              <td className="py-2.5 px-3 font-medium text-gray-900">{rule.category_name}</td>
              <td className="py-2.5 px-3 text-gray-400 font-mono text-[11px] max-w-[200px] truncate">
                {conditionSummary(rule.conditions)}
              </td>
              <td className="py-2.5 px-3 text-gray-500 max-w-[200px] truncate">{rule.ai_reasoning ?? '—'}</td>
              <td className="py-2.5 px-3">
                <span className={clsx('font-semibold', rule.confidence >= 0.9 ? 'text-emerald-600' : 'text-amber-600')}>
                  {Math.round(rule.confidence * 100)}%
                </span>
              </td>
              <td className="py-2.5 px-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => approveMut.mutate(rule.id)}
                    className="text-emerald-600 hover:text-emerald-700 font-medium"
                  >{t('rules.btn_approve')}</button>
                  <button
                    type="button"
                    onClick={() => onEdit(rule)}
                    className="text-blue-600 hover:text-blue-700 font-medium"
                  >{t('rules.btn_edit')}</button>
                  <button
                    type="button"
                    onClick={() => deleteMut.mutate(rule.id)}
                    className="text-rose-500 hover:text-rose-600 font-medium"
                  >{t('rules.btn_reject')}</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── Review Queue Tab ─────────────────────────────────────────────────────────

const TYPE_LABELS_HE: Record<string, string> = {
  income: 'הכנסות',
  expense: 'הוצאות',
  saving: 'חיסכון',
  investment: 'השקעות',
}

function ReviewQueueTab({ categories }: { categories: BudgetCategory[] }) {
  const { t } = useTranslation('budget')
  const qc = useQueryClient()
  const currentYear = new Date().getFullYear()

  const [showBulkConfirm, setShowBulkConfirm] = useState(false)
  const approveBulkMut = useMutation({
    mutationFn: () => approveBulkReview(0.9),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budget-review'] })
      qc.invalidateQueries({ queryKey: ['budget-actuals'] })
      qc.invalidateQueries({ queryKey: ['budget-summary'] })
      setShowBulkConfirm(false)
    },
  })

  // Fetch annual usage counts to sort categories by frequency
  const { data: annualSummary = [] } = useQuery({
    queryKey: ['budget-summary', currentYear, null],
    queryFn: () => getBudgetSummary(currentYear),
    staleTime: 5 * 60 * 1000,
  })
  const usageCount: Record<string, number> = {}
  for (const row of annualSummary as { category_id: string; transaction_count: number }[]) {
    usageCount[row.category_id] = row.transaction_count
  }

  // Flat sorted list: most-used first, then alphabetical for ties / zero-count
  const flatCats = flattenCategories(categories)
  const sortedCats = [...flatCats].sort((a, b) => {
    const ua = usageCount[a.id] ?? 0
    const ub = usageCount[b.id] ?? 0
    if (ub !== ua) return ub - ua
    return a.name.localeCompare(b.name, 'he')
  })

  const { data: queue = [], isLoading } = useQuery({
    queryKey: ['budget-review'],
    queryFn: getBudgetReviewQueue,
  })

  const [selected, setSelected] = useState<Record<string, string>>({})
  // Default "Remember this rule" to true
  const [genRule, setGenRule] = useState<Record<string, boolean>>({})

  // Inline new-category state
  const [newCatFor, setNewCatFor] = useState<string | null>(null)
  const [newCatName, setNewCatName] = useState('')
  const [newCatType, setNewCatType] = useState('expense')

  const categorizeMut = useMutation({
    mutationFn: ({ logId, catId, gr, excluded }: { logId: string; catId: string | null; gr: boolean; excluded?: boolean }) =>
      categorizePendingTx(logId, catId, gr, excluded),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budget-review'] })
      qc.invalidateQueries({ queryKey: ['budget-actuals'] })
      qc.invalidateQueries({ queryKey: ['budget-summary'] })
      qc.invalidateQueries({ queryKey: ['budget-rules'] })
    },
  })

  const createCatMut = useMutation({
    mutationFn: (payload: Record<string, unknown>) => createBudgetCategory(payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['budget-categories'] })
      if (newCatFor) setSelected((prev) => ({ ...prev, [newCatFor]: data.id }))
      setNewCatFor(null)
      setNewCatName('')
      setNewCatType('expense')
    },
  })

  function handleSelectChange(itemId: string, value: string) {
    if (value === '__new__') {
      setNewCatFor(itemId)
      setNewCatName('')
      setNewCatType('expense')
      setSelected((prev) => { const n = { ...prev }; delete n[itemId]; return n })
    } else {
      setSelected((prev) => ({ ...prev, [itemId]: value }))
      setNewCatFor(null)
    }
  }

  const highConfCount = (queue as ReviewItem[]).filter(
    item => item.confidence >= 0.9 && item.category_id != null,
  ).length

  if (isLoading) return <p className="text-[12px] text-gray-400 text-center py-10">{t('rules.loading')}</p>

  return (
    <>
      {highConfCount > 0 && (
        <div className="flex justify-end mb-3">
          <button
            type="button"
            onClick={() => setShowBulkConfirm(true)}
            disabled={approveBulkMut.isPending}
            className="px-3 py-1.5 text-[12px] font-medium bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors disabled:opacity-50"
          >
            {approveBulkMut.isPending ? '…' : t('rules.approve_all_queue', { count: highConfCount })}
          </button>
        </div>
      )}
      <ConfirmDialog
        open={showBulkConfirm}
        title={t('rules.approve_bulk_confirm_title')}
        message={t('rules.approve_bulk_confirm_msg', { count: highConfCount })}
        confirmLabel={t('rules.approve_all_queue', { count: highConfCount })}
        onConfirm={() => approveBulkMut.mutate()}
        onCancel={() => setShowBulkConfirm(false)}
      />
    <table className="w-full text-[12px]">
      <thead>
        <tr className="border-b border-gray-100">
          {[t('rules.review_cols.date'),t('rules.review_cols.description'),t('rules.review_cols.amount'),t('rules.review_cols.source'),t('rules.review_cols.category'),t('rules.review_cols.actions')].map((h) => (
            <th key={h} className="py-2.5 px-3 text-left text-[11px] text-gray-400 font-medium">{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {queue.length === 0 && (
          <tr><td colSpan={6} className="py-10 text-center text-gray-400">{t('rules.review_empty')}</td></tr>
        )}
        {(queue as ReviewItem[]).map((item) => (
          <tr key={item.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors align-top">
            <td className="py-2.5 px-3 text-gray-400 whitespace-nowrap">{formatDate(item.raw_date)}</td>
            <td className="py-2.5 px-3 text-gray-700 max-w-[200px] truncate" dir="rtl">{item.raw_description ?? '—'}</td>
            <td className="py-2.5 px-3 font-mono text-gray-600 whitespace-nowrap">
              {item.raw_amount != null ? Math.abs(item.raw_amount).toLocaleString() : '—'}
            </td>
            <td className="py-2.5 px-3 text-gray-400">{item.raw_source}</td>
            <td className="py-2.5 px-3 min-w-[220px]">
              <Select
                value={newCatFor === item.id ? '__new__' : (selected[item.id] ?? '')}
                onChange={(e) => handleSelectChange(item.id, e.target.value)}
                className="text-[12px]"
              >
                <option value="">{t('rules.select_category_placeholder')}</option>
                {/* Special actions — always at top */}
                <option value="__exclude__">{t('rules.exclude_from_budget')}</option>
                <option value="__new__">{t('rules.new_category')}</option>
                <optgroup label="─────────────────────" />
                {/* Categories sorted by usage frequency */}
                {sortedCats.map((c) => {
                  const count = usageCount[c.id]
                  const label = count
                    ? `${c.name}  (${count}×)`
                    : c.name
                  return <option key={c.id} value={c.id}>{label}</option>
                })}
              </Select>

              {/* Inline new-category form */}
              {newCatFor === item.id && (
                <div className="mt-2 p-3 bg-blue-50 border border-blue-100 rounded-lg space-y-2" dir="rtl">
                  <input
                    autoFocus
                    type="text"
                    value={newCatName}
                    onChange={(e) => setNewCatName(e.target.value)}
                    placeholder="שם הקטגוריה"
                    className="w-full px-2.5 py-1.5 text-[12px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 bg-white"
                    dir="rtl"
                  />
                  <div className="flex gap-1 flex-wrap">
                    {(['expense', 'income', 'saving', 'investment'] as const).map((type) => (
                      <button
                        key={type}
                        type="button"
                        onClick={() => setNewCatType(type)}
                        className={clsx(
                          'px-2 py-1 text-[10px] font-medium rounded-md border transition-colors',
                          newCatType === type
                            ? 'bg-teal-600 text-white border-teal-600'
                            : 'bg-white text-gray-500 border-gray-200 hover:border-teal-300',
                        )}
                      >
                        {TYPE_LABELS_HE[type]}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={!newCatName.trim() || createCatMut.isPending}
                      onClick={() => createCatMut.mutate({ name: newCatName.trim(), name_en: newCatName.trim(), category_type: newCatType, sort_order: 99 })}
                      className="flex-1 py-1.5 text-[11px] font-medium bg-teal-600 hover:bg-teal-700 text-white rounded-lg disabled:opacity-40 transition-colors"
                    >
                      {createCatMut.isPending ? '…' : t('rules.btn_create_select')}
                    </button>
                    <button
                      type="button"
                      onClick={() => setNewCatFor(null)}
                      className="px-3 py-1.5 text-[11px] text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg bg-white transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </td>
            <td className="py-2.5 px-3">
              <div className="flex flex-col gap-1.5 items-start">
                {selected[item.id] !== '__exclude__' && (
                  <label className="relative flex items-center gap-1.5 text-[11px] text-gray-500 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={genRule[item.id] ?? true}
                      onChange={(e) => setGenRule({ ...genRule, [item.id]: e.target.checked })}
                      className="accent-teal-600"
                    />
                    <span>{t('rules.remember_rule')}</span>
                    {/* Tooltip */}
                    <span className="pointer-events-none absolute bottom-full left-0 mb-1.5 w-56 rounded-lg bg-gray-800 px-2.5 py-2 text-[10px] leading-snug text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100 z-20">
                      {t('rules.remember_rule_tooltip')}
                    </span>
                  </label>
                )}
                {(() => {
                  const sel = selected[item.id]
                  const isExclude = sel === '__exclude__'
                  return (
                    <button
                      disabled={!sel || categorizeMut.isPending}
                      onClick={() => categorizeMut.mutate({
                        logId: item.id,
                        catId: isExclude ? null : sel,
                        gr: genRule[item.id] ?? true,
                        excluded: isExclude,
                      })}
                      className={clsx(
                        'px-3 py-1.5 text-[11px] font-medium text-white rounded-lg transition-colors disabled:opacity-40',
                        isExclude
                          ? 'bg-gray-500 hover:bg-gray-600'
                          : 'bg-teal-600 hover:bg-teal-700',
                      )}
                    >
                      {isExclude ? t('rules.btn_exclude') : t('rules.btn_confirm')}
                    </button>
                  )
                })()}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    </>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function BudgetRulesPage() {
  const { t } = useTranslation('budget')
  const [activeTab, setActiveTab] = useState<Tab>('Active')
  const [showForm, setShowForm] = useState(false)
  const [editingRule, setEditingRule] = useState<BudgetRule | null>(null)

  const { data: rules = [], isLoading: rulesLoading } = useQuery({
    queryKey: ['budget-rules'],
    queryFn: () => getBudgetRules('all'),
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['budget-categories'],
    queryFn: () => getBudgetCategories(),
  })

  const suggestedCount = (rules as BudgetRule[]).filter((r) => r.status === 'suggested').length

  function handleEdit(rule: BudgetRule) {
    setEditingRule(rule)
    setShowForm(true)
  }

  function handleClose() {
    setShowForm(false)
    setEditingRule(null)
  }

  return (
    <div className="p-6 pb-20 md:pb-6 bg-gray-50 min-h-full space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[20px] font-bold text-gray-900">{t('rules.page_title')}</h1>
          <p className="text-[12px] text-gray-400 mt-0.5">
            {t('rules.page_subtitle')}
          </p>
        </div>
        <button
          onClick={() => { setEditingRule(null); setShowForm(true) }}
          className="px-4 py-2 text-[13px] font-medium bg-teal-600 hover:bg-teal-700 text-white rounded-lg transition-colors"
        >
          {t('rules.new_rule')}
        </button>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="flex border-b border-gray-100">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={clsx(
                'px-5 py-3 text-[13px] font-medium transition-colors relative',
                activeTab === tab
                  ? 'text-teal-700 border-b-2 border-teal-600 -mb-px'
                  : 'text-gray-500 hover:text-gray-700'
              )}
            >
              {tab === 'Active' ? t('rules.tabs.active') : tab === 'Suggested' ? t('rules.tabs.suggested') : tab === 'Review Queue' ? t('rules.tabs.review_queue') : t('rules.tabs.conflicts')}
              {tab === 'Suggested' && suggestedCount > 0 && (
                <span className="ml-1.5 bg-amber-100 text-amber-700 text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                  {suggestedCount}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="p-5">
          {rulesLoading ? (
            <p className="text-[12px] text-gray-400 text-center py-10">{t('rules.loading_rules')}</p>
          ) : activeTab === 'Active' ? (
            <ActiveRulesTab
              rules={rules as BudgetRule[]}
              categories={categories as BudgetCategory[]}
              onEdit={handleEdit}
            />
          ) : activeTab === 'Suggested' ? (
            <SuggestedRulesTab rules={rules as BudgetRule[]} onEdit={handleEdit} />
          ) : activeTab === 'Review Queue' ? (
            <ReviewQueueTab categories={categories as BudgetCategory[]} />
          ) : (
            <div className="py-10 text-center text-[13px] text-gray-400">
              {t('rules.conflict_coming_soon')}
            </div>
          )}
        </div>
      </div>

      <RuleFormModal
        key={editingRule?.id ?? 'new'}
        open={showForm}
        onClose={handleClose}
        rule={editingRule}
        categories={categories as BudgetCategory[]}
      />
    </div>
  )
}
