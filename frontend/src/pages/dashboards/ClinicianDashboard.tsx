import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import type { RiskRow } from '../../types'
import { Badge, Card, Delta, PageHeader, ResearchNote, RISK_FILL, RiskScore, SEV_COLORS, StatCard } from '../../components/ui'
import { Async, Empty, useApi } from '../../components/states'

interface ClinicianData {
  total_patients: number
  risk_levels: Record<string, number>
  high_risk_patients: number
  critical_patients: number
  active_alerts: { critical: number; high: number; moderate: number; info: number; total: number; unacknowledged: number }
  improving: number
  top_risk: RiskRow[]
  recent_changes: RiskRow[]
  urgent_alerts: { id: number; patient_id: string; hour: number; severity: string; category: string; title: string }[]
}
const LEVELS = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']

function PatientRow({ p, showDelta = false }: { p: RiskRow; showDelta?: boolean }) {
  return (
    <Link to={`/patients/${p.patient_id}`} className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-50">
      <span className="w-14 font-semibold text-green-700">{p.patient_id}</span>
      <RiskScore score={p.risk_score} level={p.risk_level} />
      {showDelta
        ? <span className="text-xs text-slate-500">{p.previous_score_6h} → {p.risk_score} <Delta value={p.delta_6h} /></span>
        : <span className="hidden truncate text-xs text-slate-500 md:inline">{p.top_contributor?.label}: {p.top_contributor?.value}</span>}
      <ArrowRight className="ml-auto h-3.5 w-3.5 shrink-0 text-slate-400" />
    </Link>
  )
}

export default function ClinicianDashboard() {
  const state = useApi<ClinicianData>('/dashboard/clinician')
  return (
    <div className="space-y-4">
      <PageHeader title="Clinician Dashboard" subtitle="Patient monitoring — who needs review now, and what changed." />
      <Async state={state} what="the clinician dashboard">{d => {
        const scored = LEVELS.reduce((s, l) => s + (d.risk_levels[l] ?? 0), 0) || 1
        return (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <StatCard label="Total patients" value={d.total_patients} hint={`${d.improving} with an improving recovery trajectory`} />
              <StatCard label="High risk patients" value={<Link to="/patients?risk=HIGH&sort=risk">{d.high_risk_patients}</Link>} accent="text-red-600" hint="risk score 50–74" />
              <StatCard label="Critical patients" value={<Link to="/patients?risk=CRITICAL&sort=risk">{d.critical_patients}</Link>} accent="text-red-700" hint="risk score 75–100" />
              <StatCard label="Active alerts" value={<Link to="/alerts">{d.active_alerts.total}</Link>} accent="text-red-600"
                hint={`${d.active_alerts.critical} critical · ${d.active_alerts.high} high`} />
              <StatCard label="Awaiting review" value={d.active_alerts.unacknowledged} hint="unacknowledged critical / high alerts" />
            </div>

            <Card title="Risk distribution across the unit">
              <div className="flex h-3 overflow-hidden rounded-full">
                {LEVELS.map(l => <div key={l} className={RISK_FILL[l]} style={{ width: `${((d.risk_levels[l] ?? 0) / scored) * 100}%` }} title={`${l}: ${d.risk_levels[l] ?? 0}`} />)}
              </div>
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600">
                {LEVELS.map(l => (
                  <Link key={l} to={`/patients?risk=${l}&sort=risk`} className="flex items-center gap-1.5 hover:underline">
                    <span className={`h-2 w-2 rounded-full ${RISK_FILL[l]}`} />{l} <strong className="tabular-nums">{d.risk_levels[l] ?? 0}</strong>
                  </Link>
                ))}
                {(d.risk_levels['INSUFFICIENT DATA'] ?? 0) > 0 && <span>No score yet: {d.risk_levels['INSUFFICIENT DATA']}</span>}
              </div>
            </Card>

            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              <Card title={<span className="flex items-center justify-between">Highest risk patients <Link to="/risk" className="text-xs font-normal text-green-700 hover:underline">Risk monitoring →</Link></span>}>
                {d.top_risk.length ? d.top_risk.map(p => <PatientRow key={p.patient_id} p={p} />) : <Empty>No patients.</Empty>}
              </Card>
              <Card title="Recent patient changes (risk score, last 6 hours)">
                {d.recent_changes.length ? d.recent_changes.map(p => <PatientRow key={p.patient_id} p={p} showDelta />)
                  : <Empty>No patient's risk score moved by 5 points or more in the last 6 hours.</Empty>}
              </Card>
            </div>

            <Card title={<span className="flex items-center justify-between">Alerts awaiting review <Link to="/alerts" className="text-xs font-normal text-green-700 hover:underline">All alerts →</Link></span>}>
              {d.urgent_alerts.length ? (
                <ul className="divide-y divide-slate-100">
                  {d.urgent_alerts.map(a => (
                    <li key={a.id} className="flex flex-wrap items-center gap-2 py-1.5 text-sm">
                      <Badge label={a.severity} palette={SEV_COLORS} />
                      <span className="text-[10px] uppercase tracking-wide text-slate-500">{a.category}</span>
                      <span className="text-slate-800">{a.title}</span>
                      <Link to={`/patients/${a.patient_id}`} className="ml-auto text-xs text-green-700 hover:underline">{a.patient_id} · h{a.hour}</Link>
                    </li>
                  ))}
                </ul>
              ) : <Empty>No unacknowledged critical or high alerts at the current hour.</Empty>}
            </Card>
            <ResearchNote>
              Risk levels come from the MedVault Composite Risk Score — a research / prototype indicator, not a validated
              clinical score. Alerts are review prompts, never treatment orders.
            </ResearchNote>
          </>
        )
      }}</Async>
    </div>
  )
}
