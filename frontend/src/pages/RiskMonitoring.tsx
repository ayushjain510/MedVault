import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { RiskRow } from '../types'
import { Badge, Delta, INPUT, PageHeader, ResearchNote, RISK_COLORS, RISK_FILL, RiskScore, SEV_COLORS, TH, THEAD } from '../components/ui'
import { Async, Empty, useApi } from '../components/states'

interface UnitRisk {
  patients: RiskRow[]
  risk_levels: Record<string, number>
  label: string
  note: string
}
const LEVELS = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW', 'INSUFFICIENT DATA']

export default function RiskMonitoring() {
  const state = useApi<UnitRisk>('/risk')
  const [level, setLevel] = useState('')
  const [sort, setSort] = useState<'score' | 'delta'>('score')

  const rows = useMemo(() => {
    let r = state.data?.patients ?? []
    if (level) r = r.filter(p => (p.risk_level ?? 'INSUFFICIENT DATA') === level)
    if (sort === 'delta') r = [...r].sort((a, b) => (b.delta_6h ?? -999) - (a.delta_6h ?? -999))
    return r
  }, [state.data, level, sort])

  return (
    <div className="space-y-4">
      <PageHeader title="Risk Monitoring"
        subtitle="Unit ranking by MedVault Composite Risk Score, with the 6-hour change and the largest contributor for each patient.">
        <select value={sort} onChange={e => setSort(e.target.value as 'score' | 'delta')} className={INPUT} aria-label="Sort">
          <option value="score">Sort: highest score</option>
          <option value="delta">Sort: largest 6h increase</option>
        </select>
      </PageHeader>

      <Async state={state} what="the risk ranking">{data => {
        const total = data.patients.length || 1
        return (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              {LEVELS.map(lv => (
                <button key={lv} onClick={() => setLevel(l => (l === lv ? '' : lv))} aria-pressed={level === lv}
                  className={`rounded-xl border bg-white px-4 py-3 text-left shadow-sm transition hover:border-slate-400 ${level === lv ? 'border-slate-900 ring-1 ring-slate-900' : 'border-slate-200'}`}>
                  <Badge label={lv === 'INSUFFICIENT DATA' ? 'NO SCORE' : lv} palette={{ ...RISK_COLORS, 'NO SCORE': RISK_COLORS['INSUFFICIENT DATA'] }} />
                  <div className="mt-1 text-2xl font-bold tabular-nums">{data.risk_levels[lv] ?? 0}</div>
                  <div className="mt-1 h-1 overflow-hidden rounded bg-slate-200">
                    <div className={`h-full ${RISK_FILL[lv]}`} style={{ width: `${((data.risk_levels[lv] ?? 0) / total) * 100}%` }} />
                  </div>
                </button>
              ))}
            </div>
            <div className="text-xs text-slate-500">
              {rows.length} patient{rows.length === 1 ? '' : 's'}{level ? ` at ${level}` : ''}
              {level && <button onClick={() => setLevel('')} className="ml-2 text-green-700 hover:underline">clear filter</button>}
            </div>
            {rows.length === 0 ? <Empty>No patients in this risk band.</Empty> : (
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full text-sm">
                  <thead className={THEAD}>
                    <tr>{['Patient', 'Risk score', '6h change', 'Largest contributor', 'Patient state', 'Recovery', 'Alert'].map(h =>
                      <th key={h} className={TH}>{h}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {rows.map(p => (
                      <tr key={p.patient_id} className="hover:bg-slate-50">
                        <td className="px-3 py-2">
                          <Link to={`/patients/${p.patient_id}`} className="font-semibold text-green-700 hover:underline">{p.patient_id}</Link>
                          <div className="text-[10px] text-slate-500">{p.age}/{p.sex} · hour {p.last_hour}</div>
                        </td>
                        <td className="px-3 py-2"><RiskScore score={p.risk_score} level={p.risk_level} /></td>
                        <td className="px-3 py-2"><Delta value={p.delta_6h} /></td>
                        <td className="px-3 py-2 text-xs text-slate-700">
                          {p.top_contributor ? (
                            <>
                              <span className="font-medium">{p.top_contributor.label}</span>
                              <span className="text-slate-500"> · {p.top_contributor.value} · +{p.top_contributor.points}/{p.top_contributor.max_points}</span>
                            </>
                          ) : '—'}
                        </td>
                        <td className="px-3 py-2"><Badge label={p.engine_state} /></td>
                        <td className="px-3 py-2"><Badge label={p.recovery ?? '—'} /></td>
                        <td className="px-3 py-2"><Badge label={p.alert_level} palette={SEV_COLORS} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <ResearchNote>{data.label}. {data.note}</ResearchNote>
          </>
        )
      }}</Async>
    </div>
  )
}
