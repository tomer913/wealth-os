import { useNavigate } from 'react-router-dom'
import { useAuth } from '@clerk/clerk-react'
import { createPortfolio } from '../api/portfolio'
import { useAppStore } from '../store'
import { useState } from 'react'

export default function SetupPage() {
  const navigate = useNavigate()
  const { userId } = useAuth()
  const setActivePortfolioId = useAppStore((s) => s.setActivePortfolioId)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleStart() {
    setLoading(true)
    setError('')
    try {
      const portfolio = await createPortfolio({
        name: 'My Portfolio',
        base_currency: 'ILS',
        is_default: true,
      })
      setActivePortfolioId(portfolio.id)
      localStorage.setItem('last_portfolio_id', portfolio.id)
      navigate('/')
    } catch (e) {
      setError('Failed to create portfolio. Please try again.')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-6">
      <div className="text-center max-w-md">
        <div className="w-16 h-16 bg-teal-50 rounded-2xl flex items-center justify-center mx-auto mb-6">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#0d9488" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="3"/>
            <path d="M12 8v8M8 12h8"/>
          </svg>
        </div>
        <h1 className="text-2xl font-semibold text-gray-900 mb-2">Welcome to Finova</h1>
        <p className="text-gray-500 text-[15px] leading-relaxed mb-8">
          Let's set up your portfolio. We'll create a default portfolio to get you started.
        </p>
        {error && (
          <p className="text-rose-600 text-sm mb-4">{error}</p>
        )}
        <button
          onClick={handleStart}
          disabled={loading}
          className="px-6 py-3 bg-teal-600 text-white rounded-xl font-medium text-[15px] hover:bg-teal-700 transition-colors disabled:opacity-50"
        >
          {loading ? 'Creating…' : 'Get Started'}
        </button>
      </div>
    </div>
  )
}
