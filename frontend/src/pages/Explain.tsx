import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { ErrorState, Loading } from '../components/states'
import type { Explanation, PatientSummary } from '../types'
import { Badge, Card, STATE_COLORS } from '../components/ui'

const TASKS = [
  ['sepsis_state', 'Sepsis state'],
  ['deterioration_6h', '6h deterioration'],
  ['deterioration_12h', '12h deterioration'],
  ['deterioration_24h', '24h deterioration'],
  ['antibiotic_response', 'Antibiotic response'],
  ['fluid_status', 'Fluid status'],
  ['recovery', 'Recovery trajectory'],
]

export default function Explain() {
  const [params, setParams] = useSearchParams()
  const [patients, setPatients] = useState<PatientSummary[]>([])
  const [task, setTask] = useState('sepsis_state')
  const [exp, setExp] = useState<Explanation | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState(0)
  const pid = params.get('pid') ?? ''

  useEffect(() => {
    api<{ patients: PatientSummary[] }>('/patients').then(d => {
      setPatients(d.patients)
      if (!pid && d.patients.length) setParams({ pid: d.patients[0].patient_id })
    }).catch(e => setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
  }, []) // eslint-disable-line

  useEffect(() => {
    if (!pid) return
    setLoading(true); setExp(null); setError(null)
    api<Explanation>(`/explanations/${pid}?task=${task}`).then(setExp)
      .catch(e => setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => setLoading(false))
  }, [pid, task, attempt])

  const maxAbs = Math.max(...(exp?.factors.map(f => Math.abs(f.contribution)) ?? [1]), 0.001)

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">AI Explainability</h1>
      <div className="flex flex-wrap items-center gap-2">
        <select value={pid} onChange={e => setParams({ pid: e.target.value })}
          className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm">
          {patients.map(p => <option key={p.patient_id} value={p.patient_id}>{p.patient_id} — {p.state}</option>)}
        </select>
        {TASKS.map(([k, label]) => (
          <button key={k} onClick={() => setTask(k)}
            className={`rounded-lg px-3 py-1.5 text-sm ${task === k ? 'bg-green-700 text-white font-semibold' : 'bg-slate-200 text-slate-600 hover:bg-slate-300'}`}>
            {label}
          </button>
        ))}
      </div>

      {loading && <Loading label="Computing SHAP explanation…" />}
      {error && !loading && <ErrorState what="the explanation" error={error} onRetry={() => setAttempt(a => a + 1)} />}
      {exp && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Card title="Prediction">
            <Badge label={exp.predicted_label} palette={STATE_COLORS} />
            <div className="mt-3 text-4xl font-bold tabular-nums">{(exp.probability * 100).toFixed(0)}%</div>
            <div className="text-xs text-slate-500">model probability</div>
            <div className="mt-3 text-xs text-slate-500">Model: <span className="text-slate-700">{exp.model.replace(/_/g, ' ')}</span></div>
            <div className="mt-4 rounded-lg border border-red-300 bg-red-50 p-2 text-[11px] text-red-700">
              AI-generated risk assessment. Clinical evaluation is required. Contributions reflect model behaviour,
              not verified clinical causation.
            </div>
          </Card>
          <Card title="Top contributing factors (local explanation)" className="xl:col-span-2">
            <div className="space-y-2">
              {exp.factors.map(f => (
                <div key={f.feature} className="flex items-center gap-3 text-sm">
                  <div className="w-56 truncate text-slate-700" title={f.feature}>{f.label}</div>
                  <div className="w-20 text-right text-xs tabular-nums text-slate-500">{f.value ?? '—'}</div>
                  <div className="relative h-4 flex-1 rounded bg-slate-200">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-slate-400" />
                    <div
                      className={`absolute inset-y-0 rounded ${f.contribution > 0 ? 'bg-red-600' : 'bg-green-600'}`}
                      style={{
                        left: f.contribution > 0 ? '50%' : `${50 - (Math.abs(f.contribution) / maxAbs) * 48}%`,
                        width: `${(Math.abs(f.contribution) / maxAbs) * 48}%`,
                      }} />
                  </div>
                  <div className={`w-16 text-right text-xs tabular-nums ${f.contribution > 0 ? 'text-red-600' : 'text-green-700'}`}>
                    {f.contribution > 0 ? '+' : ''}{f.contribution.toFixed(3)}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex gap-4 text-[11px] text-slate-500">
              <span><span className="mr-1 inline-block h-2 w-4 rounded bg-red-600" />pushes toward predicted class</span>
              <span><span className="mr-1 inline-block h-2 w-4 rounded bg-green-600" />pushes away from predicted class</span>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
