import { AlertTriangle, Info } from 'lucide-react'
import type { Quality } from '../types'
import { Badge, Card, Meter, QUALITY_COLORS } from './ui'
import { Async, useApi } from './states'

const SECTIONS: [string, string][] = [
  ['vitals', 'Vitals'], ['laboratory', 'Laboratories'], ['fluid_records', 'Fluids'],
  ['antibiotic_data', 'Antibiotics'], ['recent_vitals_6h', 'Recent vitals (6h)'],
]
const LAB_LABELS: Record<string, string> = {
  lactate: 'Lactate', wbc: 'WBC', creatinine: 'Creatinine', bilirubin: 'Bilirubin', platelets: 'Platelets',
}
const fill = (v: number) => (v >= 80 ? 'bg-green-600' : v >= 60 ? 'bg-red-400' : 'bg-red-700')

function QualityBody({ q }: { q: Quality }) {
  const warnings = q.warnings.filter(w => w.severity === 'warning')
  const notes = q.warnings.filter(w => w.severity === 'info')
  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Data quality · overall</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-4xl font-bold tabular-nums text-slate-900">{q.overall_score}%</span>
            <Badge label={q.level} palette={QUALITY_COLORS} />
          </div>
        </div>
        <div className="text-right text-xs text-slate-500">
          <div><span className="font-semibold text-slate-700">{q.hours_of_data}h</span> of data</div>
          <div>{q.sufficient ? 'sufficient for prediction' : 'insufficient (<6h)'}</div>
        </div>
      </div>

      <div className="space-y-1.5 text-xs">
        {SECTIONS.map(([k, label]) => (
          <div key={k} className="flex items-center gap-2">
            <span className="w-32 text-slate-600">{label}</span>
            <Meter value={q.sections[k]} fill={fill(q.sections[k])} />
            <span className="w-10 text-right tabular-nums text-slate-700">{Math.round(q.sections[k])}%</span>
          </div>
        ))}
        <div className="flex items-center gap-2" title={`Share of the five labs measured within the last ${q.stale_threshold_hours}h`}>
          <span className="w-32 text-slate-600">Lab timeliness</span>
          <Meter value={q.lab_timeliness} fill={fill(q.lab_timeliness)} />
          <span className="w-10 text-right tabular-nums text-slate-700">{Math.round(q.lab_timeliness)}%</span>
        </div>
      </div>

      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Last laboratory measurement</div>
        <div className="grid grid-cols-5 gap-1 text-center text-[11px]">
          {Object.entries(q.stale_labs_hours).map(([lab, hrs]) => {
            const never = q.last_measured_hour[lab] == null
            const stale = never || hrs > q.stale_threshold_hours
            return (
              <div key={lab} className={`rounded-md border px-1 py-1 ${stale ? 'border-red-300 bg-red-50 text-red-800' : 'border-slate-200 bg-slate-50 text-slate-700'}`}>
                <div className="truncate text-[10px] text-slate-500">{LAB_LABELS[lab] ?? lab}</div>
                <div className="font-semibold tabular-nums">{never ? 'never' : hrs === 0 ? 'now' : `${hrs}h ago`}</div>
              </div>
            )
          })}
        </div>
      </div>

      {warnings.length > 0 ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-2.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-red-800">
            <AlertTriangle className="h-3.5 w-3.5" /> Data quality warning{warnings.length > 1 ? 's' : ''}
          </div>
          <ul className="mt-1 space-y-1 text-xs text-red-900">
            {warnings.map(w => (
              <li key={w.code + (w.variable ?? '')}><span className="font-medium">{w.title}.</span> {w.message}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="text-xs text-green-700">No missing or stale data in the current record.</div>
      )}
      {notes.map(w => (
        <div key={w.code} className="flex gap-1.5 text-[11px] text-slate-500"><Info className="mt-0.5 h-3 w-3 shrink-0" />{w.message}</div>
      ))}
      <div className="text-[10px] leading-snug text-slate-500">
        Laboratory completeness is low by design: labs are sampled every 4–8 h, not hourly, so timeliness is the
        better indicator for them. Overall = 40% vitals + 30% labs + 20% fluids + 10% recent vitals, reduced when
        a lab is older than {q.stale_threshold_hours}h or under 6h of data exist.
      </div>
    </div>
  )
}

export default function DataQualityCard({ pid, refreshKey = 0, className = '' }: { pid: string; refreshKey?: unknown; className?: string }) {
  const state = useApi<Quality>(`/patients/${pid}/data-quality`, refreshKey)
  return (
    <Card className={className}>
      <Async state={state} what="data quality">{q => <QualityBody q={q} />}</Async>
    </Card>
  )
}
