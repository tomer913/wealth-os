import clsx from 'clsx'

export interface MetaPair {
  key: string
  value: string
}

interface MetadataEditorProps {
  pairs: MetaPair[]
  onChange: (pairs: MetaPair[]) => void
}

export function MetadataEditor({ pairs, onChange }: MetadataEditorProps) {
  const update = (index: number, field: 'key' | 'value', val: string) => {
    const updated = pairs.map((p, i) => i === index ? { ...p, [field]: val } : p)
    onChange(updated)
  }

  const add = () => onChange([...pairs, { key: '', value: '' }])

  const remove = (index: number) => onChange(pairs.filter((_, i) => i !== index))

  return (
    <div className="space-y-2">
      {pairs.map((pair, i) => (
        <div key={i} className="flex gap-2 items-center">
          <input
            type="text"
            placeholder="key"
            value={pair.key}
            onChange={(e) => update(i, 'key', e.target.value)}
            className="w-1/3 px-3 py-1.5 text-[12px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 bg-gray-50 font-mono"
          />
          <span className="text-gray-300 text-[12px]">:</span>
          <input
            type="text"
            placeholder="value"
            value={pair.value}
            onChange={(e) => update(i, 'value', e.target.value)}
            className="flex-1 px-3 py-1.5 text-[12px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400"
          />
          <button
            type="button"
            onClick={() => remove(i)}
            className="w-6 h-6 flex items-center justify-center text-gray-300 hover:text-rose-400 transition-colors flex-shrink-0"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M1 1l10 10M11 1L1 11"/>
            </svg>
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="flex items-center gap-1.5 text-[12px] text-teal-600 hover:text-teal-700 font-medium transition-colors mt-1"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M6 1v10M1 6h10"/>
        </svg>
        Add field
      </button>
    </div>
  )
}

// ─── Helpers to convert between MetaPair[] and JSON object ────────────────────

export function pairsToJson(pairs: MetaPair[]): Record<string, string> {
  return Object.fromEntries(
    pairs.filter((p) => p.key.trim()).map((p) => [p.key.trim(), p.value])
  )
}

export function jsonToPairs(obj: Record<string, unknown> | null | undefined): MetaPair[] {
  if (!obj) return []
  return Object.entries(obj).map(([key, value]) => ({
    key,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  }))
}
