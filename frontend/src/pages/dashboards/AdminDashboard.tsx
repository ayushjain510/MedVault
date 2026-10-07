import { Link } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'
import { Card, PageHeader, StatCard } from '../../components/ui'
import { Async, Empty, useApi } from '../../components/states'
import { AuditTable } from '../admin/AuditLogs'
import type { AuditEvent } from '../admin/AuditLogs'

interface Status { status: string; [k: string]: unknown }
interface AdminData {
  users: { total: number; active: number; inactive: number; by_role: Record<string, number> }
  system: { status: string; api: Status & { uptime_seconds: number }; database: Status & { latency_ms?: number; dialect: string }; model_service: Status & { loaded: number; expected: number } }
  security: { jwt_secret_is_default: boolean }
  counts: Record<string, number>
  activity_24h: { events: number; logins: number; failed_logins: number; denied: number }
  recent_activity: AuditEvent[]
}

export function StatusPill({ status }: { status: string }) {
  const ok = status === 'ok'
  const Icon = ok ? CheckCircle2 : status === 'degraded' ? AlertTriangle : XCircle
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${ok
      ? 'border-green-300 bg-green-50 text-green-700' : 'border-red-300 bg-red-50 text-red-700'}`}>
      <Icon className="h-3.5 w-3.5" /> {ok ? 'Operational' : status === 'degraded' ? 'Degraded' : 'Down'}
    </span>
  )
}

export const uptime = (s: number) => s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)} min` : `${(s / 3600).toFixed(1)} h`

export default function AdminDashboard() {
  const state = useApi<AdminData>('/admin/dashboard')
  return (
    <div className="space-y-4">
      <PageHeader title="Admin Dashboard" subtitle="System management — accounts, platform status and recent activity." />
      <Async state={state} what="the admin dashboard">{d => (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Total users" value={<Link to="/admin/users">{d.users.total}</Link>} hint={`${d.users.active} active · ${d.users.inactive} deactivated`} />
            <StatCard label="Clinicians" value={d.users.by_role.clinician ?? 0} />
            <StatCard label="Researchers" value={d.users.by_role.researcher ?? 0} />
            <StatCard label="Administrators" value={d.users.by_role.admin ?? 0} />
          </div>

          <Card title={<span className="flex items-center justify-between">System status <StatusPill status={d.system.status} /></span>}>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between text-sm font-medium">API <StatusPill status={d.system.api.status} /></div>
                <div className="mt-1 text-xs text-slate-500">Up for {uptime(d.system.api.uptime_seconds)}</div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between text-sm font-medium">Database <StatusPill status={d.system.database.status} /></div>
                <div className="mt-1 text-xs text-slate-500">{d.system.database.dialect} · responded in {d.system.database.latency_ms ?? '—'} ms</div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between text-sm font-medium">Model service <StatusPill status={d.system.model_service.status} /></div>
                <div className="mt-1 text-xs text-slate-500">{d.system.model_service.loaded} of {d.system.model_service.expected} models loaded</div>
              </div>
            </div>
            {d.security.jwt_secret_is_default && (
              <div className="mt-3 flex gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                JWT_SECRET is at its development default. Tokens could be forged — set a strong secret before exposing this service beyond localhost.
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-600">
              {Object.entries(d.counts).map(([k, v]) => <span key={k}>{k.replace(/_/g, ' ')} <strong className="tabular-nums text-slate-800">{v.toLocaleString()}</strong></span>)}
            </div>
            <Link to="/admin/health" className="mt-2 inline-block text-xs text-green-700 hover:underline">System health details →</Link>
          </Card>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Events (24h)" value={d.activity_24h.events} />
            <StatCard label="Sign-ins (24h)" value={d.activity_24h.logins} />
            <StatCard label="Failed sign-ins (24h)" value={d.activity_24h.failed_logins} accent={d.activity_24h.failed_logins ? 'text-red-600' : 'text-slate-900'} />
            <StatCard label="Access denied (24h)" value={d.activity_24h.denied} accent={d.activity_24h.denied ? 'text-red-600' : 'text-slate-900'} hint="403 responses" />
          </div>

          <Card title={<span className="flex items-center justify-between">Recent activity
            <Link to="/admin/audit" className="text-xs font-normal text-green-700 hover:underline">Audit log →</Link></span>}>
            {d.recent_activity.length ? <AuditTable events={d.recent_activity} /> : <Empty>No activity recorded yet.</Empty>}
          </Card>
        </>
      )}</Async>
    </div>
  )
}
