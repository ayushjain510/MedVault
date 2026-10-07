import type { ReactNode } from 'react'

/* Severity is encoded by INTENSITY within a red/green/white palette rather than
   by hue variety, so the scheme stays white/red/green without losing the
   clinical hierarchy. Escalation runs:
     favourable  → green (soft fill)
     neutral     → grey  (informational / insufficient data)
     moderate    → red-50  tint
     high        → red-100 tint, stronger border
     critical    → solid red, white text (maximum salience)               */

export const GREEN = 'bg-green-50 text-green-700 border-green-300'
export const GREEN_STRONG = 'bg-green-700 text-white border-green-800'
export const NEUTRAL = 'bg-slate-100 text-slate-600 border-slate-300'
export const RED_SOFT = 'bg-red-50 text-red-700 border-red-200'
export const RED_MID = 'bg-red-100 text-red-800 border-red-400'
export const RED_STRONG = 'bg-red-600 text-white border-red-700'

export const SEV_COLORS: Record<string, string> = {
  critical: RED_STRONG,
  high: RED_MID,
  moderate: RED_SOFT,
  info: NEUTRAL,
  none: NEUTRAL,
}

export const STATE_COLORS: Record<string, string> = {
  'Stable': GREEN,
  'At Risk': RED_SOFT,
  'Active Sepsis': RED_MID,
  'Severe/Deteriorating': RED_STRONG,
  'Treatment Response': GREEN,
  'Recovery': GREEN_STRONG,
  'Non-responding': RED_MID,
  'Escalation': RED_STRONG,
}

const PREFIX_TONES: [string, string][] = [
  ['AR-0', GREEN], ['AR-1', GREEN], ['AR-2', NEUTRAL], ['AR-3', RED_MID], ['AR-4', RED_STRONG],
  ['FS-0', GREEN], ['FS-1', RED_SOFT], ['FS-2', RED_SOFT], ['FS-3', RED_MID], ['FS-4', RED_MID], ['FS-5', NEUTRAL],
  ['RT-0', GREEN_STRONG], ['RT-1', GREEN], ['RT-2', RED_SOFT], ['RT-3', RED_MID], ['RT-4', RED_STRONG], ['RT-5', NEUTRAL],
  ['Deterioration', RED_MID], ['No deterioration', GREEN],
]

export const ENGINE_COLORS: Record<string, string> = {
  'Stable': GREEN,
  'Treatment Response': GREEN,
  'Improving / Recovery': GREEN_STRONG,
  'Monitoring Required': RED_SOFT,
  'Treatment Response Uncertain': NEUTRAL,
  'Persistent Concern': RED_MID,
  'Fluid Status Concern': RED_MID,
  'Poor Recovery Trajectory': RED_MID,
  'High-Risk Clinical Trajectory': RED_STRONG,
  'Insufficient Data': NEUTRAL,
}

/* MedVault Composite Risk Score bands follow the same intensity ladder. */
export const RISK_COLORS: Record<string, string> = {
  LOW: GREEN, MODERATE: RED_SOFT, HIGH: RED_MID, CRITICAL: RED_STRONG,
  'INSUFFICIENT DATA': NEUTRAL,
}
export const RISK_TEXT: Record<string, string> = {
  LOW: 'text-green-700', MODERATE: 'text-red-500', HIGH: 'text-red-600', CRITICAL: 'text-red-700',
  'INSUFFICIENT DATA': 'text-slate-500',
}
export const RISK_FILL: Record<string, string> = {
  LOW: 'bg-green-600', MODERATE: 'bg-red-300', HIGH: 'bg-red-500', CRITICAL: 'bg-red-700',
  'INSUFFICIENT DATA': 'bg-slate-300',
}
export const QUALITY_COLORS: Record<string, string> = { GOOD: GREEN, FAIR: RED_SOFT, POOR: RED_MID }

export function toneFor(label: string): string | undefined {
  const hit = PREFIX_TONES.find(([p]) => label.startsWith(p))
  return hit?.[1] ?? ENGINE_COLORS[label]
}

export function Badge({ label, palette = {} }: { label: string; palette?: Record<string, string> }) {
  const cls = palette[label] ?? toneFor(label) ?? NEUTRAL
  return (
    <span className={`inline-block rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${cls}`}>
      {label}
    </span>
  )
}

export function RiskBar({ value }: { value: number | null }) {
  const v = value ?? 0
  // Four distinct fill steps: green → light red → mid red → deep red.
  const color = v >= 0.75 ? 'bg-red-700' : v >= 0.5 ? 'bg-red-500'
    : v >= 0.25 ? 'bg-red-300' : 'bg-green-600'
  return (
    <div className="flex items-center gap-2 min-w-[90px]">
      <div className="h-1.5 w-16 rounded-full bg-slate-200 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${v * 100}%` }} />
      </div>
      <span className="text-xs tabular-nums text-slate-600">{(v * 100).toFixed(0)}%</span>
    </div>
  )
}

/** Risk score as a compact bar + number + level badge (tables and lists). */
export function RiskScore({ score, level }: { score: number | null | undefined; level: string | null | undefined }) {
  const lv = level ?? 'INSUFFICIENT DATA'
  return (
    <div className="flex items-center gap-2 whitespace-nowrap">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full ${RISK_FILL[lv]}`} style={{ width: `${score ?? 0}%` }} />
      </div>
      <span className="w-6 text-right text-xs font-semibold tabular-nums text-slate-800">{score ?? '—'}</span>
      <Badge label={lv === 'INSUFFICIENT DATA' ? 'NO SCORE' : lv} palette={{ ...RISK_COLORS, 'NO SCORE': NEUTRAL }} />
    </div>
  )
}

export function Delta({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-xs text-slate-400">—</span>
  if (value === 0) return <span className="text-xs tabular-nums text-slate-500">±0</span>
  // a rising risk score is unfavourable
  return (
    <span className={`text-xs font-medium tabular-nums ${value > 0 ? 'text-red-600' : 'text-green-700'}`}>
      {value > 0 ? '▲' : '▼'} {Math.abs(value)}
    </span>
  )
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <h1 className="text-xl font-bold">{title}</h1>
        {subtitle && <div className="mt-0.5 text-sm text-slate-600">{subtitle}</div>}
      </div>
      {children && <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  )
}

export const INPUT = 'rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-green-500 focus:outline-none'
export const BTN = 'inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green-600'
export const BTN_PRIMARY = `${BTN} bg-green-700 text-white hover:bg-green-600`
export const BTN_SECONDARY = `${BTN} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`
export const BTN_DANGER = `${BTN} bg-red-600 text-white hover:bg-red-500`
export const TH = 'px-3 py-2.5 font-medium whitespace-nowrap'
export const THEAD = 'bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-600'

/** Horizontal 0-100 meter used by the risk and data-quality cards. */
export function Meter({ value, max = 100, fill = 'bg-green-600' }: { value: number | null; max?: number; fill?: string }) {
  return (
    <div className="h-2 flex-1 overflow-hidden rounded bg-slate-200">
      <div className={`h-full rounded ${fill}`} style={{ width: `${Math.min(100, ((value ?? 0) / max) * 100)}%` }} />
    </div>
  )
}

export function Card({ title, children, className = '' }: { title?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm ${className}`}>
      {title && <div className="mb-3 text-sm font-semibold text-slate-700">{title}</div>}
      {children}
    </div>
  )
}

export function StatCard({ label, value, accent = 'text-slate-900', hint }: { label: string; value: ReactNode; accent?: string; hint?: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold tabular-nums ${accent}`}>{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-slate-500">{hint}</div>}
    </div>
  )
}

/** Research framing stays next to the number it qualifies. */
export function ResearchNote({ children }: { children: ReactNode }) {
  return <div className="text-[10px] leading-snug text-red-700">{children}</div>
}

export function Disclaimer() {
  return (
    <div className="rounded-lg border-l-4 border-red-600 bg-red-50 px-3 py-2 text-[11px] leading-snug text-red-900">
      <strong>SYNTHETIC DEMONSTRATION DATA.</strong> This system is an AI-assisted research and clinical
      decision-support prototype. It does not diagnose disease, prescribe treatment, determine antibiotic
      selection, or independently recommend fluid therapy. All outputs require review by qualified
      healthcare professionals.
    </div>
  )
}
