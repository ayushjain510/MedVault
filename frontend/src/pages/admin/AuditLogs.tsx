import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { Badge, BTN_SECONDARY, GREEN, INPUT, NEUTRAL, PageHeader, RED_MID, RED_SOFT, TH, THEAD } from '../../components/ui'
import { Async, Empty, useApi } from '../../components/states'

export interface AuditEvent {
  id: number; timestamp: string; username: string; role: string | null
  action: string; target: string | null; detail: string | null; status: string
}
const STATUS: Record<string, string> = { success: GREEN, denied: RED_MID, failed: RED_SOFT }

export function AuditTable({ events }: { events: AuditEvent[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className={THEAD}>
          <tr>{['Time', 'User', 'Role', 'Action', 'Target', 'Detail', 'Result'].map(h => <th key={h} className={TH}>{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {events.map(e => (
            <tr key={e.id} className="hover:bg-slate-50">
              <td className="px-3 py-2 whitespace-nowrap text-xs tabular-nums text-slate-600">{new Date(e.timestamp).toLocaleString()}</td>
              <td className="px-3 py-2 font-medium">{e.username}</td>
              <td className="px-3 py-2 text-xs text-slate-600">{e.role ?? '—'}</td>
              <td className="px-3 py-2"><code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{e.action}</code></td>
              <td className="px-3 py-2 text-xs text-slate-700">{e.target ?? '—'}</td>
              <td className="max-w-xs truncate px-3 py-2 text-xs text-slate-600" title={e.detail ?? ''}>{e.detail ?? '—'}</td>
              <td className="px-3 py-2"><Badge label={e.status} palette={{ ...STATUS, other: NEUTRAL }} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function AuditLogs() {
  const [action, setAction] = useState('')
  const [status, setStatus] = useState('')
  const [username, setUsername] = useState('')
  const query = new URLSearchParams({ limit: '200' })
  if (action) query.set('action', action)
  if (status) query.set('status', status)
  if (username.trim()) query.set('username', username.trim())
  const state = useApi<{ total: number; events: AuditEvent[]; actions: string[] }>(`/admin/audit?${query}`)

  return (
    <div className="space-y-4">
      <PageHeader title="Audit Logs" subtitle="Who did what, and when. Passwords, tokens and request bodies are never recorded.">
        <input value={username} onChange={e => setUsername(e.target.value)} placeholder="Username" aria-label="Filter by username" className={`${INPUT} w-32`} />
        <select value={action} onChange={e => setAction(e.target.value)} aria-label="Filter by action" className={INPUT}>
          <option value="">All actions</option>
          {(state.data?.actions ?? []).map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={status} onChange={e => setStatus(e.target.value)} aria-label="Filter by result" className={INPUT}>
          <option value="">All results</option>
          {['success', 'denied', 'failed'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button onClick={state.reload} className={BTN_SECONDARY}><RefreshCw className="h-3.5 w-3.5" /> Refresh</button>
      </PageHeader>
      <Async state={state} what="the audit log">{d => d.events.length === 0 ? <Empty>No audit events match these filters.</Empty> : (
        <>
          <div className="text-xs text-slate-500">Showing {d.events.length} of {d.total} events, newest first.</div>
          <div className="rounded-xl border border-slate-200"><AuditTable events={d.events} /></div>
        </>
      )}</Async>
    </div>
  )
}
