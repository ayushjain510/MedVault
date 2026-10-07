import { useCallback, useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  AreaChart, Area, ReferenceLine,
} from 'recharts'
import { ArrowLeft, ChevronDown, ChevronRight } from 'lucide-react'
import { api, ApiError, can } from '../api'
import type { Prediction } from '../types'
import { Badge, Card, SEV_COLORS, STATE_COLORS } from '../components/ui'
import { ErrorState, Loading } from '../components/states'
import RiskCard from '../components/RiskCard'
import DataQualityCard from '../components/DataQualityCard'
import ClinicalTimeline from '../components/ClinicalTimeline'
import SimulationPanel from '../components/SimulationPanel'

interface Detail {
  patient_id: string; age: number; sex: string; icu: boolean; n_hours: number
  predictions: Record<string, Prediction>; alert_level: string
}
interface StateInfo {
  engine: { state: number | null; label: string; tone: string; reasons: string[] }
  treatment_response_index: {
    index: number; components: Record<string, number | null>; note: string
  } | null
}
interface WhatChanged {
  available: boolean; reason?: string; window_hours?: number
  overall_trajectory?: string
  changes?: { variable: string; label: string; direction: string; pct_change: number
    favourable: boolean | null; current: number; previous: number }[]
}
interface Similar {
  neighbours: { patient_id: string; distance: number; archetype: string }[]
  summary: string; method: string
}
type Row = Record<string, number | null> & { hour: number }

const CHART_TT = {
  contentStyle: { background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: '#94a3b8' },
}

function Chart({ data, k, label, color, domain }: { data: Row[]; k: string; label: string; color: string; domain?: [number | string, number | string] }) {
  return (
    <div className="h-40">
      <div className="mb-1 text-xs font-medium text-slate-600">{label}</div>
      <ResponsiveContainer width="100%" height="85%">
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
          <XAxis dataKey="hour" tick={{ fontSize: 10, fill: '#64748b' }} />
          <YAxis tick={{ fontSize: 10, fill: '#64748b' }} domain={domain ?? ['auto', 'auto']} />
          <Tooltip {...CHART_TT} />
          <Line type="monotone" dataKey={k} stroke={color} dot={false} strokeWidth={1.6} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function PatientDetail() {
  const { pid } = useParams()
  const [detail, setDetail] = useState<Detail | null>(null)
  const [vitals, setVitals] = useState<Row[]>([])
  const [labs, setLabs] = useState<Row[]>([])
  const [fluids, setFluids] = useState<Row[]>([])
  const [abx, setAbx] = useState<Record<string, unknown>[]>([])
  const [detSeries, setDetSeries] = useState<Row[]>([])
  const [stateInfo, setStateInfo] = useState<StateInfo | null>(null)
  const [wc, setWc] = useState<WhatChanged | null>(null)
  const [similar, setSimilar] = useState<Similar | null>(null)
  const [recSeries, setRecSeries] = useState<Row[]>([])
  const [showDet, setShowDet] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  // Bumped after every simulation advance: the risk, data-quality and timeline
  // cards re-fetch from the API, so everything on the page reflects the new hour.
  const [version, setVersion] = useState(0)

  const loadAll = useCallback(async () => {
    if (!pid) return
    try {
      const [d, v, l, f, a, pr] = await Promise.all([
        api<Detail>(`/patients/${pid}`),
        api<{ series: Row[] }>(`/patients/${pid}/vitals`),
        api<{ series: Row[] }>(`/patients/${pid}/labs`),
        api<{ series: Row[] }>(`/patients/${pid}/fluids`),
        api<{ records: Record<string, unknown>[] }>(`/patients/${pid}/antibiotics`),
        api<{ tasks: Record<string, { hour: number; probabilities: Record<string, number> }[]> }>(`/patients/${pid}/predictions?task=deterioration_6h`),
      ])
      setDetail(d); setVitals(v.series); setLabs(l.series); setFluids(f.series)
      setAbx(a.records); setError(null)
      setDetSeries((pr.tasks['deterioration_6h'] ?? []).map(r => ({ hour: r.hour, risk: r.probabilities['Deterioration ≤6h'] ?? 0 })))
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)))
      return
    }
    // Secondary panels fail independently: one broken request must not blank the page.
    api<StateInfo>(`/patients/${pid}/state`).then(setStateInfo).catch(() => setStateInfo(null))
    api<WhatChanged>(`/patients/${pid}/what-changed`).then(setWc).catch(() => setWc(null))
    api<Similar>(`/patients/${pid}/similar`).then(setSimilar).catch(() => setSimilar(null))
    api<{ series: { hour: number; score: number; label: string }[] }>(`/patients/${pid}/recovery-trajectory`)
      .then(r => setRecSeries(r.series as unknown as Row[])).catch(() => setRecSeries([]))
  }, [pid])

  useEffect(() => { setDetail(null); setError(null); loadAll() }, [loadAll])

  const onAdvanced = useCallback(() => { setVersion(v => v + 1); loadAll() }, [loadAll])

  if (error && !detail) {
    return (
      <div className="space-y-3">
        <Link to="/patients" className="flex items-center gap-1 text-sm text-slate-600 hover:text-slate-800"><ArrowLeft className="h-4 w-4" />Patients</Link>
        <ErrorState what={`patient ${pid}`} error={error} onRetry={loadAll} />
      </div>
    )
  }
  if (!detail) return <Loading label="Loading patient…" />
  const p = detail.predictions
  const recScore = recSeries.length ? (recSeries[recSeries.length - 1] as { score?: number }).score ?? null : null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/patients" className="flex items-center gap-1 text-sm text-slate-600 hover:text-slate-800"><ArrowLeft className="h-4 w-4" />Patients</Link>
        <h1 className="text-xl font-bold">{detail.patient_id}</h1>
        <span className="text-sm text-slate-600">{detail.age}y · {detail.sex} · ICU · hour {detail.n_hours - 1}</span>
        {stateInfo && <Badge label={stateInfo.engine.label} />}
        <span className="flex items-center gap-1 text-xs text-slate-500">alerts <Badge label={detail.alert_level} palette={SEV_COLORS} /></span>
        <span className="ml-auto rounded-md border border-slate-300 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600">Synthetic data · research prototype</span>
      </div>

      {/* Headline summary: composite risk + the quality of the data behind it */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <RiskCard pid={detail.patient_id} refreshKey={version} className="xl:col-span-2" />
        <DataQualityCard pid={detail.patient_id} refreshKey={version} />
      </div>

      {/* PRIMARY: recovery trajectory is the platform's headline output */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Card title="Recovery trajectory" className="lg:col-span-2 border-green-400">
          {p.recovery ? (
            <div className="flex flex-wrap items-center gap-6">
              <div>
                <div className="text-3xl font-bold text-slate-900">{p.recovery.predicted_label}</div>
                <div className="mt-1 text-sm text-slate-600">
                  {(p.recovery.probability * 100).toFixed(0)}% model probability — not certainty
                </div>
              </div>
              {recScore != null && (
                <div className="ml-auto text-right">
                  <div className={`text-5xl font-bold tabular-nums ${recScore >= 70 ? 'text-green-700' : recScore >= 45 ? 'text-red-600' : 'text-red-600'}`}>
                    {recScore}
                  </div>
                  <div className="text-[10px] text-slate-500">recovery score / 100</div>
                </div>
              )}
            </div>
          ) : <span className="text-slate-500">—</span>}
        </Card>
        <Card title="Overall patient state (rule-based engine)">
          {stateInfo ? (
            <>
              <Badge label={stateInfo.engine.label} />
              <ul className="mt-2 space-y-1 text-xs text-slate-600">
                {stateInfo.engine.reasons.map((r, i) => <li key={i}>• {r}</li>)}
              </ul>
              <div className="mt-2 text-[10px] text-slate-500">
                Recovery-led rule-based combination of model outputs (dashboard interpretation), separate from the ML predictions.
              </div>
            </>
          ) : <span className="text-slate-500">—</span>}
        </Card>
      </div>

      <Card title="Recovery trajectory over time" className="border-green-400">
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={recSeries} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
              <XAxis dataKey="hour" tick={{ fontSize: 10, fill: '#64748b' }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#64748b' }} />
              <Tooltip {...CHART_TT} formatter={(v: unknown, _n: unknown, e: { payload?: { label?: string } }) => [`${v} / 100`, e?.payload?.label ?? 'Recovery score']} />
              <ReferenceLine y={70} stroke="#16a34a" strokeDasharray="4 4" />
              <ReferenceLine y={45} stroke="#f87171" strokeDasharray="4 4" />
              <Area type="monotone" dataKey="score" stroke="#16a34a" fill="#16a34a33" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-1 text-[10px] text-slate-500">
          Probability-weighted favourability of the recovery model's output distribution — model-derived, not a validated clinical score.
        </div>
      </Card>

      {/* Treatment-response modules */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {([
          ['Antibiotic response', p.antibiotic_response],
          ['Fluid status', p.fluid_status],
          ['Sepsis state classifier', p.sepsis_state],
        ] as [string, Prediction | undefined][]).map(([label, pred]) => (
          <Card key={label} title={label}>
            {pred ? (
              <>
                <Badge label={pred.predicted_label} palette={label === 'Sepsis state classifier' ? STATE_COLORS : {}} />
                <div className="mt-2 text-2xl font-bold tabular-nums">{(pred.probability * 100).toFixed(0)}%</div>
                <div className="text-[10px] text-slate-500">model probability — not certainty</div>
              </>
            ) : <span className="text-slate-500">—</span>}
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Card title="Treatment Response Index">
          {stateInfo?.treatment_response_index ? (
            <>
              <div className="text-4xl font-bold tabular-nums">
                {stateInfo.treatment_response_index.index}<span className="text-lg text-slate-500"> / 100</span>
              </div>
              <div className="mt-2 space-y-1 text-xs">
                {Object.entries(stateInfo.treatment_response_index.components).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2">
                    <span className="w-40 text-slate-600">{k.replace(/_/g, ' ')}</span>
                    <div className="h-2 flex-1 rounded bg-slate-200">
                      <div className="h-full rounded bg-green-600" style={{ width: `${v ?? 0}%` }} />
                    </div>
                    <span className="w-8 text-right tabular-nums text-slate-700">{v ?? '—'}</span>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-[10px] text-red-700">Research-derived composite indicator — not a validated clinical score.</div>
            </>
          ) : <span className="text-slate-500">—</span>}
        </Card>
        <Card title={`What changed? (last ${wc?.window_hours ?? 6}h vs previous)`}>
          {wc?.available && wc.changes ? (
            <>
              <div className="space-y-1 text-sm">
                {wc.changes.slice(0, 6).map(c => (
                  <div key={c.variable} className="flex items-center justify-between">
                    <span className="text-slate-700">
                      <span className={c.favourable == null ? 'text-slate-500' : c.favourable ? 'text-green-700' : 'text-red-600'}>
                        {c.direction === 'up' ? '↑' : '↓'}
                      </span>{' '}{c.label}
                    </span>
                    <span className="tabular-nums text-xs text-slate-600">{c.pct_change > 0 ? '+' : ''}{c.pct_change}%</span>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-xs">Overall trajectory: <Badge label={wc.overall_trajectory ?? ''} palette={{
                'IMPROVING': 'bg-green-50 text-green-700 border-green-400',
                'WORSENING': 'bg-red-50 text-red-600 border-red-400',
                'MIXED / STABLE': 'bg-slate-300/30 text-slate-700 border-slate-400/40' }} /></div>
            </>
          ) : <span className="text-sm text-slate-500">{wc?.reason ?? '—'}</span>}
        </Card>
      </div>

      {/* SUPPORTING SIGNAL: deterioration risk, collapsed by default */}
      <div className="rounded-xl border border-slate-200 bg-slate-100/40">
        <button onClick={() => setShowDet(s => !s)}
          className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm text-slate-600 hover:text-slate-800">
          {showDet ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <span className="font-medium">Deterioration risk — supporting signal</span>
          <span className="ml-auto flex items-center gap-3 text-xs">
            {(['deterioration_6h', 'deterioration_12h', 'deterioration_24h'] as const).map(t => {
              const pr = p[t]
              const risk = pr ? Object.entries(pr.probabilities).find(([k]) => k.startsWith('Deterioration'))?.[1] ?? 0 : 0
              return (
                <span key={t} className="tabular-nums text-slate-500">
                  {t.replace('deterioration_', '')} <span className={risk >= 0.75 ? 'text-red-600' : risk >= 0.5 ? 'text-red-600' : risk >= 0.25 ? 'text-red-600' : 'text-green-700'}>{(risk * 100).toFixed(0)}%</span>
                </span>
              )
            })}
          </span>
        </button>
        {showDet && (
          <div className="border-t border-slate-200 p-4">
            <div className="mb-3 text-[11px] text-slate-500">
              Deterioration models inform the state engine as a corroborating signal; the platform's
              primary output is the recovery trajectory above.
            </div>
            <div className="h-36">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={detSeries} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                  <XAxis dataKey="hour" tick={{ fontSize: 10, fill: '#64748b' }} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#64748b' }} />
                  <Tooltip {...CHART_TT} formatter={(v) => `${(Number(v) * 100).toFixed(0)}%`} />
                  <ReferenceLine y={0.5} stroke="#ef4444" strokeDasharray="4 4" />
                  <ReferenceLine y={0.75} stroke="#b91c1c" strokeDasharray="4 4" />
                  <Area type="monotone" dataKey="risk" stroke="#94a3b8" fill="#94a3b822" strokeWidth={1.4} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>

      <Card title="Vital signs">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Chart data={vitals} k="heart_rate" label="Heart rate (bpm)" color="#dc2626" />
          <Chart data={vitals} k="map" label="MAP (mmHg)" color="#16a34a" />
          <Chart data={vitals} k="sbp" label="Systolic BP (mmHg)" color="#16a34a" />
          <Chart data={vitals} k="resp_rate" label="Respiratory rate (/min)" color="#f87171" />
          <Chart data={vitals} k="spo2" label="SpO2 (%)" color="#16a34a" domain={[80, 100]} />
          <Chart data={vitals} k="temperature" label="Temperature (°C)" color="#dc2626" />
        </div>
      </Card>

      <Card title="Laboratory data (measured intermittently — gaps are real sampling gaps)">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Chart data={labs} k="lactate" label="Lactate (mmol/L)" color="#dc2626" />
          <Chart data={labs} k="wbc" label="WBC (×10⁹/L)" color="#dc2626" />
          <Chart data={labs} k="creatinine" label="Creatinine (mg/dL)" color="#f87171" />
          <Chart data={labs} k="bilirubin" label="Bilirubin (mg/dL)" color="#dc2626" />
          <Chart data={labs} k="platelets" label="Platelets (×10⁹/L)" color="#16a34a" />
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Fluid management">
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={fluids} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis dataKey="hour" tick={{ fontSize: 10, fill: '#64748b' }} />
                <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
                <Tooltip {...CHART_TT} />
                <Area type="monotone" dataKey="cumulative_balance" name="Cumulative balance (mL)" stroke="#16a34a" fill="#16a34a33" strokeWidth={1.6} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2 text-center text-xs">
            {(() => {
              const last = fluids[fluids.length - 1]
              return <>
                <div className="rounded-lg bg-slate-100 p-2"><div className="text-slate-600">Input (last h)</div><div className="font-bold">{last?.fluid_input ?? '—'} mL</div></div>
                <div className="rounded-lg bg-slate-100 p-2"><div className="text-slate-600">Output (last h)</div><div className="font-bold">{last?.fluid_output ?? '—'} mL</div></div>
                <div className="rounded-lg bg-slate-100 p-2"><div className="text-slate-600">Cumulative</div><div className="font-bold">{last?.cumulative_balance ?? '—'} mL</div></div>
              </>
            })()}
          </div>
          <Chart data={fluids} k="urine_output" label="Urine output (mL/h)" color="#f87171" />
        </Card>

        <Card title="Antibiotic timeline">
          {abx.length === 0 && <div className="text-sm text-slate-500">No antibiotic records.</div>}
          {abx.map((a, i) => (
            <div key={i} className="mb-3 rounded-lg border border-slate-200 bg-white p-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-green-700">{String(a.abx_class)}</span>
                <span className="text-xs text-slate-500">started h{String(a.start_hour)} · {String(a.duration_hours)}h duration</span>
              </div>
              <div className="mt-1 text-xs text-slate-600">
                {a.culture_taken ? (
                  a.culture_positive
                    ? <>Culture positive{a.organism ? <> — <em>{String(a.organism)}</em></> : null}, {a.susceptible ? 'susceptible' : 'reduced susceptibility'}</>
                    : 'Culture taken — negative/pending'
                ) : 'No culture recorded'}
              </div>
              <div className="mt-2">
                <span className="text-xs text-slate-500 mr-2">AI response assessment:</span>
                <Badge label={p.antibiotic_response?.predicted_label ?? '—'} palette={STATE_COLORS} />
              </div>
              <div className="mt-1 text-[10px] text-slate-500">
                Antibiotic decisions remain with qualified clinicians. Review culture data, coverage, source control and clinical status.
              </div>
            </div>
          ))}
        </Card>
      </div>

      <ClinicalTimeline pid={detail.patient_id} refreshKey={version} />

      {can('simulation.run') && (
        <SimulationPanel pid={detail.patient_id} currentHour={detail.n_hours - 1} onAdvanced={onAdvanced} />
      )}

      <Card title="Similar historical trajectories (exploratory)">
        {similar ? (
          <>
            <div className="text-sm text-slate-700">{similar.summary}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {similar.neighbours.map(n => (
                <Link key={n.patient_id} to={`/patients/${n.patient_id}`}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-green-700 hover:underline">
                  {n.patient_id} <span className="text-slate-500">· d={n.distance}</span>
                </Link>
              ))}
            </div>
            <div className="mt-2 text-[10px] text-slate-500">{similar.method}</div>
          </>
        ) : <span className="text-slate-500">—</span>}
      </Card>

      {can('explainability.view') && (
        <Card title="Why this prediction?">
          <Link to={`/explain?pid=${detail.patient_id}`} className="text-sm text-green-700 hover:underline">
            Open the AI Explainability view for {detail.patient_id} →
          </Link>
        </Card>
      )}
    </div>
  )
}
