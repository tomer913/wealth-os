import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Modal, ConfirmDialog } from '../components/shared/Modal'
import { Field, Input, Select, FormGrid, FormSection, Divider } from '../components/shared/Form'
import {
  getBudgetRules, getBudgetCategories, getBudgetReviewQueue,
  createBudgetRule, updateBudgetRule, deleteBudgetRule,
  approveBudgetRule, testBudgetRule, testBudgetConditions,
  categorizePendingTx,
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

function conditionSummary(cond: Conditions): string {
  if (!cond?.rules?.length) return '—'
  const parts = cond.rules.map((r) => {
    const val = Array.isArray(r.value) ? `${r.value[0]}–${r.value[1]}` : String(r.value)
    return `${r.field} ${r.op} "${val}"`
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

// ─── Condition Builder ────────────────────────────────────────────────────────

function ConditionBuilder({ conditions, onChange }: {
  conditions: Conditions
  onChange: (c: Conditions) => void
}) {
  function updateOp(op: 'AND' | 'OR') {
    onChange({ ...conditions, operator: op })
  }

  function updateRule(i: number, patch: Partial<Condition>) {
    const rules = [...conditions.rules]
    rules[i] = { ...rules[i], ...patch }
    // Reset value when switching op
    if (patch.op && patch.op === 'between') rules[i].value = [0, 9999999]
    else if (patch.op && NUMBER_OPS.includes(patch.op) && !Array.isArray(rules[i].value)) rules[i].value = 0
    else if (patch.op && STRING_OPS.includes(patch.op) && typeof rules[i].value !== 'string') rules[i].value = ''
    onChange({ ...conditions, rules })
  }

  function addRule() {
    onChange({ ...conditions, rules: [...conditions.rules, { field: 'description', op: 'contains', value: '' }] })
  }

  function removeRule(i: number) {
    const rules = conditions.rules.filter((_, idx) => idx !== i)
    onChange({ ...conditions, rules: rules.length ? rules : [{ field: 'description', op: 'contains', value: '' }] })
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-[12px] text-gray-500">Match</span>
        {(['AND', 'OR'] as const).map((op) => (
          <button
            key={op}
            type="button"
            onClick={() => updateOp(op)}
            className={clsx(
              'px-2.5 py-1 text-[11px] font-semibold rounded transition-colors',
              conditions.operator === op
                ? 'bg-teal-600 text-white'
                : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
            )}
          >{op}</button>
        ))}
        <span className="text-[12px] text-gray-500">conditions</span>
      </div>

      {conditions.rules.map((rule, i) => (
        <div key={i} className="flex items-center gap-2">
          <Select
            value={rule.field}
            onChange={(e) => updateRule(i, { field: e.target.value })}
            className="flex-shrink-0 w-36 text-[12px]"
          >
            {FIELDS.map((f) => <option key={f} value={f}>{f}</option>)}
          </Select>

          <Select
            value={rule.op}
            onChange={(e) => updateRule(i, { op: e.target.value })}
            className="flex-shrink-0 w-32 text-[12px]"
          >
            {ALL_OPS.map((op) => <option key={op} value={op}>{op.replace('_', ' ')}</option>)}
          </Select>

          {rule.op === 'between' ? (
            <div className="flex items-center gap-1 flex-1">
              <Input
                type="number"
                value={Array.isArray(rule.value) ? rule.value[0] : 0}
                onChange={(e) => updateRule(i, { value: [Number(e.target.value), Array.isArray(rule.value) ? rule.value[1] : 0] })}
                className="w-24 text-[12px]"
              />
              <span className="text-[11px] text-gray-400">–</span>
              <Input
                type="number"
                value={Array.isArray(rule.value) ? rule.value[1] : 0}
                onChange={(e) => updateRule(i, { value: [Array.isArray(rule.value) ? rule.value[0] : 0, Number(e.target.value)] })}
                className="w-24 text-[12px]"
              />
            </div>
          ) : NUMBER_OPS.includes(rule.op) ? (
            <Input
              type="number"
              value={typeof rule.value === 'number' ? rule.value : 0}
              onChange={(e) => updateRule(i, { value: Number(e.target.value) })}
              className="flex-1 text-[12px]"
            />
          ) : (
            <Input
              value={typeof rule.value === 'string' ? rule.value : ''}
              onChange={(e) => updateRule(i, { value: e.target.value })}
              placeholder="value"
              className="flex-1 text-[12px]"
              dir="rtl"
            />
          )}

          <button
            type="button"
            onClick={() => removeRule(i)}
            className="text-gray-300 hover:text-rose-500 transition-colors flex-shrink-0"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M1 1l12 12M13 1L1 13"/>
            </svg>
          </button>
        </div>
      ))}

      <button
        type="button"
        onClick={addRule}
        className="text-[12px] text-teal-600 hover:text-teal-700 font-medium"
      >
        + Add condition
      </button>
    </div>
  )
}

// ─── Rule Form Modal ──────────────────────────────────────────────────────────

function RuleFormModal({ open, onClose, rule, categories }: {
  open: boolean
  onClose: () => void
  rule: BudgetRule | null
  categories: BudgetCategory[]
}) {
  const qc = useQueryClient()
  const flatCats = flattenCategories(categories)
  const grouped = flatCats.reduce((acc: Record<string, BudgetCategory[]>, c) => {
    if (!acc[c.category_type]) acc[c.category_type] = []
    acc[c.category_type].push(c)
    return acc
  }, {})

  const [form, setForm] = useState(() =>
    rule ? {
      name: rule.name,
      category_id: rule.category_id,
      priority: rule.priority,
      status: rule.status,
      conditions: rule.conditions,
    } : emptyRuleForm()
  )
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [testing, setTesting] = useState(false)

  const createMut = useMutation({
    mutationFn: (payload: typeof form) => createBudgetRule(payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['budget-rules'] }); onClose() },
  })
  const updateMut = useMutation({
    mutationFn: (payload: typeof form) => updateBudgetRule(rule!.id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['budget-rules'] }); onClose() },
  })

  async function handleTest() {
    setTesting(true)
    try {
      const result = await testBudgetConditions(form.conditions as unknown as Record<string, unknown>)
      setTestResult(result)
    } catch (e) {
      alert('Test failed')
    } finally {
      setTesting(false)
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (rule) updateMut.mutate(form)
    else createMut.mutate(form)
  }

  const saving = createMut.isPending || updateMut.isPending

  return (
    <Modal open={open} onClose={onClose} title={rule ? 'Edit Rule' : 'New Rule'} width="max-w-2xl">
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormGrid>
          <Field label="Rule Name" required>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Supermarket → shopping"
              required
            />
          </Field>
          <Field label="Category" required>
            <Select
              value={form.category_id}
              onChange={(e) => setForm({ ...form, category_id: e.target.value })}
              required
            >
              <option value="">Select category…</option>
              {Object.entries(grouped).map(([type, cats]) => (
                <optgroup key={type} label={CATEGORY_TYPE_LABELS[type] ?? type}>
                  {(cats as BudgetCategory[]).map((c) => (
                    <option key={c.id} value={c.id}>{c.name}{c.name_en ? ` (${c.name_en})` : ''}</option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </Field>
          <Field label="Priority">
            <Input
              type="number"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
              min={1}
              max={9999}
            />
          </Field>
          <Field label="Status">
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
        <FormSection title="Conditions">
          <ConditionBuilder
            conditions={form.conditions}
            onChange={(c) => setForm({ ...form, conditions: c })}
          />
        </FormSection>

        {/* Test inline */}
        <div className="pt-2">
          <button
            type="button"
            onClick={handleTest}
            disabled={testing}
            className="text-[12px] text-teal-600 hover:text-teal-700 font-medium underline"
          >
            {testing ? 'Testing…' : 'Test this rule against recent transactions'}
          </button>
          {testResult && (
            <div className="mt-2 p-3 bg-gray-50 rounded-lg border border-gray-200 text-[12px]">
              <p className="font-semibold text-gray-700 mb-2">
                {testResult.count} matching transactions (showing up to 5)
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
            {saving ? 'Saving…' : rule ? 'Save Changes' : 'Create Rule'}
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
  if (!result) return null
  return (
    <Modal open={open} onClose={onClose} title={`Test: ${ruleName}`}>
      <p className="text-[13px] text-gray-600 mb-4">
        <span className="font-semibold text-gray-900">{result.count}</span> matching transactions in the last 90 days
      </p>
      <div className="space-y-1">
        {result.sample.map((tx) => (
          <div key={tx.id} className="flex items-center gap-3 py-2 border-b border-gray-100 last:border-0 text-[12px]" dir="rtl">
            <span className="text-gray-400 w-20 flex-shrink-0">{tx.date?.slice(0, 10)}</span>
            <span className="flex-1 text-gray-700 truncate">{tx.description}</span>
            <span className="text-gray-500 font-mono flex-shrink-0">{tx.amount.toLocaleString()} {tx.currency}</span>
          </div>
        ))}
        {result.count === 0 && <p className="text-[12px] text-gray-400 text-center py-6">No matches found</p>}
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
              {['Priority', 'Name', 'Category', 'Conditions', 'Matches', 'Status', 'Actions'].map((h) => (
                <th key={h} className="py-2.5 px-3 text-left text-[11px] text-gray-400 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {active.length === 0 && (
              <tr><td colSpan={7} className="py-10 text-center text-gray-400">No active rules yet</td></tr>
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
                    <button onClick={() => onEdit(rule)} className="text-teal-600 hover:text-teal-700 font-medium">Edit</button>
                    <button onClick={() => handleTest(rule)} className="text-blue-600 hover:text-blue-700 font-medium">Test</button>
                    <button onClick={() => setDeleteTarget(rule)} className="text-rose-500 hover:text-rose-600 font-medium">Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete rule"
        message={`Delete "${deleteTarget?.name}"? This cannot be undone.`}
        confirmLabel="Delete"
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

function SuggestedRulesTab({ rules }: { rules: BudgetRule[] }) {
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

  function approveAll() {
    const highConf = suggested.filter((r) => r.confidence >= 0.9)
    highConf.forEach((r) => approveMut.mutate(r.id))
  }

  return (
    <div className="space-y-4">
      {suggested.length > 0 && (
        <div className="flex justify-end">
          <button
            onClick={approveAll}
            className="px-3 py-1.5 text-[12px] font-medium bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-colors"
          >
            Approve all high confidence (&gt;0.9)
          </button>
        </div>
      )}
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-gray-100">
            {['Category', 'Conditions', 'AI Reasoning', 'Confidence', 'Actions'].map((h) => (
              <th key={h} className="py-2.5 px-3 text-left text-[11px] text-gray-400 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {suggested.length === 0 && (
            <tr><td colSpan={5} className="py-10 text-center text-gray-400">No suggested rules</td></tr>
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
                    onClick={() => approveMut.mutate(rule.id)}
                    className="text-emerald-600 hover:text-emerald-700 font-medium"
                  >Approve</button>
                  <button
                    onClick={() => deleteMut.mutate(rule.id)}
                    className="text-rose-500 hover:text-rose-600 font-medium"
                  >Reject</button>
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

function ReviewQueueTab({ categories }: { categories: BudgetCategory[] }) {
  const qc = useQueryClient()
  const flatCats = flattenCategories(categories)
  const { data: queue = [], isLoading } = useQuery({
    queryKey: ['budget-review'],
    queryFn: getBudgetReviewQueue,
  })
  const [selected, setSelected] = useState<Record<string, string>>({})
  const [genRule, setGenRule] = useState<Record<string, boolean>>({})

  const categorizeMut = useMutation({
    mutationFn: ({ logId, catId, gr }: { logId: string; catId: string; gr: boolean }) =>
      categorizePendingTx(logId, catId, gr),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budget-review'] })
    },
  })

  if (isLoading) return <p className="text-[12px] text-gray-400 text-center py-10">Loading…</p>

  return (
    <table className="w-full text-[12px]">
      <thead>
        <tr className="border-b border-gray-100">
          {['Date', 'Description', 'Amount', 'Source', 'Category', 'Actions'].map((h) => (
            <th key={h} className="py-2.5 px-3 text-left text-[11px] text-gray-400 font-medium">{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {queue.length === 0 && (
          <tr><td colSpan={6} className="py-10 text-center text-gray-400">Review queue is empty</td></tr>
        )}
        {(queue as ReviewItem[]).map((item) => (
          <tr key={item.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
            <td className="py-2.5 px-3 text-gray-400">{formatDate(item.raw_date)}</td>
            <td className="py-2.5 px-3 text-gray-700 max-w-[200px] truncate" dir="rtl">{item.raw_description ?? '—'}</td>
            <td className="py-2.5 px-3 font-mono text-gray-600">
              {item.raw_amount != null ? Math.abs(item.raw_amount).toLocaleString() : '—'}
            </td>
            <td className="py-2.5 px-3 text-gray-400">{item.raw_source}</td>
            <td className="py-2.5 px-3">
              <Select
                value={selected[item.id] ?? ''}
                onChange={(e) => setSelected({ ...selected, [item.id]: e.target.value })}
                className="text-[12px]"
              >
                <option value="">Pick category…</option>
                {flatCats.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </Select>
            </td>
            <td className="py-2.5 px-3">
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1 text-[11px] text-gray-400">
                  <input
                    type="checkbox"
                    checked={genRule[item.id] ?? false}
                    onChange={(e) => setGenRule({ ...genRule, [item.id]: e.target.checked })}
                  />
                  Gen rule
                </label>
                <button
                  disabled={!selected[item.id] || categorizeMut.isPending}
                  onClick={() => categorizeMut.mutate({
                    logId: item.id,
                    catId: selected[item.id],
                    gr: genRule[item.id] ?? false,
                  })}
                  className="px-2.5 py-1 text-[11px] font-medium bg-teal-600 hover:bg-teal-700 text-white rounded transition-colors disabled:opacity-40"
                >
                  Confirm
                </button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function BudgetRulesPage() {
  const [activeTab, setActiveTab] = useState<Tab>('Active')
  const [showForm, setShowForm] = useState(false)
  const [editingRule, setEditingRule] = useState<BudgetRule | null>(null)

  const { data: rules = [], isLoading: rulesLoading } = useQuery({
    queryKey: ['budget-rules'],
    queryFn: () => getBudgetRules('all'),
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['budget-categories'],
    queryFn: getBudgetCategories,
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
          <h1 className="text-[20px] font-bold text-gray-900">Budget Rules</h1>
          <p className="text-[12px] text-gray-400 mt-0.5">
            Classification rules that map bank transactions to budget categories
          </p>
        </div>
        <button
          onClick={() => { setEditingRule(null); setShowForm(true) }}
          className="px-4 py-2 text-[13px] font-medium bg-teal-600 hover:bg-teal-700 text-white rounded-lg transition-colors"
        >
          + New Rule
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
              {tab}
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
            <p className="text-[12px] text-gray-400 text-center py-10">Loading rules…</p>
          ) : activeTab === 'Active' ? (
            <ActiveRulesTab
              rules={rules as BudgetRule[]}
              categories={categories as BudgetCategory[]}
              onEdit={handleEdit}
            />
          ) : activeTab === 'Suggested' ? (
            <SuggestedRulesTab rules={rules as BudgetRule[]} />
          ) : activeTab === 'Review Queue' ? (
            <ReviewQueueTab categories={categories as BudgetCategory[]} />
          ) : (
            <div className="py-10 text-center text-[13px] text-gray-400">
              Conflict detection coming soon
            </div>
          )}
        </div>
      </div>

      <RuleFormModal
        open={showForm}
        onClose={handleClose}
        rule={editingRule}
        categories={categories as BudgetCategory[]}
      />
    </div>
  )
}
