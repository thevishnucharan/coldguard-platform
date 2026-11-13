import { API_BASE } from '../api/client'
import { useAuthStore } from '../../store/authStore'

export type RealtimeStatus = 'connecting' | 'open' | 'closed'
export interface RealtimeEvent { type: string; data: Record<string, unknown>; facility_id: string | null; ts: string }
type Listener = (e: RealtimeEvent) => void

/**
 * WebSocket client with exponential-backoff reconnection.
 * - Auth: the access token is sent as the first frame (never in the URL).
 * - After a reconnect a synthetic `resync` event is emitted so views re-fetch over REST,
 *   because events missed while disconnected are not replayed.
 * - Heartbeats from the server keep `lastMessageAt` fresh so the UI can flag a stale link.
 */
class RealtimeClient {
  private ws: WebSocket | null = null
  private listeners = new Map<string, Set<Listener>>()
  private statusListeners = new Set<(s: RealtimeStatus) => void>()
  private retry = 0
  private timer: number | undefined
  private wantOpen = false
  private everOpened = false
  status: RealtimeStatus = 'closed'
  lastMessageAt = 0

  private url() {
    const base = API_BASE.startsWith('http') ? API_BASE : `${window.location.origin}${API_BASE}`
    return base.replace(/^http/, 'ws') + '/ws'
  }

  private setStatus(s: RealtimeStatus) {
    this.status = s
    this.statusListeners.forEach((l) => l(s))
  }

  connect() {
    this.wantOpen = true
    if (this.ws && this.ws.readyState <= 1) return
    const token = useAuthStore.getState().accessToken
    if (!token) return
    this.setStatus('connecting')
    const ws = new WebSocket(this.url())
    this.ws = ws
    ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token }))
    ws.onmessage = (m) => {
      this.lastMessageAt = Date.now()
      let ev: RealtimeEvent
      try { ev = JSON.parse(m.data) } catch { return }
      if (ev.type === 'hello') {
        const reconnected = this.everOpened
        this.everOpened = true
        this.retry = 0
        this.setStatus('open')
        if (reconnected) this.emit({ type: 'resync', data: {}, facility_id: null, ts: new Date().toISOString() })
        return
      }
      if (ev.type === 'ping') { ws.send('pong'); return }
      this.emit(ev)
    }
    ws.onclose = (e) => {
      this.ws = null
      this.setStatus('closed')
      if (!this.wantOpen) return
      if (e.code === 4401) {
        // token expired: refresh then retry
        import('../api/client').then(({ refreshAccessToken }) => refreshAccessToken().then(() => this.schedule()))
        return
      }
      this.schedule()
    }
    ws.onerror = () => ws.close()
  }

  private schedule() {
    window.clearTimeout(this.timer)
    const delay = Math.min(30000, 1000 * 2 ** this.retry) + Math.random() * 500
    this.retry += 1
    this.timer = window.setTimeout(() => this.connect(), delay)
  }

  disconnect() {
    this.wantOpen = false
    this.everOpened = false
    window.clearTimeout(this.timer)
    this.ws?.close()
    this.ws = null
    this.setStatus('closed')
  }

  private emit(ev: RealtimeEvent) {
    this.listeners.get(ev.type)?.forEach((l) => l(ev))
    this.listeners.get('*')?.forEach((l) => l(ev))
  }

  on(type: string, l: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set())
    this.listeners.get(type)!.add(l)
    return () => { this.listeners.get(type)?.delete(l) }
  }

  onStatus(l: (s: RealtimeStatus) => void) {
    this.statusListeners.add(l)
    return () => { this.statusListeners.delete(l) }
  }
}

export const realtime = new RealtimeClient()
