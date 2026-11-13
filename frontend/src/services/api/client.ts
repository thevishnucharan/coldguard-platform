import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '../../store/authStore'
import type { ApiErrorShape } from '../../types'

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || '/api/v1'

export const api = axios.create({ baseURL: API_BASE, timeout: 30000 })

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing: Promise<string | null> | null = null

/** Single-flight refresh: concurrent 401s share one refresh request. */
export function refreshAccessToken(): Promise<string | null> {
  if (refreshing) return refreshing
  const { refreshToken, setSession, clear } = useAuthStore.getState()
  if (!refreshToken) return Promise.resolve(null)
  refreshing = axios
    .post(`${API_BASE}/auth/refresh`, { refresh_token: refreshToken })
    .then((r) => {
      setSession(r.data.access_token, r.data.refresh_token)
      return r.data.access_token as string
    })
    .catch(() => {
      clear()
      return null
    })
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined
    const isAuthCall = original?.url?.includes('/auth/login') || original?.url?.includes('/auth/refresh')
    if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true
      const token = await refreshAccessToken()
      if (token) {
        original.headers.Authorization = `Bearer ${token}`
        return api(original)
      }
      if (!window.location.pathname.startsWith('/login')) window.location.assign('/login?expired=1')
    }
    return Promise.reject(error)
  },
)

/** Human-readable error message from any API error. */
export function errorMessage(err: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as ApiErrorShape | undefined
    if (data?.errors?.length) return data.errors.map((e) => `${e.loc.slice(1).join('.')}: ${e.msg}`).join('; ')
    if (typeof data?.detail === 'string') return data.detail
    if (err.code === 'ECONNABORTED') return 'The server took too long to respond'
    if (!err.response) return 'Cannot reach the ColdGuard API'
    return `${fallback} (HTTP ${err.response.status})`
  }
  return err instanceof Error ? err.message : fallback
}

/** Authenticated file download (reports). Uses the Content-Disposition filename. */
export async function downloadFile(url: string, params?: Record<string, unknown>) {
  const r = await api.get(url, { params, responseType: 'blob' })
  const cd = (r.headers['content-disposition'] as string | undefined) || ''
  const name = /filename="?([^"]+)"?/.exec(cd)?.[1] || 'coldguard-report'
  const href = URL.createObjectURL(r.data as Blob)
  const a = document.createElement('a')
  a.href = href
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(href), 1000)
}
