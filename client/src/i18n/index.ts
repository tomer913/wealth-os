import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

// Hebrew translations
import heCommon from './locales/he/common.json'
import heDashboard from './locales/he/dashboard.json'
import heAssets from './locales/he/assets.json'
import heAccounts from './locales/he/accounts.json'
import heTransactions from './locales/he/transactions.json'
import heValuations from './locales/he/valuations.json'
import heConnectors from './locales/he/connectors.json'
import heBudget from './locales/he/budget.json'
import hePipeline from './locales/he/pipeline.json'

// English translations
import enCommon from './locales/en/common.json'
import enDashboard from './locales/en/dashboard.json'
import enAssets from './locales/en/assets.json'
import enAccounts from './locales/en/accounts.json'
import enTransactions from './locales/en/transactions.json'
import enValuations from './locales/en/valuations.json'
import enConnectors from './locales/en/connectors.json'
import enBudget from './locales/en/budget.json'
import enPipeline from './locales/en/pipeline.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'he',
    supportedLngs: ['he', 'en'],
    defaultNS: 'common',
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'wealth_os_language',
    },
    resources: {
      he: {
        common: heCommon,
        dashboard: heDashboard,
        assets: heAssets,
        accounts: heAccounts,
        transactions: heTransactions,
        valuations: heValuations,
        connectors: heConnectors,
        budget: heBudget,
        pipeline: hePipeline,
      },
      en: {
        common: enCommon,
        dashboard: enDashboard,
        assets: enAssets,
        accounts: enAccounts,
        transactions: enTransactions,
        valuations: enValuations,
        connectors: enConnectors,
        budget: enBudget,
        pipeline: enPipeline,
      },
    },
  })

export default i18n
