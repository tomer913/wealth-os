import './i18n'
import i18n from './i18n'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'
import { useAppStore } from './store'
import { FEATURES } from './config/features'

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

// Expose store on window so api/portfolio.ts can access activePortfolioId
// without creating a circular dependency
;(window as unknown as { __wealthOsStore: typeof useAppStore }).__wealthOsStore = useAppStore

// Set document direction and language based on i18n
function applyDir(lng: string) {
  document.documentElement.dir = lng === 'he' ? 'rtl' : 'ltr'
  document.documentElement.lang = lng
}
applyDir(i18n.language)
i18n.on('languageChanged', applyDir)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
})

if (!publishableKey && FEATURES.auth_enabled) {
  document.getElementById('root')!.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:center;
                height:100vh;font-family:sans-serif;flex-direction:column;gap:16px;
                color:#111">
      <h2 style="margin:0">Configuration Error</h2>
      <p style="margin:0">VITE_CLERK_PUBLISHABLE_KEY is not set.</p>
      <p style="margin:0;color:#666">Add it to Vercel environment variables and redeploy.</p>
    </div>
  `
} else {
  // ClerkProvider must be outermost so all Clerk hooks work inside BrowserRouter/App
  const app = (
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>
  )

  ReactDOM.createRoot(document.getElementById('root')!).render(
    FEATURES.auth_enabled && publishableKey
      ? <ClerkProvider publishableKey={publishableKey}>{app}</ClerkProvider>
      : app
  )
}
