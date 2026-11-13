import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import type { Me } from '../types'

/**
 * Session state.
 * - The access token lives in memory only (never persisted).
 * - The refresh token is kept in sessionStorage (cleared when the tab closes) and rotated
 *   on every use by the API; reuse of an old token revokes the whole session server-side.
 * - Permissions here only drive the UI. Every request is re-authorised by the backend.
 */
interface AuthState {
  me: Me | null
  accessToken: string | null
  refreshToken: string | null
  setSession: (access: string, refresh: string) => void
  setMe: (me: Me) => void
  clear: () => void
  can: (...perms: string[]) => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      me: null,
      accessToken: null,
      refreshToken: null,
      setSession: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
      setMe: (me) => set({ me }),
      clear: () => set({ me: null, accessToken: null, refreshToken: null }),
      can: (...perms) => {
        const p = get().me?.permissions
        return !!p && perms.every((x) => p.includes(x))
      },
    }),
    {
      name: 'coldguard-session',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (s) => ({ refreshToken: s.refreshToken, me: s.me }),
    },
  ),
)

export const can = (...perms: string[]) => useAuthStore.getState().can(...perms)
