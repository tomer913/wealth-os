import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  getProcessorRuns, triggerProcessorRun, resetProcessorCheckpoint,
  getProcessorRun, rebuildSnapshot, getRecentSnapshots,
} from '../api/portfolio'
import { isEnabled } from '../config/features'
import type { ProcessorRun } from '../types'
import clsx from 'clsx'

const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS = 5 * 60 * 1000  // 5 minutes

function fmtDuration(ms: number | null) {
  if (ms == null) return '–'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

const STATUS_STYLES: Record<string, string> = {
  completed: 'bg-emerald-100 text-emerald-700',
  running:   'bg-blue-100 text-blue-700 animate-pulse',
  failed:    'bg-red-100 text-red-600',
  partial:   'bg-amber-100 text-amber-700',
  success:   'bg-emerald-100 text-emerald-700',
  pending:   'bg-gray-100 text-gray-500',
}

// ─── Processor run state per card ─────────────────────────────────────────────
interface RunState {
  phase: 'idle' | 'running' | 'done' | 'error'
  rows_read?: number | null
  rows_written?: number | null
  rows_skipped?: number | null
  error?: string | null
}

// ─── Hook: trigger + poll a processor run ─────────────────────────────────────
function useProcessorTrigger(processorName: string, onComplete: () => void) {
  const [state, setState] = useState<RunState>({ phase: 'idle' })
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const deadlineRef = useRef<number>(0)

  function stopPolling() {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
  }

  async function trigger() {
    if (state.phase === 'running') return
    setState({ phase: 'running' })
    try {
      const { run_id } = await triggerProcessorRun(processorName)
      deadlineRef.current = Date.now() + POLL_TIMEOUT_MS

      timerRef.current = setInterval(async () => {
        if (Date.now() > deadlineRef.current) {
          stopPolling()
          setState({ phase: 'error', error: 'Timed out after 5 minutes' })
          return
        }
        try {
          const run = await getProcessorRun(run_id)
          if (run.status === 'success') {
            stopPolling()
            setState({
              phase: 'done',
              rows_read: run.rows_read,
              rows_written: run.rows_written,
              rows_skipped: run.rows_skipped,
            })
            onComplete()
          } else if (run.status === 'failed') {
            stopPolling()
            setState({ phase: 'error', error: run.error_message })
            onComplete()
          } else if (run.status === 'running' || run.status === 'pending') {
            setState(prev => ({
              ...prev,
              phase: 'running',
              rows_read: run.rows_read,
              rows_written: run.rows_written,
              rows_skipped: run.rows_skipped,
            }))
          }
        } catch {
          // transient fetch error — keep polling
        }
      }, POLL_INTERVAL_MS)

    } catch (e: unknown) {
      setState({ phase: 'error', error: String(e) })
    }
  }

  function reset() { stopPolling(); setState({ phase: 'idle' }) }

  useEffect(() => () => stopPolling(), [])

  return { state, trigger, reset }
}

// ─── Main page ─────────────────────────────────────────────────────────────────
export default function PipelineStatusPage() {
  const { t } = useTranslation('pipeline')
  const { t: tc } = useTranslation('common')
  const qc = useQueryClient()
  const [selectedProcessor, setSelectedProcessor] = useState<string>('all')

  const { data: allRuns = [], isLoading } = useQuery({
    queryKey: ['processor-runs'],
    queryFn: () => getProcessorRuns(undefined, 100),
    refetchInterval: 10000,
  })

  function fmtRelative(iso: string | null) {
    if (!iso) return '–'
    const diff = Date.now() - new Date(iso).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 2) return tc('time.just_now')
    if (mins < 60) return tc('time.minutes_ago', { count: mins })
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return tc('time.hours_ago', { count: hrs })
    return tc('time.days_ago', { count: Math.floor(hrs / 24) })
  }

  function invalidateRuns() {
    setTimeout(() => qc.invalidateQueries({ queryKey: ['processor-runs'] }), 1500)
  }

  const bankTrigger   = useProcessorTrigger('bank_processor', invalidateRuns)
  const budgetTrigger = useProcessorTrigger('budget_processor', invalidateRuns)

  const processorDefs = [
    { name: 'bank_processor',   labelKey: 'stages.bank_processor',   descKey: 'bank_processor_desc',   trigger: bankTrigger   },
    { name: 'budget_processor', labelKey: 'stages.budget_processor',  descKey: 'budget_processor_desc', trigger: budgetTrigger },
  ]

  function getLastRun(processorName: string): ProcessorRun | null {
    return allRuns.find((r: ProcessorRun) => r.processor_name === processorName) ?? null
  }

  const filteredRuns = selectedProcessor === 'all'
    ? allRuns
    : allRuns.filter((r: ProcessorRun) => r.processor_name === selectedProcessor)

  return (
    <div className="p-6 space-y-6 bg-gray-50 min-h-full" dir="rtl">

      {/* Stage cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">

        {/* Connectors */}
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xl">🔌</span>
            <div>
              <p className="text-[13px] font-semibold text-gray-800">{t('stages.connectors')}</p>
              <p className="text-[11px] text-gray-400">{t('connectors_desc')}</p>
            </div>
          </div>
          <div className="text-[11px] text-gray-500 space-y-1">
            <p>{t('connectors_mizrachi')}</p>
            <p>{t('connectors_leumi')}</p>
            <p>{t('connectors_cards')}</p>
          </div>
          <div className="mt-3 pt-3 border-t border-gray-100">
            <p className="text-[11px] text-gray-400">{t('auto_run_time')}</p>
          </div>
        </div>

        {/* Processor cards */}
        {processorDefs.map((proc) => {
          const lastRun = getLastRun(proc.name)
          const canControl = isEnabled('processor_controls')
          const { state, trigger } = proc.trigger

          return (
            <div key={proc.name} className="bg-white rounded-xl border border-gray-100 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">{proc.name === 'bank_processor' ? '🏦' : '🏷'}</span>
                  <div>
                    <p className="text-[13px] font-semibold text-gray-800">{t(proc.labelKey)}</p>
                    <p className="text-[11px] text-gray-400">{t(proc.descKey)}</p>
                  </div>
                </div>
                {state.phase === 'idle' && lastRun && (
                  <span className={clsx('text-[10px] px-2 py-0.5 rounded-full font-medium', STATUS_STYLES[lastRun.status] ?? 'bg-gray-100 text-gray-500')}>
                    {tc(`status.${lastRun.status}`)}
                  </span>
                )}
                {state.phase === 'running' && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-blue-100 text-blue-700 animate-pulse">
                    {tc('status.running')}
                  </span>
                )}
                {state.phase === 'done' && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-emerald-100 text-emerald-700">
                    {tc('status.completed')}
                  </span>
                )}
                {state.phase === 'error' && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-600">
                    {tc('status.failed')}
                  </span>
                )}
              </div>

              {/* Last run info (idle) */}
              {state.phase === 'idle' && lastRun ? (
                <div className="text-[11px] text-gray-500 space-y-1">
                  <p>{t('processor.last_run', { time: fmtRelative(lastRun.started_at) })}</p>
                  <p>{t('processor.rows', { read: lastRun.rows_read, written: lastRun.rows_written, skipped: lastRun.rows_skipped })}</p>
                  <p>{t('processor.duration', { duration: fmtDuration(lastRun.duration_ms) })}</p>
                  {lastRun.error_message && (
                    <p className="text-red-500 text-[10px] truncate" title={lastRun.error_message}>
                      {t('processor.error', { message: lastRun.error_message })}
                    </p>
                  )}
                </div>
              ) : state.phase === 'idle' ? (
                <p className="text-[11px] text-gray-400">{t('processor.no_runs')}</p>
              ) : null}

              {/* Running state */}
              {state.phase === 'running' && (
                <div className="text-[11px] text-blue-600 space-y-1">
                  <div className="flex items-center gap-1.5">
                    <svg className="animate-spin flex-shrink-0" width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5.5 1v2M5.5 8v2M1 5.5h2M8 5.5h2" strokeLinecap="round"/></svg>
                    <span>{t('processor.running')}</span>
                  </div>
                  {(state.rows_read != null || state.rows_written != null) && (
                    <p className="text-gray-500">{t('processor.rows', { read: state.rows_read ?? 0, written: state.rows_written ?? 0, skipped: state.rows_skipped ?? 0 })}</p>
                  )}
                </div>
              )}

              {/* Done state */}
              {state.phase === 'done' && (
                <div className="text-[11px] text-emerald-700 space-y-1">
                  <p>{t('processor.rows', { read: state.rows_read ?? 0, written: state.rows_written ?? 0, skipped: state.rows_skipped ?? 0 })}</p>
                </div>
              )}

              {/* Error state */}
              {state.phase === 'error' && (
                <p className="text-[11px] text-red-500 truncate" title={state.error ?? undefined}>
                  {state.error ?? t('processor.error', { message: '?' })}
                </p>
              )}

              {canControl && (
                <div className="mt-3 pt-3 border-t border-gray-100 flex gap-2">
                  <button
                    onClick={() => state.phase === 'idle' ? trigger() : proc.trigger.reset()}
                    disabled={state.phase === 'running'}
                    className="flex-1 py-1.5 text-[11px] bg-teal-50 text-teal-700 border border-teal-200 rounded-lg hover:bg-teal-100 disabled:opacity-50 transition-colors"
                  >
                    {state.phase === 'running'
                      ? t('processor.triggering')
                      : state.phase === 'done' || state.phase === 'error'
                        ? t('processor.run_again')
                        : t('processor.trigger')}
                  </button>
                  <button
                    onClick={async () => {
                      if (confirm(t('processor.reset_warning'))) {
                        await resetProcessorCheckpoint(proc.name)
                      }
                    }}
                    disabled={state.phase === 'running'}
                    className="py-1.5 px-2 text-[11px] text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
                    title={t('processor.reset_title')}
                  >
                    {t('processor.reset_title')}
                  </button>
                </div>
              )}
            </div>
          )
        })}

        {/* Engine / Snapshot card */}
        <EngineCard />
      </div>

      {/* Recent runs table */}
      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <p className="text-[12px] font-semibold text-gray-700">{t('recent_runs')}</p>
          <div className="flex gap-1">
            {([
              { key: 'all', label: t('filter_all') },
              { key: 'bank_processor', label: t('filter_bank') },
              { key: 'budget_processor', label: t('filter_budget') },
            ]).map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setSelectedProcessor(key)}
                className={clsx(
                  'px-2 py-1 text-[10px] rounded font-medium transition-colors',
                  selectedProcessor === key ? 'bg-gray-800 text-white' : 'text-gray-500 hover:bg-gray-100',
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {isLoading ? (
          <div className="p-6 text-center text-gray-400 text-sm">{tc('status.loading')}</div>
        ) : filteredRuns.length === 0 ? (
          <div className="p-6 text-center text-gray-400 text-sm">{t('processor.no_runs')}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-gray-100 text-gray-400 text-[10px] uppercase tracking-wide">
                  <th className="px-4 py-2 text-right">{t('columns.processor')}</th>
                  <th className="px-4 py-2 text-right">{t('columns.status')}</th>
                  <th className="px-4 py-2 text-right">{t('columns.started')}</th>
                  <th className="px-4 py-2 text-left">{t('columns.read')}</th>
                  <th className="px-4 py-2 text-left">{t('columns.written')}</th>
                  <th className="px-4 py-2 text-left">{t('columns.skipped')}</th>
                  <th className="px-4 py-2 text-left">{t('columns.duration')}</th>
                  <th className="px-4 py-2 text-right">{t('columns.triggered_by')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredRuns.slice(0, 50).map((run: ProcessorRun) => (
                  <tr key={run.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                    <td className="px-4 py-2.5 font-mono text-[11px] text-gray-600">{run.processor_name}</td>
                    <td className="px-4 py-2.5">
                      <span className={clsx('text-[10px] px-2 py-0.5 rounded-full font-medium', STATUS_STYLES[run.status] ?? 'bg-gray-100 text-gray-500')}>
                        {tc(`status.${run.status}`)}
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

// ─── Engine card with date picker + recent snapshots ──────────────────────────
function EngineCard() {
  const { t } = useTranslation('pipeline')
  const { t: tc } = useTranslation('common')

  const todayStr = new Date().toISOString().split('T')[0]
  const [asOfDate, setAsOfDate] = useState(todayStr)
  const [building, setBuilding] = useState(false)
  const [buildResult, setBuildResult] = useState<string | null>(null)
  const [buildError, setBuildError] = useState<string | null>(null)

  const { data: recentSnapshots = [], refetch: refetchRecent } = useQuery({
    queryKey: ['recent-snapshots'],
    queryFn: () => getRecentSnapshots(5),
  })

  async function handleBuild() {
    setBuilding(true)
    setBuildResult(null)
    setBuildError(null)
    try {
      const result = await rebuildSnapshot(asOfDate)
      const assetCount = result?.summary?.asset_count ?? '?'
      setBuildResult(`${asOfDate} — ${assetCount} assets`)
      refetchRecent()
    } catch (e: unknown) {
      setBuildError(String(e))
    } finally {
      setBuilding(false)
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-100 p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xl">⚡</span>
        <div>
          <p className="text-[13px] font-semibold text-gray-800">{t('stages.engine')}</p>
          <p className="text-[11px] text-gray-400">{t('engine_desc')}</p>
        </div>
      </div>

      <div className="text-[11px] text-gray-500 space-y-1 mb-3">
        <p dir="ltr" className="text-right">{t('engine_endpoint')}</p>
      </div>

      {/* Date picker */}
      <div className="mb-2">
        <label className="text-[10px] text-gray-400 block mb-1">{t('engine_date_label')}</label>
        <input
          type="date"
          value={asOfDate}
          max={todayStr}
          onChange={e => { setAsOfDate(e.target.value); setBuildResult(null); setBuildError(null) }}
          className="w-full px-2 py-1.5 text-[12px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400"
          dir="ltr"
        />
      </div>

      <button
        onClick={handleBuild}
        disabled={building}
        className="w-full py-1.5 text-[12px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5"
      >
        {building && (
          <svg className="animate-spin" width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="white" strokeWidth="2"><path d="M5.5 1v2M5.5 8v2M1 5.5h2M8 5.5h2" strokeLinecap="round"/></svg>
        )}
        {building ? tc('building') : t('engine_build_for', { date: asOfDate })}
      </button>

      {buildResult && (
        <p className="mt-2 text-[10px] text-emerald-600 text-center">✓ {buildResult}</p>
      )}
      {buildError && (
        <p className="mt-2 text-[10px] text-red-500 text-center truncate" title={buildError}>{buildError}</p>
      )}

      {/* Last 5 snapshots */}
      {recentSnapshots.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <p className="text-[10px] text-gray-400 uppercase tracking-wide mb-1.5">{t('engine_recent_snapshots')}</p>
          <div className="space-y-1">
            {recentSnapshots.map(snap => (
              <div key={snap.snapshot_date} className="flex items-center justify-between text-[11px]">
                <span className="text-gray-600 font-mono" dir="ltr">{snap.snapshot_date}</span>
                <span className="text-gray-400">{snap.asset_count} assets</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
