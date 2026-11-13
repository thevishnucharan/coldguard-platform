import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import { useThemeStore } from '../../store/themeStore'
import { tiles } from './FacilityMap'
import { TRIP_COLORS } from './routeColors'

export interface RouteStop { facility_code: string; facility_name: string; lat: number; lon: number; doses: number; arrival_offset_minutes: number }
export interface RouteTrip { trip: number; vehicle: number; stops: RouteStop[] }
export interface RouteSource { code: string; name: string; lat: number; lon: number; unit_code?: string }

function stopIcon(label: string, color: string, source = false) {
  return L.divIcon({
    className: 'cg-pin-wrap', iconSize: [0, 0],
    html: `<div style="transform:translate(-50%,-50%);display:grid;place-items:center;min-width:22px;height:22px;padding:0 5px;border-radius:${source ? '6px' : '999px'};
      background:${color};color:#fff;font:600 11px/1 system-ui;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35)">${label}</div>`,
  })
}

export function RouteMap({ source, trips, height = 360 }: { source: RouteSource; trips: RouteTrip[]; height?: number }) {
  const theme = useThemeStore((s) => s.theme)
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const overlay = useRef<L.LayerGroup | null>(null)
  const base = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true, scrollWheelZoom: false })
    L.control.scale({ imperial: false }).addTo(m)
    m.setView([source.lat, source.lon], 10)
    map.current = m
    overlay.current = L.layerGroup().addTo(m)
    const ro = new ResizeObserver(() => m.invalidateSize())
    ro.observe(el.current)
    return () => { ro.disconnect(); m.remove(); map.current = null; base.current = null }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

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
    const pts: [number, number][] = [[source.lat, source.lon]]
    trips.forEach((t, i) => {
      const color = TRIP_COLORS[i % TRIP_COLORS.length]
      const path: [number, number][] = [[source.lat, source.lon], ...t.stops.map((s) => [s.lat, s.lon] as [number, number])]
      L.polyline(path, { color, weight: 4, opacity: 0.85 }).addTo(lg)
      L.polyline([path[path.length - 1], path[0]], { color, weight: 2, opacity: 0.5, dashArray: '6 6' }).addTo(lg) // return leg
      t.stops.forEach((s, k) => {
        pts.push([s.lat, s.lon])
        L.marker([s.lat, s.lon], { icon: stopIcon(`${t.trip}.${k + 1}`, color), title: `Trip ${t.trip} stop ${k + 1}: ${s.facility_name}` })
          .bindTooltip(`<b>${s.facility_name}</b><br/>Trip ${t.trip} · stop ${k + 1}<br/>${s.doses.toLocaleString()} doses · ETA +${Math.round(s.arrival_offset_minutes)} min`, { direction: 'top', offset: [0, -12] })
          .addTo(lg)
      })
    })
    L.marker([source.lat, source.lon], { icon: stopIcon('SRC', '#c2253b', true), title: `Source: ${source.name}` })
      .bindTooltip(`<b>${source.name}</b><br/>Excursion source${source.unit_code ? ` · ${source.unit_code}` : ''}`, { direction: 'top', offset: [0, -12] })
      .addTo(lg)
    if (pts.length > 1) m.fitBounds(L.latLngBounds(pts).pad(0.25), { maxZoom: 12 })
    else m.setView(pts[0], 11)
  }, [source, trips])

  return (
    <div className="relative">
      <div ref={el} style={{ height }} className="w-full rounded-xl overflow-hidden border border-line bg-surface-2 z-0" role="region" aria-label="Relocation route map" />
      <div className="absolute left-2 bottom-7 z-[500] flex flex-wrap gap-x-3 gap-y-1 rounded-lg bg-surface/95 px-2.5 py-1.5 text-[11px] text-ink-2 border border-line shadow-sm">
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm" style={{ background: '#c2253b' }} />Source</span>
        {trips.map((t, i) => <span key={t.trip} className="flex items-center gap-1"><span className="h-1 w-4 rounded" style={{ background: TRIP_COLORS[i % TRIP_COLORS.length] }} />Trip {t.trip} · vehicle {t.vehicle}</span>)}
      </div>
    </div>
  )
}
