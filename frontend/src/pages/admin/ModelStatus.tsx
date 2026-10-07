import { Card, PageHeader } from '../../components/ui'
import { Async, useApi } from '../../components/states'
import { StatusPill } from '../dashboards/AdminDashboard'
import { ModelTable } from './SystemHealth'
import type { Health } from './SystemHealth'

interface ModelsInfo {
  trained_at: string; dataset: string
  tasks: Record<string, { best_model: string; classes: string[] }>
}

/** Operational view of the model service for administrators: what is deployed
 *  and whether it is loaded. Evaluation metrics live in the researcher's Model Lab. */
export default function ModelStatus() {
  const health = useApi<Health>('/admin/system-health')
  const info = useApi<ModelsInfo>('/models')
  return (
    <div className="space-y-4">
      <PageHeader title="Model Status" subtitle="Which model serves each prediction task, and whether the model service has it loaded." />
      <Async state={health} what="the model service status">{h => (
        <>
          <Card title={<span className="flex items-center justify-between">Model service <StatusPill status={h.model_service.status} /></span>}>
            <div className="text-sm text-slate-700">{h.model_service.loaded} of {h.model_service.expected} models loaded.</div>
            {h.model_service.error && <div className="mt-1 text-sm text-red-600">{h.model_service.error}</div>}
          </Card>
          <ModelTable models={h.models} />
        </>
      )}</Async>
      <Async state={info} what="the deployed models">{m => (
        <Card title="Output classes per task">
          <div className="space-y-2 text-xs">
            {Object.entries(m.tasks).map(([task, t]) => (
              <div key={task}>
                <span className="font-medium capitalize text-slate-800">{task.replace(/_/g, ' ')}</span>
                <span className="text-slate-500"> · {t.classes.join(' · ')}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 text-[11px] text-slate-500">
            Dataset {m.dataset}, trained {new Date(m.trained_at).toLocaleString()}. Models are trained offline
            (<code>ml/train.py</code>); retraining is not available from the application.
          </div>
        </Card>
      )}</Async>
    </div>
  )
}
