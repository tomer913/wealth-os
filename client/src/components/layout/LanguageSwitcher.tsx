import { useTranslation } from 'react-i18next'

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const isHe = i18n.language === 'he'

  function toggle() {
    i18n.changeLanguage(isHe ? 'en' : 'he')
  }

  return (
    <button
      onClick={toggle}
      className="flex items-center gap-1 px-2.5 py-1 text-[12px] font-medium border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 transition-colors"
      // Intentionally show target language's own name — standard i18n toggle pattern
      title={isHe ? 'Switch to English' : '\u05E2\u05D1\u05D5\u05E8 \u05DC\u05E2\u05D1\u05E8\u05D9\u05EA'}
    >
      {/* Show target language label — intentionally not translated */}
      {isHe ? 'EN' : '\u05E2\u05D1'}
    </button>
  )
}
