import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check } from 'lucide-react'
import { api, ApiError, can } from '../api'
import type { AlertItem } from '../types'
import { Badge, BTN_SECONDARY, INPUT, PageHeader, SEV_COLORS } from '../components/ui'
import { Async, Empty, useApi } from '../components/states'

const SEV_DESC: Record<string, string> = {
  critical: 'Immediate clinical review suggested',
  high: 'Prompt review suggested',
  moderate: 'Continue monitoring',
  info: 'Trend update',
}

export default function Alerts() {
  const [sev, setSev] = useState('')
  const [openOnly, setOpenOnly] = useState(false)
  const [error, setError] = useState('')
  const state = useApi<{ alerts: AlertItem[] }>(`/alerts${sev ? `?severity=${sev}` : ''}`)
  const mayAcknowledge = can('alerts.acknowledge')

  async function acknowledge(id: number) {
    setError('')
    try {
      await api(`/alerts/${id}/acknowledge`, { method: 'POST' })
      state.reload()
    } catch (e) {
      setError(e instanceof ApiError && e.status === 403
        ? 'Your role cannot acknowledge alerts.' : 'The alert could not be acknowledged. Try again.')
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Alerts" subtitle="Review prompts raised by the alert engine. They never order a treatment.">
        <select value={sev} onChange={e => setSev(e.target.value)} className={INPUT} aria-label="Filter by severity">
          <option value="">All severities</option>
          {['critical', 'high', 'moderate', 'info'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-slate-600">
          <input type="checkbox" checked={openOnly} onChange={e => setOpenOnly(e.target.checked)} /> Unacknowledged only
        </label>
      </PageHeader>
      {error && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{error}</div>}
      <Async state={state} what="alerts">{d => {
        const alerts = openOnly ? d.alerts.filter(a => !a.acknowledged) : d.alerts
        if (alerts.length === 0) return <Empty>No alerts match the current filters.</Empty>
        return (
          <>
            <div className="text-xs text-slate-500">{alerts.length} alerts, newest first</div>
            <div className="space-y-2">
              {alerts.map(a => (
                <div key={a.id} className={`rounded-xl border border-slate-200 p-3 ${a.acknowledged ? 'bg-white opacity-70' : 'bg-slate-50'}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge label={a.severity} palette={SEV_COLORS} />
                    <span className="text-xs uppercase tracking-wide text-slate-500">{a.category}</span>
                    <span className="font-semibold text-slate-800">{a.title}</span>
                    <span className="ml-auto text-xs text-slate-500">
                      <Link to={`/patients/${a.patient_id}`} className="text-green-700 hover:underline">{a.patient_id}</Link> · h{a.hour}
                      {a.confidence != null && <> · confidence {(a.confidence * 100).toFixed(0)}%</>}
                    </span>
                  </div>
                  <div className="mt-1 text-sm text-slate-600">{a.message}</div>
                  <div className="mt-1 flex items-center gap-3">
                    <span className="text-[10px] text-slate-500">{SEV_DESC[a.severity]}{a.variable ? ` · variable: ${a.variable}` : ''}</span>
                    {a.acknowledged
                      ? <span className="ml-auto flex items-center gap-1 text-xs text-green-700"><Check className="h-3.5 w-3.5" /> Acknowledged</span>
                      : mayAcknowledge && (
                        <button onClick={() => acknowledge(a.id)} className={`${BTN_SECONDARY} ml-auto px-2 py-1 text-xs`}>
                          <Check className="h-3 w-3" /> Acknowledge
                        </button>
                      )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )
      }}</Async>
    </div>
  )
}
