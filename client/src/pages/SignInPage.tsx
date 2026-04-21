import { SignIn } from '@clerk/clerk-react'

export default function SignInPage() {
  const supportsPasskeys = typeof window !== 'undefined' && 'PublicKeyCredential' in window

  async function handlePasskey() {
    // authenticateWithPasskey available via window.Clerk (not yet typed in @clerk/clerk-react)
    const clerk = (window as any).Clerk
    if (clerk?.authenticateWithPasskey) {
      await clerk.authenticateWithPasskey()
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="flex flex-col items-center gap-6 w-full max-w-sm">
        {/* Branding */}
        <div className="text-center">
          <div className="w-12 h-12 bg-teal-600 rounded-2xl flex items-center justify-center mx-auto mb-3">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
          </div>
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight">Finova</h1>
          <p className="text-sm text-gray-500 mt-1">Portfolio Intelligence</p>
        </div>

        {/* Face ID / Passkey button — only on supporting devices */}
        {supportsPasskeys && (
          <button
            onClick={handlePasskey}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gray-900 text-white rounded-xl text-[14px] font-medium hover:bg-gray-800 transition-colors"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
              <path d="M8 12c0-2.21 1.79-4 4-4s4 1.79 4 4"/>
              <circle cx="12" cy="12" r="1.5" fill="currentColor"/>
            </svg>
            Sign in with Face ID / Passkey
          </button>
        )}

        {/* Clerk sign-in form */}
        <SignIn
          routing="path"
          path="/sign-in"
          afterSignInUrl="/"
          appearance={{
            elements: {
              rootBox: 'w-full',
              card: 'shadow-none border border-gray-200 rounded-2xl',
            },
          }}
        />
      </div>
    </div>
  )
}
