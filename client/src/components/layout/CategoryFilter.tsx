import clsx from 'clsx'
import { useTranslation } from 'react-i18next'
import { useAppStore } from '../../store'
import { categoryLabel } from '../../utils/format'

export default function CategoryFilter() {
  const { t } = useTranslation('common')
  const snapshot = useAppStore((s) => s.snapshot)
  const selected = useAppStore((s) => s.selectedCategories)
  const toggle = useAppStore((s) => s.toggleCategory)
  const clear = useAppStore((s) => s.clearFilter)

  if (!snapshot) return null

  const categories = snapshot.categories.map((c) => c.category)
  const isAll = selected.length === 0

  return (
    <div className="bg-white border-b border-gray-100 flex-shrink-0 overflow-hidden">
    <div className="flex items-center gap-2 overflow-x-auto scrollbar-hide py-2.5 px-5">
      <Chip
        label={t('categories.all')}
        active={isAll}
        onClick={clear}
      />
      {categories.map((cat) => (
        <Chip
          key={cat}
          label={categoryLabel(cat, t)}
          active={selected.includes(cat)}
          onClick={() => toggle(cat)}
        />
      ))}
    </div>
    </div>
  )
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'px-3 py-1 rounded-full text-[12px] font-semibold whitespace-nowrap transition-all border',
        active
          ? 'bg-[#0d9488] text-white border-[#0d9488] shadow-sm'
          : 'bg-white text-gray-600 border-gray-300 hover:border-gray-400 hover:text-gray-900',
      )}
    >
      {label}
    </button>
  )
}
