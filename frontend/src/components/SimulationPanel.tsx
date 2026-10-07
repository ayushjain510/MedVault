import { useEffect, useRef, useState } from 'react'
import { ArrowRight, FastForward, Loader2, Play, Square, StepForward } from 'lucide-react'
import { api, ApiError } from '../api'
import type { SimResult } from '../types'
import { Badge, BTN_DANGER, BTN_PRIMARY, BTN_SECONDARY, Card, INPUT, RISK_COLORS, SEV_COLORS } from './ui'
import { ErrorState, useApi } from './states'

interface Scenarios {
  scenarios: { key: string; label: string; description: string }[]
  max_hours: number
}

/** Scenario simulation controls. Every advance is a real backend tick: a new
 *  synthetic hour is stored and the full pipeline re-runs, then `onAdvanced`
 *  lets the page reload risk, timeline, alerts and data quality from the API. */
export default function SimulationPanel({ pid, currentHour, onAdvanced }: {
  pid: string; currentHour: number | null; onAdvanced: () => void
}) {
  const scenarios = useApi<Scenarios>('/sim/scenarios')
  const [scenario, setScenario] = useState('deteriorating')
  const [busy, setBusy] = useState(0)          // hours being advanced, 0 = idle
  const [auto, setAuto] = useState(false)
  const [result, setResult] = useState<SimResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const inFlight = useRef(false)

  useEffect(() => { setResult(null); setError(null); setAuto(false) }, [pid])

  async function advance(hours: number) {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(hours); setError(null)
    try {
      const r = await api<SimResult>(`/sim/${pid}/tick`, { method: 'POST', body: JSON.stringify({ scenario, hours }) })
      setResult(r)
      onAdvanced()
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)))
      setAuto(false)
    } finally {
      inFlight.current = false
      setBusy(0)
    }
  }

  // Auto-run: the original "live monitoring" loop — one hour every 3 s.
  const advanceRef = useRef(advance)
  useEffect(() => { advanceRef.current = advance })
  useEffect(() => {
    if (!auto) return
    const t = setInterval(() => advanceRef.current(1), 3000)
    return () => clearInterval(t)
  }, [auto])

  const chosen = scenarios.data?.scenarios.find(s => s.key === scenario)
  const alertTitles = result ? [...new Map(result.new_alerts.map(a => [a.title, a])).values()] : []

  return (
    <Card title={<span className="flex items-center gap-2">Scenario simulation <Badge label="Simulation mode" palette={{ 'Simulation mode': 'bg-slate-800 text-white border-slate-900' }} /></span>}>
      <div className="mb-3 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-700">
        <strong>Synthetic scenario simulation.</strong> Advancing generates new synthetic hours for this patient and
        runs them through the real pipeline (features → 7 models → risk score → state engine → alerts). It demonstrates
        the system; it does not model a real patient and never suggests a treatment.
      </div>

      {scenarios.error && <ErrorState what="the simulation scenarios" error={scenarios.error} onRetry={scenarios.reload} />}

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-600">
          <span className="mb-1 block font-medium">Scenario</span>
          <select value={scenario} onChange={e => setScenario(e.target.value)} disabled={busy > 0} className={`${INPUT} min-w-44`}>
            {(scenarios.data?.scenarios ?? [{ key: scenario, label: scenario, description: '' }]).map(s =>
              <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </label>
        <button onClick={() => advance(1)} disabled={busy > 0 || auto} className={BTN_PRIMARY}>
          {busy === 1 ? <Loader2 className="h-4 w-4 animate-spin" /> : <StepForward className="h-4 w-4" />} Advance 1 hour
        </button>
        <button onClick={() => advance(6)} disabled={busy > 0 || auto} className={BTN_PRIMARY}>
          {busy === 6 ? <Loader2 className="h-4 w-4 animate-spin" /> : <FastForward className="h-4 w-4" />} Advance 6 hours
        </button>
        <button onClick={() => setAuto(a => !a)} className={auto ? BTN_DANGER : BTN_SECONDARY}
          title="Advance one hour every 3 seconds">
          {auto ? <><Square className="h-3.5 w-3.5" /> Stop auto-run</> : <><Play className="h-3.5 w-3.5" /> Auto-run</>}
        </button>
        <div className="ml-auto text-right text-xs text-slate-500">
          Current simulation hour
          <div className="text-2xl font-bold tabular-nums text-slate-900">{currentHour ?? '—'}</div>
        </div>
      </div>
      {chosen?.description && <div className="mt-1.5 text-xs text-slate-500">{chosen.description}</div>}
      {busy > 0 && <div className="mt-2 text-xs text-slate-500" role="status">Running the pipeline for {busy} hour{busy > 1 ? 's' : ''}…</div>}
      {auto && <div className="mt-2 rounded-lg border border-green-400 bg-green-50 px-3 py-1.5 text-xs text-green-700">
        Auto-run active — a new synthetic hour is generated and scored every 3 s.
      </div>}
      {error && <div className="mt-3"><ErrorState what="the simulation result" error={error}
        onRetry={error.status === 403 ? undefined : () => advance(1)} /></div>}

      {result && (
        <div className="mt-4 border-t border-slate-200 pt-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Last advance · {result.hours_advanced}h under “{result.scenario}” · now hour {result.hour}
          </div>
          <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <div className="text-xs text-slate-500">Risk score</div>
              <div className="flex items-center gap-2 text-xl font-bold tabular-nums">
                {result.risk_before?.score ?? '—'} <ArrowRight className="h-4 w-4 text-slate-400" /> {result.risk.score ?? '—'}
                <Badge label={result.risk.level} palette={RISK_COLORS} />
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Patient state (rule-based engine)</div>
              <div className="mt-1"><Badge label={result.state.label} /></div>
              <div className="mt-1 text-xs text-slate-600">Recovery: {result.predictions.recovery?.predicted_label}</div>
            </div>
            <div>
              <div className="text-xs text-slate-500">New alerts ({result.new_alerts.length})</div>
              {alertTitles.length === 0 ? <div className="mt-1 text-xs text-slate-500">None raised.</div> : (
                <ul className="mt-1 space-y-0.5 text-xs text-slate-700">
                  {alertTitles.slice(0, 4).map(a => (
                    <li key={a.title} className="flex items-center gap-1.5"><Badge label={a.severity} palette={SEV_COLORS} /><span className="truncate">{a.title}</span></li>
                  ))}
                  {alertTitles.length > 4 && <li className="text-slate-500">+{alertTitles.length - 4} more — see the timeline</li>}
                </ul>
              )}
            </div>
          </div>
          {result.steps.length > 1 && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-left text-slate-500">
                  <tr>{['Hour', 'Risk', 'Level', '6h deterioration', 'State', 'Recovery'].map(h => <th key={h} className="px-2 py-1 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {result.steps.map(s => (
                    <tr key={s.hour}>
                      <td className="px-2 py-1 tabular-nums">{s.hour}</td>
                      <td className="px-2 py-1 font-semibold tabular-nums">{s.risk_score ?? '—'}</td>
                      <td className="px-2 py-1"><Badge label={s.risk_level} palette={RISK_COLORS} /></td>
                      <td className="px-2 py-1 tabular-nums">{s.det6_risk != null ? `${(s.det6_risk * 100).toFixed(0)}%` : '—'}</td>
                      <td className="px-2 py-1">{s.state}</td>
                      <td className="px-2 py-1">{s.recovery}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
