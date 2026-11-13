import { create } from 'zustand'

export type Theme = 'light' | 'dark'
const KEY = 'coldguard-theme'

function initial(): Theme {
  const t = typeof document !== 'undefined' ? document.documentElement.dataset.theme : undefined
  return t === 'dark' ? 'dark' : 'light'
}

/** Viewer preference only (localStorage); index.html applies it before first paint to avoid a flash. */
export const useThemeStore = create<{ theme: Theme; toggle: () => void }>((set, get) => ({
  theme: initial(),
  toggle: () => {
    const theme: Theme = get().theme === 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem(KEY, theme) } catch { /* storage blocked */ }
    set({ theme })
  },
}))
