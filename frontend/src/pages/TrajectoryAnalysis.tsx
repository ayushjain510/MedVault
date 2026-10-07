import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, PageHeader, RISK_FILL, TH, THEAD } from '../components/ui'
import { Async, useApi } from '../components/states'

interface Trajectories {
  archetypes: string[]
  bucket_hours: number
  risk_over_time: (Record<string, number> & { hour: number })[]
  summary: {
    archetype: string; n: number; mean_risk: number | null; min_risk: number | null; max_risk: number | null
    levels: Record<string, number>; recovery: Record<string, number>
  }[]
  note: string
}
const COLORS = ['#15803d', '#b91c1c', '#1d4ed8', '#a16207', '#7c3aed', '#0e7490', '#475569', '#be185d']
const LEVELS = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']
const nice = (a: string) => a.replace(/_/g, ' ')

export default function TrajectoryAnalysis() {
  const state = useApi<Trajectories>('/research/trajectories')
  const [focus, setFocus] = useState<string | null>(null)

  return (
    <div className="space-y-4">
      <PageHeader title="Trajectory Analysis"
        subtitle="How the composite risk score evolves across the cohort, grouped by the synthetic generator's ground-truth archetype." />
      <Async state={state} what="trajectory analysis">{d => {
        const color = Object.fromEntries(d.archetypes.map((a, i) => [a, COLORS[i % COLORS.length]]))
        return (
          <>
            <Card title={`Mean composite risk score over the stay (${d.bucket_hours}-hour buckets)`}>
              <div className="mb-2 flex flex-wrap gap-1.5">
                {d.archetypes.map(a => (
                  <button key={a} onClick={() => setFocus(f => (f === a ? null : a))} aria-pressed={focus === a}
                    className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs transition ${focus && focus !== a ? 'border-slate-200 text-slate-400' : 'border-slate-300 text-slate-700'}`}>
                    <span className="h-2 w-2 rounded-full" style={{ background: color[a] }} />{nice(a)}
                  </button>
                ))}
              </div>
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={d.risk_over_time} margin={{ top: 4, right: 12, bottom: 0, left: -18 }}>
                    <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                    <XAxis dataKey="hour" tick={{ fontSize: 10, fill: '#64748b' }} tickFormatter={h => `h${h}`} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#64748b' }} />
                    <Tooltip contentStyle={{ background: '#fff', border: '1px solid #cbd5e1', borderRadius: 8, fontSize: 12 }}
                      labelFormatter={h => `Hours ${h}–${Number(h) + d.bucket_hours - 1}`}
                      formatter={(v, name) => [`${v} / 100`, nice(String(name))]} />
                    {[25, 50, 75].map(y => <ReferenceLine key={y} y={y} stroke="#cbd5e1" strokeDasharray="4 4" />)}
                    {d.archetypes.map(a => (
                      <Line key={a} type="monotone" dataKey={a} stroke={color[a]} dot={false} connectNulls isAnimationActive={false}
                        strokeWidth={focus === a ? 3 : 1.8} strokeOpacity={focus && focus !== a ? 0.15 : 1} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-1 text-[11px] text-slate-500">{d.note} Dashed lines mark the MODERATE / HIGH / CRITICAL band limits.</div>
            </Card>

            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full text-sm">
                <thead className={THEAD}>
                  <tr>{['Archetype', 'Patients', 'Mean risk (latest hour)', 'Range', 'Risk levels', 'Predicted recovery class'].map(h => <th key={h} className={TH}>{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {d.summary.map(s => (
                    <tr key={s.archetype} className="hover:bg-slate-50">
                      <td className="px-3 py-2 font-medium capitalize">
                        <span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: color[s.archetype] }} />{nice(s.archetype)}
                      </td>
                      <td className="px-3 py-2 tabular-nums">{s.n}</td>
                      <td className="px-3 py-2 font-semibold tabular-nums">{s.mean_risk ?? '—'}</td>
                      <td className="px-3 py-2 text-xs tabular-nums text-slate-600">{s.min_risk ?? '—'} – {s.max_risk ?? '—'}</td>
                      <td className="px-3 py-2">
                        <div className="flex h-2 w-40 overflow-hidden rounded-full bg-slate-200"
                          title={LEVELS.map(l => `${l}: ${s.levels[l] ?? 0}`).join(' · ')}>
                          {LEVELS.map(l => <div key={l} className={RISK_FILL[l]} style={{ width: `${((s.levels[l] ?? 0) / s.n) * 100}%` }} />)}
                        </div>
                        <div className="mt-0.5 text-[10px] text-slate-500">{LEVELS.filter(l => s.levels[l]).map(l => `${l} ${s.levels[l]}`).join(' · ')}</div>
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-600">
                        {Object.entries(s.recovery).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}`).join(' · ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )
      }}</Async>
    </div>
  )
}
