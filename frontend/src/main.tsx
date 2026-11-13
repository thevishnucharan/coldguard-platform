import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Toaster } from 'react-hot-toast'
import { RouterProvider } from 'react-router-dom'
import './index.css'
import { router } from './app/router'
import { refreshAccessToken } from './services/api/client'
import { Auth } from './services/api/endpoints'
import { realtime } from './services/websocket/realtime'
import { useAuthStore } from './store/authStore'

/** Restore a session after reload: the access token is memory-only, so exchange the
 *  (rotating) refresh token, re-read /auth/me (permissions come from the server), then
 *  open the realtime channel. */
function Bootstrap() {
  const [ready, setReady] = useState(false)
  const token = useAuthStore((s) => s.accessToken)
  useEffect(() => {
    (async () => {
      const s = useAuthStore.getState()
      if (!s.accessToken && s.refreshToken) {
        const t = await refreshAccessToken()
        if (t) {
          try { s.setMe(await Auth.me()) } catch { s.clear() }
        }
      }
      setReady(true)
    })()
  }, [])
  useEffect(() => {
    if (token) realtime.connect()
    else realtime.disconnect()
  }, [token])
  if (!ready) return <div className="grid h-full place-items-center text-sm text-ink-3">Loading ColdGuard…</div>
  return <RouterProvider router={router} />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Toaster position="top-right" toastOptions={{ style: { fontSize: 13, borderRadius: 10 }, duration: 3500 }} />
    <Bootstrap />
  </StrictMode>,
)
