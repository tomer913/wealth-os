import { useAuth, RedirectToSignIn } from '@clerk/clerk-react'
import { isEnabled } from '../../config/features'

function LoadingSpinner() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth()

  // Feature flag: skip auth in local dev when auth_enabled = false
  if (!isEnabled('auth_enabled')) {
    return <>{children}</>
  }

  if (!isLoaded) return <LoadingSpinner />
  if (!isSignedIn) return <RedirectToSignIn />
  return <>{children}</>
}
