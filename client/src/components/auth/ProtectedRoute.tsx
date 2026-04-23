import { useAuth, RedirectToSignIn } from '@clerk/clerk-react'
import { FEATURES } from '../../config/features'

function LoadingSpinner() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

// Split into two components so useAuth() is only called when ClerkProvider is in the tree.
// Calling useAuth() outside ClerkProvider crashes — this guard prevents that.
function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth()
  if (!isLoaded) return <LoadingSpinner />
  if (!isSignedIn) return <RedirectToSignIn />
  return <>{children}</>
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!FEATURES.auth_enabled) return <>{children}</>
  return <AuthGuard>{children}</AuthGuard>
}
