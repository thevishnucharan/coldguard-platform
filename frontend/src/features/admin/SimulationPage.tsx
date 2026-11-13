import { FlaskConical, Pause, Play, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { Card, CardHeader } from '../../components/common/Card'
import { DataTable } from '../../components/common/DataTable'
import { ErrorState, PageSkeleton } from '../../components/common/Feedback'
import { ConfirmDialog } from '../../components/common/Modal'
import { PageHeader } from '../../components/common/PageHeader'
import { Pill, StatusPill } from '../../components/common/Status'
import { useApi, useNow } from '../../hooks/useApi'
import { errorMessage } from '../../services/api/client'
import { System } from '../../services/api/endpoints'
import { ago, fmtTemp, humanize } from '../../utils/format'

const HELP: Record<string, string> = {
  normal: 'Stable mid-range with compressor cycling', drift: 'Gradual warming (~0.12 °C/min) past the upper limit',
  excursion: 'Sudden spike above the limit for ~12 min, then recovery', fluctuation: 'Repeated swings across the upper limit',
  missing: 'Intermittent gaps (~65% of readings dropped)', disconnect: 'No readings at all — sensor goes offline',
}

export default function SimulationPage() {
  const q = useApi(() => System.simulation(), [], { refreshOn: ['reading', 'sensor.status'], interval: 15000 })
  const [reset, setReset] = useState(false)
  const [interval, setIntervalS] = useState(15)
  const now = useNow(5000)
  if (q.loading && !q.data) return <PageSkeleton />
  if (q.error || !q.data) return <ErrorState message={q.error || 'Simulation unavailable (DEMO_MODE disabled?)'} onRetry={q.reload} />
  const s = q.data
  const act = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); toast.success(ok); q.reload() } catch (e) { toast.error(errorMessage(e)) } }
  return (
    <>
      <PageHeader title="Demo simulation" subtitle="Drive simulated sensors through the real ingestion pipeline. All generated data is labelled as simulated."
        crumbs={[{ label: 'Configuration' }, { label: 'Simulation' }]}
        meta={<Pill tone={s.running ? 'ok' : 'neutral'} icon={FlaskConical}>{s.running ? `Running · every ${s.interval_seconds}s` : 'Stopped'}</Pill>}
        actions={<>
          {s.running ? <button className="btn-secondary" onClick={() => act(System.stopSim, 'Simulation stopped')}><Pause size={15} /> Stop</button>
            : <><input type="number" min={3} max={300} className="input w-20" value={interval} onChange={(e) => setIntervalS(Number(e.target.value))} aria-label="Interval seconds" />
              <button className="btn-primary" onClick={() => act(() => System.startSim(interval), 'Simulation started')}><Play size={15} /> Start</button></>}
          <button className="btn-danger" onClick={() => setReset(true)}><RotateCcw size={15} /> Reset demo data</button>
        </>} />
      <Card className="mb-4">
        <CardHeader title="Scenarios" />
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {s.available_scenarios.map((k: string) => <div key={k} className="rounded-lg border border-line px-3 py-2"><p className="text-[13px] font-medium">{humanize(k)}</p><p className="text-xs text-ink-3">{HELP[k]}</p></div>)}
        </div>
        <p className="text-[11px] text-ink-3 mt-3">A standalone MQTT simulator container (<span className="mono">simulator/</span>) can publish the same scenarios over MQTT for end-to-end testing.</p>
      </Card>
      <div className="card p-0">
        <DataTable rows={s.sensors} columns={[
          { key: 'c', header: 'Simulated sensor', render: (x) => <span className="mono font-medium">{x.sensor_code}</span> },
          { key: 'u', header: 'Unit', render: (x) => x.unit_code },
          { key: 's', header: 'Status', render: (x) => <StatusPill status={x.status} /> },
          { key: 't', header: 'Last value', align: 'right', render: (x) => fmtTemp(x.last_temperature) },
          { key: 'l', header: 'Last reading', render: (x) => <span className="text-xs">{ago(x.last_reading_at, now)}</span> },
          { key: 'sc', header: 'Scenario', render: (x) => (
            <select className="input h-8 text-xs w-40" value={x.scenario} onChange={(e) => act(() => System.setScenario(x.id, e.target.value), `${x.sensor_code}: ${e.target.value}`)}>
              {s.available_scenarios.map((k: string) => <option key={k} value={k}>{humanize(k)}</option>)}</select>) },
        ]} />
      </div>
      <ConfirmDialog open={reset} onClose={() => setReset(false)} danger title="Reset all demo data" typeToConfirm="RESET DEMO DATA"
        description="Deletes ALL records (users, incidents, stock, audit trail) and re-creates the demonstration dataset. Only available in demo mode. Takes ~30 s."
        confirmLabel="Reset" onConfirm={async () => { try { await System.resetDemo(); toast.success('Demo data reset — please sign in again'); window.location.assign('/login') } catch (e) { toast.error(errorMessage(e)) } }} />
    </>
  )
}
