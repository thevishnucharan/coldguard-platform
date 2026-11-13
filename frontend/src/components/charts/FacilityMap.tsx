import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { ArrowRight, X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useThemeStore } from '../../store/themeStore'
import type { FacilitySummary } from '../../types'
import { HealthBadge, healthColor } from '../common/Status'

/**
 * Geographic facility map (Leaflet + Esri Canvas basemap, keyless; © Esri, © OpenStreetMap contributors).
 * Layers:
 *  - "status": every facility gets a catchment area shaded by its health (risk-map style)
 *  - "region": one district area per region, tinted per region
 * Pins carry colour AND a text label + tooltip; a legend is always shown (never colour alone).
 * Basemap follows the light/dark theme. Without internet the overlays still render on a plain canvas.
 */
export type MapLayer = 'status' | 'region'
const REGION_TINTS = ['#2a78d6', '#eb6834', '#1baf7a', '#6250d6', '#e87ba4']
const HEALTH_LABEL: Record<string, string> = {
  NORMAL: 'Normal', WARNING: 'Warning', MISSING_TELEMETRY: 'Missing data', OFFLINE: 'Offline', CRITICAL: 'Critical', NO_DATA: 'No data',
}
const RANK: Record<string, number> = { NORMAL: 0, NO_DATA: 1, WARNING: 2, MISSING_TELEMETRY: 3, OFFLINE: 4, CRITICAL: 5 }

function hull(pts: [number, number][]): [number, number][] {
  const p = [...pts].sort((a, b) => a[0] - b[0] || a[1] - b[1])
  if (p.length < 3) return p
  const cross = (o: number[], a: number[], b: number[]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
  const lo: [number, number][] = []
  for (const q of p) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q) }
  const up: [number, number][] = []
  for (const q of [...p].reverse()) { while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], q) <= 0) up.pop(); up.push(q) }
  return [...lo.slice(0, -1), ...up.slice(0, -1)]
}

/** Organic-looking area: hull of a jittered circular buffer around the points. */
function districtArea(points: [number, number][], radiusDeg: number, seed = 1): [number, number][] {
  const buf: [number, number][] = []
  let s = seed
  const rnd = () => { s = (s * 9301 + 49297) % 233280; return s / 233280 }
  for (const [lat, lng] of points) {
    for (let k = 0; k < 28; k++) {
      const a = (k / 28) * Math.PI * 2
      const r = radiusDeg * (0.82 + rnd() * 0.3)
      buf.push([lat + Math.sin(a) * r, lng + Math.cos(a) * r * 1.05])
    }
  }
  return hull(buf)
}

function pinIcon(f: FacilitySummary, selected: boolean) {
  const alert = f.critical_incidents > 0 ? '<span class="cg-pin-alert">!</span>' : ''
  return L.divIcon({
    className: 'cg-pin-wrap', iconSize: [0, 0],
    html: `<div class="cg-pin ${selected ? 'is-selected' : ''}" style="--pin:${healthColor(f.health)}">
             <span class="cg-pin-dot">${alert}</span><span class="cg-pin-label">${f.code}</span></div>`,
  })
}

export function tiles(theme: 'light' | 'dark') {
  const esri = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas'
  const base = theme === 'dark' ? 'World_Dark_Gray_Base' : 'World_Light_Gray_Base'
  const ref = theme === 'dark' ? 'World_Dark_Gray_Reference' : 'World_Light_Gray_Reference'
  return L.layerGroup([
    L.tileLayer(`${esri}/${base}/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 16, attribution: 'Basemap &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors' }),
    L.tileLayer(`${esri}/${ref}/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 16, pane: 'shadowPane' }),
  ])
}

export function FacilityMap({ facilities, selectedId, onSelect, height = 420, layer = 'status', children }: {
  facilities: FacilitySummary[]; selectedId?: string | null; onSelect?: (f: FacilitySummary) => void; height?: number
  layer?: MapLayer; children?: ReactNode
}) {
  const theme = useThemeStore((s) => s.theme)
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const overlay = useRef<L.LayerGroup | null>(null)
  const base = useRef<L.LayerGroup | null>(null)
  const fitted = useRef(false)
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true, scrollWheelZoom: false, attributionControl: true })
    L.control.scale({ imperial: false }).addTo(m)
    m.setView([13.5, 76.5], 7)
    const zoomClass = () => el.current?.classList.toggle('cg-zoom-low', m.getZoom() < 10)
    m.on('zoomend', zoomClass)
    zoomClass()
    map.current = m
    overlay.current = L.layerGroup().addTo(m)
    const ro = new ResizeObserver(() => m.invalidateSize())
    ro.observe(el.current)
    return () => { ro.disconnect(); m.remove(); map.current = null; fitted.current = false; base.current = null }
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m) return
    base.current?.remove()
    base.current = tiles(theme).addTo(m)
  }, [theme])

  useEffect(() => {
    const m = map.current, lg = overlay.current
    if (!m || !lg) return
    lg.clearLayers()
    const pts = facilities.filter((f) => f.latitude !== null && f.longitude !== null)
    const byRegion = new Map<string, { name: string; pts: [number, number][] }>()
    pts.forEach((f) => {
      const r = byRegion.get(f.region_id) || { name: f.region_name || 'Region', pts: [] }
      r.pts.push([f.latitude!, f.longitude!])
      byRegion.set(f.region_id, r)
    })
    ;[...byRegion.values()].forEach((r, i) => {
      const tint = REGION_TINTS[i % REGION_TINTS.length]
      const ring = districtArea(r.pts, 0.2, i + 3)
      L.polygon(ring, {
        color: layer === 'region' ? tint : '#5b6b82', weight: 1.4, opacity: 0.7, dashArray: '5 5',
        fillColor: tint, fillOpacity: layer === 'region' ? 0.2 : 0.03, smoothFactor: 2, interactive: false,
      }).addTo(lg)
      const north = ring.reduce((a, b) => (b[0] > a[0] ? b : a))
      L.tooltip({ permanent: true, direction: 'top', className: 'cg-region-label', offset: [0, -2] }).setLatLng(north).setContent(r.name).addTo(lg)
    })
    if (layer === 'status') {
      // catchment area per facility, worst status drawn last (on top)
      ;[...pts].sort((a, b) => (RANK[a.health] ?? 0) - (RANK[b.health] ?? 0)).forEach((f, i) => {
        const c = healthColor(f.health)
        L.polygon(districtArea([[f.latitude!, f.longitude!]], 0.075, i + 11), {
          color: c, weight: 1.5, opacity: 0.9, fillColor: c, fillOpacity: 0.32, smoothFactor: 1.5, interactive: false,
        }).addTo(lg)
      })
    }
    pts.forEach((f) => {
      const mk = L.marker([f.latitude!, f.longitude!], { icon: pinIcon(f, f.id === selectedId), keyboard: true, title: `${f.name}: ${HEALTH_LABEL[f.health] || f.health}` })
      mk.bindTooltip(`<b>${f.name}</b><br/>${HEALTH_LABEL[f.health] || f.health} · ${f.active_incidents} active incident(s)<br/>${f.sensors_online}/${f.sensors_total} sensors online`,
        { direction: 'top', offset: [0, -14] })
      mk.on('click', () => onSelectRef.current?.(f))
      mk.addTo(lg)
    })
    if (!fitted.current && pts.length) {
      m.fitBounds(L.latLngBounds(pts.map((f) => [f.latitude!, f.longitude!] as [number, number])).pad(0.25), { maxZoom: 10 })
      fitted.current = true
    }
  }, [facilities, selectedId, layer])

  useEffect(() => {
    const f = facilities.find((x) => x.id === selectedId)
    if (f && f.latitude !== null && map.current) map.current.panTo([f.latitude, f.longitude!], { animate: true })
  }, [selectedId, facilities])

  return (
    <div className="relative">
      <div ref={el} style={{ height }} className="w-full rounded-xl overflow-hidden border border-line bg-surface-2 z-0" role="region" aria-label="Facility map" />
      <div className="absolute left-2 bottom-7 z-[500] flex flex-wrap gap-x-3 gap-y-1 rounded-lg bg-surface/95 px-2.5 py-1.5 text-[11px] text-ink-2 border border-line shadow-sm">
        {[['NORMAL', 'Normal'], ['WARNING', 'Warning'], ['MISSING_TELEMETRY', 'Missing data'], ['CRITICAL', 'Critical / offline']].map(([h, l]) => (
          <span key={h} className="flex items-center gap-1"><span className="size-2.5 rounded-full" style={{ background: healthColor(h) }} />{l}</span>
        ))}
      </div>
      {children}
    </div>
  )
}

/** Floating facility card shown over the map (risk-map "district" card). */
export function FacilityMapCard({ facility, onClose, rows, to, action = 'Inspect facility' }: {
  facility: FacilitySummary; onClose: () => void; rows: [string, ReactNode][]; to: string; action?: string
}) {
  return (
    <div className="absolute right-3 top-3 z-[600] w-72 rounded-2xl border border-line bg-surface/95 backdrop-blur p-4 shadow-xl">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="display text-[17px] font-semibold text-ink leading-tight">{facility.name}</div>
          <div className="text-[11.5px] text-ink-3 mt-0.5">{facility.facility_type} · {facility.region_name}</div>
        </div>
        <button className="btn-ghost btn-sm -mr-2 -mt-1 h-7 w-7 p-0" onClick={onClose} aria-label="Close"><X size={14} /></button>
      </div>
      <dl className="mt-3 space-y-1.5 text-[12.5px]">
        <div className="flex justify-between items-center"><dt className="text-ink-3">Status</dt><dd><HealthBadge health={facility.health} /></dd></div>
        {rows.map(([k, v]) => <div key={k} className="flex justify-between"><dt className="text-ink-3">{k}</dt><dd className="font-medium text-ink tabular-nums">{v}</dd></div>)}
      </dl>
      <Link to={to} className="btn-dark w-full mt-4 justify-between">{action} <ArrowRight size={14} /></Link>
    </div>
  )
}
