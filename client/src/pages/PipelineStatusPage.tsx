import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getProcessorRuns, triggerProcessorRun, resetProcessorCheckpoint, triggerSnapshotRebuild,
} from '../api/portfolio'
import { useRebuildSnapshot } from '../hooks/usePortfolio'
import { isEnabled } from '../config/features'
import type { ProcessorRun } from '../types'
import clsx from 'clsx'

function fmtRelative(iso: string | null) {
  if (!iso) return '–'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 2) return 'זה עתה'
  if (mins < 60) return `לפני ${mins} דקות`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `לפני ${hrs} שעות`
  return `לפני ${Math.floor(hrs / 24)} ימים`
}

function fmtDuration(ms: number | null) {
  if (ms == null) return '–'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

const STATUS_STYLES: Record<string, string> = {
  completed: 'bg-emerald-100 text-emerald-700',
  running: 'bg-blue-100 text-blue-700 animate-pulse',
  failed: 'bg-red-100 text-red-600',
  partial: 'bg-amber-100 text-amber-700',
}

const PROCESSOR_INFO: Array<{ name: string; label: string; description: string; icon: string }> = [
  {
    name: 'bank_processor',
    label: 'מעבד בנקאי',
    description: 'ממיר raw_transactions → transactions',
    icon: '🏦',
  },
  {
    name: 'budget_processor',
    label: 'מעבד תקציב',
    description: 'מסווג עסקאות לקטגוריות תקציב',
    icon: '🏷',
  },
]

export default function PipelineStatusPage() {
  const qc = useQueryClient()
  const [selectedProcessor, setSelectedProcessor] = useState<string>('all')

  const { data: allRuns = [], isLoading } = useQuery({
    queryKey: ['processor-runs'],
    queryFn: () => getProcessorRuns(undefined, 100),
    refetchInterval: 10000,
  })

  const { mutate: rebuild, isPending: isRebuilding } = useRebuildSnapshot()

  const triggerMut = useMutation({
    mutationFn: triggerProcessorRun,
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ['processor-runs'] }), 2000)
    },
  })

  const resetMut = useMutation({
    mutationFn: resetProcessorCheckpoint,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['processor-runs'] }),
  })

  function getLastRun(processorName: string): ProcessorRun | null {
    return allRuns.find((r: ProcessorRun) => r.processor_name === processorName) ?? null
  }

  const filteredRuns = selectedProcessor === 'all'
    ? allRuns
    : allRuns.filter((r: ProcessorRun) => r.processor_name === selectedProcessor)

  return (
    <div className="p-6 space-y-6 bg-gray-50 min-h-full" dir="rtl">

      {/* Stage cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        {/* Connectors */}
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xl">🔌</span>
            <div>
              <p className="text-[13px] font-semibold text-gray-800">קונקטורים</p>
              <p className="text-[11px] text-gray-400">מביאים raw_transactions</p>
            </div>
          </div>
          <div className="text-[11px] text-gray-500 space-y-1">
            <p>מזרחי טפחות: Upload ידני</p>
            <p>לאומי: Upload ידני</p>
            <p>כרטיסי אשראי: GitHub Actions (05:00 UTC)</p>
          </div>
          <div className="mt-3 pt-3 border-t border-gray-100">
            <p className="text-[11px] text-gray-400">הפעלה אוטומטית: 07:00 IL</p>
          </div>
        </div>

        {/* Processors */}
        {PROCESSOR_INFO.map((proc) => {
          const lastRun = getLastRun(proc.name)
          const canControl = isEnabled('processor_controls')

          return (
            <div key={proc.name} className="bg-white rounded-xl border border-gray-100 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">{proc.icon}</span>
                  <div>
                    <p className="text-[13px] font-semibold text-gray-800">{proc.label}</p>
                    <p className="text-[11px] text-gray-400">{proc.description}</p>
                  </div>
                </div>
                {lastRun && (
                  <span className={clsx('text-[10px] px-2 py-0.5 rounded-full font-medium', STATUS_STYLES[lastRun.status] ?? 'bg-gray-100 text-gray-500')}>
                    {lastRun.status}
                  </span>
                )}
              </div>

              {lastRun ? (
                <div className="text-[11px] text-gray-500 space-y-1">
                  <p>הרצה אחרונה: {fmtRelative(lastRun.started_at)}</p>
                  <p>שורות: {lastRun.rows_read} קרא / {lastRun.rows_written} כתב / {lastRun.rows_skipped} דילג</p>
                  <p>משך: {fmtDuration(lastRun.duration_ms)}</p>
                  {lastRun.error_message && (
                    <p className="text-red-500 text-[10px] truncate" title={lastRun.error_message}>
                      שגיאה: {lastRun.error_message}
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-[11px] text-gray-400">אין הרצות</p>
              )}

              {canControl && (
                <div className="mt-3 pt-3 border-t border-gray-100 flex gap-2">
                  <button
                    onClick={() => triggerMut.mutate(proc.name)}
                    disabled={triggerMut.isPending}
                    className="flex-1 py-1.5 text-[11px] bg-teal-50 text-teal-700 border border-teal-200 rounded-lg hover:bg-teal-100 disabled:opacity-50 transition-colors"
                  >
                    {triggerMut.isPending ? '…' : '▶ הפעל'}
                  </button>
                  <button
                    onClick={() => {
                      if (confirm('לאפס נקודת ביקורת? כל העסקאות יעובדו מחדש.')) {
                        resetMut.mutate(proc.name)
                      }
                    }}
                    disabled={resetMut.isPending}
                    className="py-1.5 px-2 text-[11px] text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
                    title="אפס נקודת ביקורת"
                  >
                    ↺
                  </button>
                </div>
              )}
            </div>
          )
        })}

        {/* Engine / Snapshot */}
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xl">⚡</span>
            <div>
              <p className="text-[13px] font-semibold text-gray-800">מנוע תמונת מצב</p>
              <p className="text-[11px] text-gray-400">מחשב ערכי תיק עדכניים</p>
            </div>
          </div>
          <div className="text-[11px] text-gray-500 space-y-1">
            <p>POST /api/v1/snapshots/rebuild</p>
            <p>הפעלה אוטומטית: 07:10 IL</p>
          </div>
          <div className="mt-3 pt-3 border-t border-gray-100">
            <button
              onClick={() => rebuild(undefined)}
              disabled={isRebuilding}
              className="w-full py-1.5 text-[12px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50 transition-colors"
            >
              {isRebuilding ? 'בונה…' : '⟳ בנה תמונת מצב'}
            </button>
          </div>
        </div>
      </div>

      {/* Recent runs table */}
      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <p className="text-[12px] font-semibold text-gray-700">הרצות אחרונות</p>
          <div className="flex gap-1">
            {(['all', ...PROCESSOR_INFO.map(p => p.name)] as const).map((p) => (
              <button
                key={p}
                onClick={() => setSelectedProcessor(p)}
                className={clsx(
                  'px-2 py-1 text-[10px] rounded font-medium transition-colors',
                  selectedProcessor === p
                    ? 'bg-gray-800 text-white'
                    : 'text-gray-500 hover:bg-gray-100',
                )}
              >
                {p === 'all' ? 'הכל' : p === 'bank_processor' ? 'בנקאי' : 'תקציב'}
              </button>
            ))}
          </div>
        </div>

        {isLoading ? (
          <div className="p-6 text-center text-gray-400 text-sm">טוען…</div>
        ) : filteredRuns.length === 0 ? (
          <div className="p-6 text-center text-gray-400 text-sm">אין הרצות</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-gray-100 text-gray-400 text-[10px] uppercase tracking-wide">
                  <th className="px-4 py-2 text-right">מעבד</th>
                  <th className="px-4 py-2 text-right">סטטוס</th>
                  <th className="px-4 py-2 text-right">התחיל</th>
                  <th className="px-4 py-2 text-left">קרא</th>
                  <th className="px-4 py-2 text-left">כתב</th>
                  <th className="px-4 py-2 text-left">דילג</th>
                  <th className="px-4 py-2 text-left">משך</th>
                  <th className="px-4 py-2 text-right">מופעל ע"י</th>
                </tr>
              </thead>
              <tbody>
                {filteredRuns.slice(0, 50).map((run: ProcessorRun) => (
                  <tr key={run.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                    <td className="px-4 py-2.5 font-mono text-[11px] text-gray-600">{run.processor_name}</td>
                    <td className="px-4 py-2.5">
                      <span className={clsx('text-[10px] px-2 py-0.5 rounded-full font-medium', STATUS_STYLES[run.status] ?? 'bg-gray-100 text-gray-500')}>
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-gray-500">{fmtRelative(run.started_at)}</td>
                    <td className="px-4 py-2.5 text-gray-700" dir="ltr">{run.rows_read ?? '–'}</td>
                    <td className="px-4 py-2.5 text-gray-700" dir="ltr">{run.rows_written ?? '–'}</td>
                    <td className="px-4 py-2.5 text-gray-400" dir="ltr">{run.rows_skipped ?? '–'}</td>
                    <td className="px-4 py-2.5 text-gray-500" dir="ltr">{fmtDuration(run.duration_ms)}</td>
                    <td className="px-4 py-2.5 text-gray-400">{run.triggered_by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
