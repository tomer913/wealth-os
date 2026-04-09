import axios from 'axios'

// Single axios instance — all API calls go through here.
// Auth-ready: when you add Clerk/Auth0 later, add one line to the
// request interceptor below and every call gets the token automatically.

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'https://your-railway-url.railway.app',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// REQUEST interceptor — add auth token here when ready
apiClient.interceptors.request.use(
  (config) => {
    // TODO (v2): const token = getToken()
    // if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  },
  (error) => Promise.reject(error),
)

// RESPONSE interceptor — global error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // TODO (v2): redirect to login
      console.warn('Unauthorized — add auth in v2')
    }
    return Promise.reject(error)
  },
)

export default apiClient
