import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { PatientSummary } from '../types'
import { Badge, INPUT, PageHeader, RiskBar, RiskScore, StatCard, SEV_COLORS, TH, THEAD } from '../components/ui'
import { Async, Empty, ErrorState, useApi } from '../components/states'

interface Overview {
  total_patients: number; high_concern: number; poor_response: number
  poor_recovery: number; fluid_concern: number; improving: number
  monitoring: number; needs_review: number; avg_det6_risk: number
}

type SortKey = 'patient_id' | 'state' | 'det6_risk' | 'alert_level' | 'recovery' | 'risk'
const ALERT_ORDER: Record<string, number> = { critical: 0, high: 1, moderate: 2, info: 3, none: 4 }
// Most-concerning recovery trajectory first (RT-4 worsening → RT-0 improving).
const RECOVERY_ORDER = ['RT-4', 'RT-3', 'RT-2', 'RT-1', 'RT-0', 'RT-5']
const recRank = (label?: string | null) => {
  const i = RECOVERY_ORDER.findIndex(k => (label ?? '').startsWith(k))
  return i === -1 ? 99 : i
}
const RISK_LEVELS = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW']

/** Patient list (the former "Unit Overview"), now with the composite risk score. */
export default function Patients() {
  const [params, setParams] = useSearchParams()
  const overview = useApi<Overview>('/overview')
  const list = useApi<{ patients: PatientSummary[] }>('/patients')
  const [sort, setSort] = useState<SortKey>(params.get('sort') === 'risk' ? 'risk' : 'recovery')
  const [filter, setFilter] = useState('')
  const [alertFilter, setAlertFilter] = useState('')
  const riskFilter = params.get('risk') ?? ''
  const ov = overview.data

  const rows = useMemo(() => {
    let r = list.data?.patients ?? []
    if (filter) r = r.filter(p => p.patient_id.toLowerCase().includes(filter.toLowerCase()))
    if (alertFilter) r = r.filter(p => p.alert_level === alertFilter)
    if (riskFilter) r = r.filter(p => p.risk_level === riskFilter)
    return [...r].sort((a, b) => {
      if (sort === 'risk') return (b.risk_score ?? -1) - (a.risk_score ?? -1)
      if (sort === 'recovery') return recRank(a.recovery) - recRank(b.recovery)
      if (sort === 'det6_risk') return (b.det6_risk ?? 0) - (a.det6_risk ?? 0)
      if (sort === 'alert_level') return ALERT_ORDER[a.alert_level] - ALERT_ORDER[b.alert_level]
      if (sort === 'state') return (a.state ?? '').localeCompare(b.state ?? '')
      return a.patient_id.localeCompare(b.patient_id)
    })
  }, [list.data, sort, filter, alertFilter, riskFilter])

  return (
    <div className="space-y-4">
      <PageHeader title="Patients" subtitle="Every monitored patient with the latest model outputs." />
      {overview.error && <ErrorState what="the unit summary" error={overview.error} onRetry={overview.reload} />}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <StatCard label="Patients monitored" value={ov?.total_patients ?? '—'} />
        <StatCard label="Improving / recovering" value={ov?.improving ?? '—'} accent="text-green-700" />
        <StatCard label="Poor recovery" value={ov?.poor_recovery ?? '—'} accent="text-red-600" />
        <StatCard label="Poor response" value={ov?.poor_response ?? '—'} accent="text-red-600" />
        <StatCard label="Fluid concern" value={ov?.fluid_concern ?? '—'} accent="text-red-600" />
        <StatCard label="Monitoring" value={ov?.monitoring ?? '—'} accent="text-red-600" />
        <StatCard label="Needs review" value={ov?.needs_review ?? '—'} accent="text-red-600" />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Search patient ID…"
          aria-label="Search patient ID" className={INPUT} />
        <select value={riskFilter} aria-label="Filter by risk level" className={INPUT}
          onChange={e => setParams(e.target.value ? { risk: e.target.value } : {})}>
          <option value="">All risk levels</option>
          {RISK_LEVELS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={alertFilter} onChange={e => setAlertFilter(e.target.value)} aria-label="Filter by alert level" className={INPUT}>
          <option value="">All alert levels</option>
          {['critical', 'high', 'moderate', 'info', 'none'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={sort} onChange={e => setSort(e.target.value as SortKey)} aria-label="Sort patients" className={INPUT}>
          <option value="recovery">Sort: recovery trajectory</option>
          <option value="risk">Sort: risk score</option>
          <option value="alert_level">Sort: alert level</option>
          <option value="state">Sort: state</option>
          <option value="det6_risk">Sort: 6h risk (supporting)</option>
          <option value="patient_id">Sort: patient ID</option>
        </select>
        <span className="text-xs text-slate-500">{rows.length} patients</span>
      </div>

      <Async state={list} what="the patient list">{() => rows.length === 0 ? <Empty>No patients match the current filters.</Empty> : (
        <div className="overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-sm">
            <thead className={THEAD}>
              <tr>
                {['Patient', 'Age/Sex', 'Risk score', 'Recovery trajectory', 'Overall state', 'Antibiotic response', 'Fluid status', 'Alert', '6h risk'].map(h =>
                  <th key={h} className={TH}>{h}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {rows.map(p => (
                <tr key={p.patient_id} className="hover:bg-slate-50">
                  <td className="px-3 py-2">
                    <Link to={`/patients/${p.patient_id}`} className="font-semibold text-green-700 hover:underline">{p.patient_id}</Link>
                    <div className="text-[10px] text-slate-500">hour {p.last_hour}</div>
                  </td>
                  <td className="px-3 py-2 text-slate-600">{p.age} / {p.sex}</td>
                  <td className="px-3 py-2"><RiskScore score={p.risk_score} level={p.risk_level} /></td>
                  <td className="px-3 py-2"><Badge label={p.recovery ?? '—'} /></td>
                  <td className="px-3 py-2"><Badge label={p.engine_state ?? '—'} /></td>
                  <td className="px-3 py-2 text-slate-700">{p.abx_response ?? '—'}</td>
                  <td className="px-3 py-2 text-slate-700">{p.fluid_status ?? '—'}</td>
                  <td className="px-3 py-2"><Badge label={p.alert_level} palette={SEV_COLORS} /></td>
                  <td className="px-3 py-2 opacity-60"><RiskBar value={p.det6_risk} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}</Async>
    </div>
  )
}
