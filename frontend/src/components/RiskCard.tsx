import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, Info } from 'lucide-react'
import type { Risk } from '../types'
import { Badge, Card, Delta, Meter, QUALITY_COLORS, ResearchNote, RISK_COLORS, RISK_TEXT } from './ui'
import { Async, useApi } from './states'

const CONCERN_FILL: Record<string, string> = {
  high: 'bg-red-600', moderate: 'bg-red-400', low: 'bg-green-600', unknown: 'bg-slate-300',
}
const BAND_FILL = ['bg-green-600', 'bg-red-300', 'bg-red-500', 'bg-red-700']

/** Four-band scale with a marker at the current score. */
function BandScale({ risk }: { risk: Risk }) {
  return (
    <div className="mt-3">
      <div className="relative">
        <div className="flex h-2 overflow-hidden rounded-full">
          {risk.bands.map((b, i) => {
            const end = risk.bands[i + 1]?.min ?? 100
            return <div key={b.level} className={BAND_FILL[i]} style={{ width: `${end - b.min}%`, opacity: b.level === risk.level ? 1 : 0.3 }} />
          })}
        </div>
        {risk.score != null && (
          <div className="absolute -top-1 h-4 w-1 -translate-x-1/2 rounded bg-slate-900" style={{ left: `${risk.score}%` }} />
        )}
      </div>
      <div className="mt-1 flex text-[9px] uppercase tracking-wide text-slate-500">
        {risk.bands.map((b, i) => {
          const end = risk.bands[i + 1]?.min ?? 101
          return <div key={b.level} style={{ width: `${(risk.bands[i + 1]?.min ?? 100) - b.min}%` }}>{b.level} {b.min}–{end - 1}</div>
        })}
      </div>
    </div>
  )
}

function RiskBody({ risk }: { risk: Risk }) {
  if (risk.score == null) {
    return (
      <div className="text-sm text-slate-600">
        <Badge label="INSUFFICIENT DATA" palette={RISK_COLORS} />
        <p className="mt-2">{risk.reason ?? 'No risk score can be produced for this patient yet.'}</p>
      </div>
    )
  }
  const dq = risk.data_quality
  const history = risk.history.filter(h => h.score != null)
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
      <div className="lg:col-span-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Patient risk</div>
        <div className={`mt-1 text-3xl font-bold ${RISK_TEXT[risk.level]}`}>{risk.level}</div>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="text-5xl font-bold tabular-nums text-slate-900">{risk.score}</span>
          <span className="text-lg text-slate-500">/ 100</span>
          <span className="ml-2 text-xs text-slate-500">vs 6h ago <Delta value={risk.delta_6h} /></span>
        </div>
        <BandScale risk={risk} />
        {history.length > 1 && (
          <div className="mt-3 h-20" aria-label="Risk score over the stay">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history} margin={{ top: 2, right: 2, bottom: 0, left: 2 }}>
                <XAxis dataKey="hour" hide />
                <YAxis domain={[0, 100]} hide />
                <Tooltip contentStyle={{ background: '#fff', border: '1px solid #cbd5e1', borderRadius: 8, fontSize: 12 }}
                  labelFormatter={h => `Hour ${h}`} formatter={(v) => [`${v} / 100`, 'Risk score']} />
                {risk.bands.slice(1).map(b => <ReferenceLine key={b.level} y={b.min} stroke="#cbd5e1" strokeDasharray="3 3" />)}
                <Area type="monotone" dataKey="score" stroke="#b91c1c" fill="#b91c1c1f" strokeWidth={1.6} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
            <div className="text-[10px] text-slate-500">Score across the stay (dashed lines: band limits)</div>
          </div>
        )}
      </div>

      <div className="lg:col-span-3">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Why is this patient {risk.level.toLowerCase()} risk?
        </div>
        <div className="mt-2 space-y-2">
          {risk.components.map(c => (
            <div key={c.key} title={c.detail}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="font-medium text-slate-800">{c.label}</span>
                <span className="truncate text-xs text-slate-600">{c.value ?? '—'}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2">
                <Meter value={c.points} max={c.max_points} fill={CONCERN_FILL[c.concern ?? 'unknown']} />
                <span className="w-20 text-right text-xs tabular-nums text-slate-700">
                  {c.points == null ? 'n/a' : <>+{c.points.toFixed(1)}<span className="text-slate-400"> / {c.max_points}</span></>}
                </span>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-2 text-[11px] text-slate-500">
          Points add up to the score. Each bar is filled relative to that component's maximum
          {risk.renormalised && ' (unavailable components are left out and the rest rescaled)'}.
        </div>
        {risk.floor_applied && (
          <div className="mt-2 flex gap-1.5 text-xs text-red-700">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            The state engine reports “{risk.engine_state}”, so the score is held at the HIGH band (raw score {risk.raw_score}).
          </div>
        )}
      </div>

      <div className="space-y-2 border-t border-slate-200 pt-3 lg:col-span-5">
        {dq && (
          <div className={`flex flex-wrap items-center gap-2 text-xs ${dq.caution ? 'text-red-800' : 'text-slate-600'}`}>
            {dq.caution && <AlertTriangle className="h-3.5 w-3.5" />}
            <span>Data quality {dq.overall_score}%</span>
            <Badge label={dq.level} palette={QUALITY_COLORS} />
            <span>{dq.interpretation}</span>
          </div>
        )}
        <ResearchNote>
          {risk.label}. {risk.note} It summarises existing model outputs for hour {risk.hour}; it is not a diagnosis
          and does not recommend treatment.
        </ResearchNote>
      </div>
    </div>
  )
}

export default function RiskCard({ pid, refreshKey = 0, className = '' }: { pid: string; refreshKey?: unknown; className?: string }) {
  const state = useApi<Risk>(`/patients/${pid}/risk`, refreshKey)
  const level = state.data?.level
  return (
    <Card className={`${level === 'CRITICAL' ? 'border-red-500' : level === 'HIGH' ? 'border-red-300' : ''} ${className}`}>
      <Async state={state} what="the risk score">{risk => <RiskBody risk={risk} />}</Async>
    </Card>
  )
}

