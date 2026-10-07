import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import type { QualityWarning } from '../types'
import { Badge, Card, PageHeader, QUALITY_COLORS, StatCard, TH, THEAD } from '../components/ui'
import { Async, Empty, useApi } from '../components/states'

interface Row {
  patient_id: string
  overall_score: number
  sufficient: boolean
  sections: Record<string, number>
  level: string
  lab_timeliness: number
  hours_of_data: number
  max_stale_hours: number
  warnings: QualityWarning[]
}
interface Unit { patients: Row[]; levels: Record<string, number>; patients_with_warnings: number }

function Bar({ v }: { v: number }) {
  const color = v >= 80 ? 'bg-green-600' : v >= 60 ? 'bg-red-400' : 'bg-red-700'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 rounded-full bg-slate-200 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${v}%` }} />
      </div>
      <span className="text-xs tabular-nums text-slate-600">{v}%</span>
    </div>
  )
}

export default function DataQuality() {
  const state = useApi<Unit>('/data-quality')
  const [warnOnly, setWarnOnly] = useState(false)

  return (
    <div className="space-y-4">
      <PageHeader title="Data Quality" subtitle="Completeness and freshness of the data every prediction depends on.">
        <label className="flex items-center gap-1.5 text-xs text-slate-600">
          <input type="checkbox" checked={warnOnly} onChange={e => setWarnOnly(e.target.checked)} /> Patients with warnings only
        </label>
      </PageHeader>
      <p className="text-sm text-slate-600">
        Prediction confidence is reduced when data completeness is low, laboratory values are stale,
        or fewer than 6 hours of observations exist. Laboratory completeness reflects real sampling
        cadence (labs are measured every 4–8 h, not hourly).
      </p>
      <Async state={state} what="data quality">{d => {
        const rows = warnOnly ? d.patients.filter(r => r.warnings.length) : d.patients
        const avg = (k: string) => d.patients.length
          ? Math.round(d.patients.reduce((s, r) => s + (r.sections[k] ?? 0), 0) / d.patients.length) : 0
        const mean = d.patients.length
          ? Math.round(d.patients.reduce((s, r) => s + r.overall_score, 0) / d.patients.length) : 0
        return (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <StatCard label="Mean overall quality" value={`${mean}%`} />
              <StatCard label="Good" value={d.levels.GOOD ?? 0} accent="text-green-700" />
              <StatCard label="Fair" value={d.levels.FAIR ?? 0} accent="text-red-500" />
              <StatCard label="Poor" value={d.levels.POOR ?? 0} accent="text-red-700" />
              <StatCard label="Patients with warnings" value={d.patients_with_warnings} accent={d.patients_with_warnings ? 'text-red-600' : 'text-slate-900'} />
            </div>
            <Card title="Unit-wide completeness (averages)">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-5 text-sm">
                {[['vitals', 'Vitals'], ['laboratory', 'Laboratory'], ['fluid_records', 'Fluid records'],
                  ['antibiotic_data', 'Antibiotic data'], ['recent_vitals_6h', 'Recent vitals (6h)']].map(([k, label]) => (
                  <div key={k}>
                    <div className="mb-1 text-xs text-slate-500">{label}</div>
                    <Bar v={avg(k)} />
                  </div>
                ))}
              </div>
            </Card>
            {rows.length === 0 ? <Empty>No patients have data-quality warnings.</Empty> : (
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full text-sm">
                  <thead className={THEAD}>
                    <tr>{['Patient', 'Overall', 'Level', 'Vitals', 'Laboratory', 'Fluids', 'Oldest lab', 'Warnings', 'Sufficient data'].map(h =>
                      <th key={h} className={TH}>{h}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {rows.map(r => (
                      <tr key={r.patient_id} className="hover:bg-slate-50">
                        <td className="px-3 py-2"><Link to={`/patients/${r.patient_id}`} className="font-semibold text-green-700 hover:underline">{r.patient_id}</Link></td>
                        <td className="px-3 py-2"><Bar v={r.overall_score} /></td>
                        <td className="px-3 py-2"><Badge label={r.level} palette={QUALITY_COLORS} /></td>
                        <td className="px-3 py-2"><Bar v={r.sections.vitals} /></td>
                        <td className="px-3 py-2"><Bar v={r.sections.laboratory} /></td>
                        <td className="px-3 py-2"><Bar v={r.sections.fluid_records} /></td>
                        <td className={`px-3 py-2 text-xs tabular-nums ${r.max_stale_hours > 12 ? 'font-semibold text-red-600' : 'text-slate-600'}`}>{r.max_stale_hours}h ago</td>
                        <td className="px-3 py-2 text-xs">
                          {r.warnings.length
                            ? <span className="flex items-center gap-1 text-red-700" title={r.warnings.map(w => `${w.title}. ${w.message}`).join('\n')}>
                                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />{r.warnings[0].title}{r.warnings.length > 1 && ` +${r.warnings.length - 1}`}
                              </span>
                            : <span className="text-slate-400">none</span>}
                        </td>
                        <td className="px-3 py-2 text-xs">{r.sufficient
                          ? <span className="text-green-700">yes</span>
                          : <span className="text-red-600">insufficient (&lt;6h)</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )
      }}</Async>
    </div>
  )
}
