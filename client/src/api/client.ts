import axios from 'axios'

// Single axios instance — all API calls go through here.
// Auth-ready: when you add Clerk/Auth0 later, add one line to the
// request interceptor below and every call gets the token automatically.

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'https://your-railway-url.railway.app',
  timeout: 30_000,
  maxRedirects: 5,
  headers: {
    'Content-Type': 'application/json',
  },
})

// REQUEST interceptor — attach Clerk JWT when available
apiClient.interceptors.request.use(
  async (config) => {
    try {
      // window.Clerk is set by ClerkProvider; works outside React components
      const token = await (window as any).Clerk?.session?.getToken()
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
    } catch {
      // Not signed in or Clerk not loaded yet — proceed without token
    }
    return config
  },
  (error) => Promise.reject(error),
)

// RESPONSE interceptor — global error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clerk will handle redirect via ProtectedRoute / RedirectToSignIn
      console.warn('Unauthorized — Clerk session may have expired')
    }
    return Promise.reject(error)
  },
)

export default apiClient
