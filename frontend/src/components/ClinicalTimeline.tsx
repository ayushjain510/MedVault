import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, ArrowDownUp, Bell, Bed, Brain, ChevronDown, ChevronRight, Droplets,
  FlaskConical, Gauge, HeartPulse, Microscope, Pill, PlayCircle,
} from 'lucide-react'
import type { Timeline, TimelineEvent } from '../types'
import { Badge, Card, NEUTRAL, SEV_COLORS, GREEN } from './ui'
import { Async, Empty, useApi } from './states'

const ICONS: Record<string, typeof Activity> = {
  admission: Bed, antibiotic: Pill, culture: Microscope, vital: HeartPulse, lab: FlaskConical,
  fluid: Droplets, state_change: Activity, prediction: Brain, risk_change: Gauge,
  alert: Bell, simulation: PlayCircle,
}
const MARKER: Record<string, string> = {
  critical: 'bg-red-600 text-white border-red-700',
  high: 'bg-red-100 text-red-700 border-red-400',
  moderate: 'bg-red-50 text-red-600 border-red-200',
  good: 'bg-green-50 text-green-700 border-green-300',
  info: 'bg-slate-100 text-slate-600 border-slate-300',
}
const SEV_LABEL: Record<string, string> = { ...SEV_COLORS, good: GREEN }
const SOURCE: Record<string, string> = {
  observed: 'Recorded observation', model: 'Model output', rule: 'Rule-based engine', simulation: 'Simulation',
}

function Event({ e, last }: { e: TimelineEvent; last: boolean }) {
  const [open, setOpen] = useState(false)
  const Icon = ICONS[e.type] ?? Activity
  const sev = e.severity ?? 'info'
  return (
    <li className="relative flex gap-3">
      <div className="flex flex-col items-center">
        <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${MARKER[sev]} ${e.simulated ? 'border-dashed' : ''}`}>
          <Icon className="h-3.5 w-3.5" />
        </div>
        {!last && <div className="w-px flex-1 bg-slate-200" />}
      </div>
      <div className="min-w-0 flex-1 pb-4">
        <button onClick={() => setOpen(o => !o)} aria-expanded={open}
          className="flex w-full flex-wrap items-center gap-x-2 gap-y-0.5 text-left">
          <span className="w-16 shrink-0 text-xs font-semibold tabular-nums text-slate-500">Hour {e.hour}</span>
          <span className="text-[10px] uppercase tracking-wide text-slate-500">{e.type_label}</span>
          <span className="text-sm font-semibold text-slate-900">{e.title}</span>
          {e.severity && e.severity !== 'info' && e.type !== 'state_change' && <Badge label={e.severity} palette={SEV_LABEL} />}
          {e.simulated && <Badge label="simulated" palette={{ simulated: NEUTRAL }} />}
          <span className="ml-auto text-slate-400">{open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}</span>
        </button>
        <div className={`pl-[4.5rem] text-xs text-slate-600 ${open ? '' : 'truncate'}`}>{e.detail}</div>
        {open && (
          <dl className="mt-1 flex flex-wrap gap-x-5 gap-y-0.5 pl-[4.5rem] text-[11px] text-slate-500">
            {e.value && <div><dt className="inline">Value: </dt><dd className="inline font-medium text-slate-700">{e.value}</dd></div>}
            <div><dt className="inline">Source: </dt><dd className="inline text-slate-700">{SOURCE[e.source ?? 'observed']}</dd></div>
            {e.until_hour != null && e.until_hour > e.hour && <div><dt className="inline">Through: </dt><dd className="inline text-slate-700">hour {e.until_hour}</dd></div>}
            {e.category && <div><dt className="inline">Category: </dt><dd className="inline text-slate-700">{e.category}</dd></div>}
          </dl>
        )}
      </div>
    </li>
  )
}

function TimelineBody({ tl }: { tl: Timeline }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [newestFirst, setNewestFirst] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  const events = useMemo(() => {
    const ev = tl.events.filter(e => !hidden.has(e.type))
    return newestFirst ? [...ev].reverse() : ev
  }, [tl, hidden, newestFirst])

  // Oldest-first is the reading order, but the latest events are what a
  // returning user needs — so keep the view pinned to the end of the record.
  useEffect(() => {
    if (box.current) box.current.scrollTop = newestFirst ? 0 : box.current.scrollHeight
  }, [events, newestFirst])

  const toggle = (t: string) => setHidden(h => {
    const n = new Set(h)
    if (n.has(t)) n.delete(t); else n.add(t)
    return n
  })

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        {Object.entries(tl.event_types).filter(([t]) => tl.counts[t]).map(([t, label]) => (
          <button key={t} onClick={() => toggle(t)} aria-pressed={!hidden.has(t)}
            className={`rounded-full border px-2.5 py-0.5 text-xs transition ${hidden.has(t)
              ? 'border-slate-200 bg-white text-slate-400 line-through' : 'border-green-300 bg-green-50 text-green-800'}`}>
            {label} <span className="tabular-nums opacity-70">{tl.counts[t]}</span>
          </button>
        ))}
        <button onClick={() => setNewestFirst(n => !n)}
          className="ml-auto flex items-center gap-1 rounded-lg border border-slate-300 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-50">
          <ArrowDownUp className="h-3 w-3" /> {newestFirst ? 'Newest first' : 'Oldest first'}
        </button>
      </div>
      {events.length === 0
        ? <Empty>No events match the selected filters.</Empty>
        : (
          <div ref={box} className="max-h-[32rem] overflow-y-auto pr-2">
            <ol>{events.map((e, i) => <Event key={`${e.hour}-${e.type}-${e.title}`} e={e} last={i === events.length - 1} />)}</ol>
          </div>
        )}
      <div className="mt-2 text-[10px] text-slate-500">
        {events.length} of {tl.events.length} events through hour {tl.current_hour}. The timeline lists threshold crossings,
        step changes and model/state transitions, not every measurement. Dashed markers are synthetic simulation hours.
      </div>
    </>
  )
}

export default function ClinicalTimeline({ pid, refreshKey = 0 }: { pid: string; refreshKey?: unknown }) {
  const state = useApi<Timeline>(`/patients/${pid}/timeline`, refreshKey)
  return (
    <Card title="Clinical timeline">
      <Async state={state} what="the clinical timeline">{tl => <TimelineBody tl={tl} />}</Async>
    </Card>
  )
}
