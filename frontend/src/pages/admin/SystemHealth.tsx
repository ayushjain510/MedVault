import { RefreshCw } from 'lucide-react'
import { BTN_SECONDARY, Card, PageHeader, StatCard, TH, THEAD } from '../../components/ui'
import { Async, useApi } from '../../components/states'
import { StatusPill, uptime } from '../dashboards/AdminDashboard'

export interface ModelRow {
  task: string; loaded: boolean; file_present: boolean; algorithm: string | null
  model_version: string | null; feature_version: string | null; n_features: number | null; trained_at: string | null
}
export interface Health {
  status: string
  api: { status: string; uptime_seconds: number }
  database: { status: string; latency_ms?: number; dialect: string; error?: string }
  model_service: { status: string; loaded: number; expected: number; error: string | null }
  models: ModelRow[]
  counts: Record<string, number>
  security: { jwt_secret_is_default: boolean }
  data: string
  checked_at: string
}

export function ModelTable({ models }: { models: ModelRow[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-sm">
        <thead className={THEAD}><tr>{['Prediction task', 'Status', 'Algorithm', 'Model version', 'Features', 'Trained'].map(h => <th key={h} className={TH}>{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-200">
          {models.map(m => (
            <tr key={m.task} className="hover:bg-slate-50">
              <td className="px-3 py-2 font-medium capitalize">{m.task.replace(/_/g, ' ')}</td>
              <td className="px-3 py-2"><StatusPill status={m.loaded ? 'ok' : 'down'} />{!m.file_present && <span className="ml-2 text-xs text-red-600">model file missing</span>}</td>
              <td className="px-3 py-2">{m.algorithm?.replace(/_/g, ' ') ?? '—'}</td>
              <td className="px-3 py-2"><code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{m.model_version ?? '—'}</code></td>
              <td className="px-3 py-2 tabular-nums">{m.n_features ?? '—'} <span className="text-xs text-slate-500">v{m.feature_version}</span></td>
              <td className="px-3 py-2 text-xs text-slate-600">{m.trained_at ? new Date(m.trained_at).toLocaleString() : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function SystemHealth() {
  const state = useApi<Health>('/admin/system-health')
  return (
    <div className="space-y-4">
      <PageHeader title="System Health" subtitle="Live checks of the API, the database and the model service.">
        <button onClick={state.reload} className={BTN_SECONDARY}><RefreshCw className={`h-3.5 w-3.5 ${state.loading ? 'animate-spin' : ''}`} /> Run checks</button>
      </PageHeader>
      <Async state={state} what="system health">{h => (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Card title={<span className="flex items-center justify-between">API <StatusPill status={h.api.status} /></span>}>
              <div className="text-sm text-slate-700">Up for {uptime(h.api.uptime_seconds)}</div>
              <div className="text-xs text-slate-500">Serving {h.data} data</div>
            </Card>
            <Card title={<span className="flex items-center justify-between">Database <StatusPill status={h.database.status} /></span>}>
              <div className="text-sm text-slate-700">{h.database.dialect}</div>
              <div className="text-xs text-slate-500">{h.database.error ?? `Query round-trip ${h.database.latency_ms} ms`}</div>
            </Card>
            <Card title={<span className="flex items-center justify-between">Model service <StatusPill status={h.model_service.status} /></span>}>
              <div className="text-sm text-slate-700">{h.model_service.loaded} of {h.model_service.expected} models loaded</div>
              <div className="text-xs text-slate-500">{h.model_service.error ?? 'All prediction tasks are being served'}</div>
            </Card>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {Object.entries(h.counts).map(([k, v]) => <StatCard key={k} label={k.replace(/_/g, ' ')} value={v.toLocaleString()} />)}
          </div>
          <ModelTable models={h.models} />
          <div className="text-[11px] text-slate-500">Checked {new Date(h.checked_at).toLocaleString()}.</div>
        </>
      )}</Async>
    </div>
  )
}
