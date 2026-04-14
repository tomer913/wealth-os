import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  getProcessorRuns, triggerProcessorRun, resetProcessorCheckpoint,
} from '../api/portfolio'
import { useRebuildSnapshot } from '../hooks/usePortfolio'
import { isEnabled } from '../config/features'
import type { ProcessorRun } from '../types'
import clsx from 'clsx'

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

  const processorDefs = [
    { name: 'bank_processor', labelKey: 'stages.bank_processor', descKey: 'bank_processor_desc' },
    { name: 'budget_processor', labelKey: 'stages.budget_processor', descKey: 'budget_processor_desc' },
  ]

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
                {lastRun && (
                  <span className={clsx('text-[10px] px-2 py-0.5 rounded-full font-medium', STATUS_STYLES[lastRun.status] ?? 'bg-gray-100 text-gray-500')}>
                    {tc(`status.${lastRun.status}`)}
                  </span>
                )}
              </div>

              {lastRun ? (
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
              ) : (
                <p className="text-[11px] text-gray-400">{t('processor.no_runs')}</p>
              )}

              {canControl && (
                <div className="mt-3 pt-3 border-t border-gray-100 flex gap-2">
                  <button
                    onClick={() => triggerMut.mutate(proc.name)}
                    disabled={triggerMut.isPending}
                    className="flex-1 py-1.5 text-[11px] bg-teal-50 text-teal-700 border border-teal-200 rounded-lg hover:bg-teal-100 disabled:opacity-50 transition-colors"
                  >
                    {triggerMut.isPending ? t('processor.triggering') : t('processor.trigger')}
                  </button>
                  <button
                    onClick={() => {
                      if (confirm(t('processor.reset_warning'))) {
                        resetMut.mutate(proc.name)
                      }
                    }}
                    disabled={resetMut.isPending}
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

        {/* Engine / Snapshot */}
        <div className="bg-white rounded-xl border border-gray-100 p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xl">⚡</span>
            <div>
              <p className="text-[13px] font-semibold text-gray-800">{t('stages.engine')}</p>
              <p className="text-[11px] text-gray-400">{t('engine_desc')}</p>
            </div>
          </div>
          <div className="text-[11px] text-gray-500 space-y-1">
            <p dir="ltr" className="text-right">{t('engine_endpoint')}</p>
            <p>{t('auto_run_time')}</p>
          </div>
          <div className="mt-3 pt-3 border-t border-gray-100">
            <button
              onClick={() => rebuild(undefined)}
              disabled={isRebuilding}
              className="w-full py-1.5 text-[12px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50 transition-colors"
            >
              {isRebuilding ? tc('building') : tc('build_snapshot')}
            </button>
          </div>
        </div>
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
                  selectedProcessor === key
                    ? 'bg-gray-800 text-white'
                    : 'text-gray-500 hover:bg-gray-100',
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
