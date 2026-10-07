import type { ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Card, PageHeader } from '../../components/ui'
import { Async, useApi } from '../../components/states'

interface Band { level: string; min: number }
interface SettingsData {
  authentication: { algorithm: string; token_lifetime_minutes: number; password_hashing: string; jwt_secret_is_default: boolean }
  database: { dialect: string }
  models: { dataset: string; trained_at: string; model_version: string; feature_version: string }
  risk_score: { bands: Band[]; max_points: Record<string, number>; minimum_hours: number }
  data_quality: { bands: Band[]; stale_lab_hours: number }
  simulation: { scenarios: string[]; max_hours_per_request: number }
  disclaimer: string
  note: string
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-slate-100 py-1.5 text-sm last:border-0">
      <span className="text-slate-600">{k}</span><span className="text-right font-medium text-slate-900">{children}</span>
    </div>
  )
}
const bands = (b: Band[]) => b.map(x => `${x.level} ≥ ${x.min}`).join(' · ')

export default function SystemSettings() {
  const state = useApi<SettingsData>('/admin/settings')
  return (
    <div className="space-y-4">
      <PageHeader title="System Settings" subtitle="Effective platform configuration (read-only). Secrets are never shown." />
      <Async state={state} what="system settings">{s => (
        <>
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            <Card title="Authentication">
              <Row k="Token signing">{s.authentication.algorithm}</Row>
              <Row k="Session lifetime">{s.authentication.token_lifetime_minutes / 60} hours</Row>
              <Row k="Password storage">{s.authentication.password_hashing}</Row>
              <Row k="JWT secret">{s.authentication.jwt_secret_is_default
                ? <span className="inline-flex items-center gap-1 text-red-700"><AlertTriangle className="h-3.5 w-3.5" />development default</span>
                : 'custom (set via JWT_SECRET)'}</Row>
            </Card>
            <Card title="Data & models">
              <Row k="Database">{s.database.dialect}</Row>
              <Row k="Dataset">{s.models.dataset}</Row>
              <Row k="Model / feature version">{s.models.model_version} / {s.models.feature_version}</Row>
              <Row k="Trained">{new Date(s.models.trained_at).toLocaleString()}</Row>
            </Card>
            <Card title="Composite risk score">
              <Row k="Bands">{bands(s.risk_score.bands)}</Row>
              <Row k="Minimum data">{s.risk_score.minimum_hours} hours</Row>
              {Object.entries(s.risk_score.max_points).map(([k, v]) => <Row key={k} k={`Max points · ${k.replace(/_/g, ' ')}`}>{v}</Row>)}
            </Card>
            <Card title="Data quality & simulation">
              <Row k="Quality bands">{bands(s.data_quality.bands)}</Row>
              <Row k="Lab considered stale after">{s.data_quality.stale_lab_hours} hours</Row>
              <Row k="Simulation scenarios">{s.simulation.scenarios.join(', ')}</Row>
              <Row k="Max hours per advance">{s.simulation.max_hours_per_request}</Row>
            </Card>
          </div>
          <Card title="Disclaimer shown across the platform"><p className="text-sm text-slate-700">{s.disclaimer}</p></Card>
          <div className="text-[11px] text-slate-500">{s.note}</div>
        </>
      )}</Async>
    </div>
  )
}
