import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from '../services/api/client'
import { realtime, type RealtimeEvent, type RealtimeStatus } from '../services/websocket/realtime'

interface Options {
  /** realtime event types that trigger a (debounced) background reload */
  refreshOn?: string[]
  /** fallback polling interval in ms (used regardless of websocket state) */
  interval?: number
  enabled?: boolean
}

/** Data fetching with loading/error state, realtime-triggered refresh and resync after reconnect. */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[], opts: Options = {}) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [updatedAt, setUpdatedAt] = useState<number | null>(null)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  const enabled = opts.enabled ?? true

  const load = useCallback(async (background = false) => {
    if (!background) setLoading(true)
    try {
      const d = await fetcherRef.current()
      setData(d)
      setError(null)
      setUpdatedAt(Date.now())
    } catch (e) {
      setError(errorMessage(e, 'Failed to load data'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (enabled) load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps])

  const refreshKey = (opts.refreshOn || []).join(',')
  useEffect(() => {
    if (!enabled) return
    let t: number | undefined
    const trigger = () => {
      window.clearTimeout(t)
      t = window.setTimeout(() => load(true), 800)
    }
    const offs = [...(opts.refreshOn || []), 'resync'].map((type) => realtime.on(type, trigger))
    const poll = opts.interval ? window.setInterval(() => load(true), opts.interval) : undefined
    return () => {
      offs.forEach((o) => o())
      window.clearTimeout(t)
      if (poll) window.clearInterval(poll)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, refreshKey, opts.interval, load])

  return { data, error, loading, reload: () => load(true), setData, updatedAt }
}

export function useRealtimeStatus() {
  const [status, setStatus] = useState<RealtimeStatus>(realtime.status)
  useEffect(() => realtime.onStatus(setStatus), [])
  return status
}

export function useRealtimeEvent(type: string, handler: (e: RealtimeEvent) => void) {
  const ref = useRef(handler)
  ref.current = handler
  useEffect(() => realtime.on(type, (e) => ref.current(e)), [type])
}

/** Re-render every `ms` so relative times ("12 s ago") and staleness stay truthful. */
export function useNow(ms = 10000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(t)
  }, [ms])
  return now
}
