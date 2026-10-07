import { Link } from 'react-router-dom'
import { Card, Meter, PageHeader, RISK_FILL, StatCard, TH, THEAD } from '../../components/ui'
import { Async, useApi } from '../../components/states'

export interface TaskRow {
  task: string; best_model: string; n_classes: number; candidates: string[]
  val_f1_macro: number; val_recall_macro: number; test_f1_macro: number; test_recall_macro: number
  test_roc_auc: number | null
}
interface ResearcherData {
  n_patients: number; n_observations: number; n_predictions: number; n_simulated_hours: number
  n_features: number; prediction_tasks: TaskRow[]; n_prediction_tasks: number; models_available: number
  candidate_algorithms: string[]; n_models_evaluated: number; mean_val_f1_macro: number
  dataset: string; trained_at: string; model_version: string; feature_version: string
  splits: Record<string, number>
  data_completeness: Record<string, number | null>
  risk_levels: Record<string, number>; mean_risk_score: number | null
  recovery_distribution: Record<string, number>; archetypes: Record<string, number>
}
export const MODEL_NAMES: Record<string, string> = {
  logistic_regression: 'Logistic Regression', random_forest: 'Random Forest', xgboost: 'XGBoost', lightgbm: 'LightGBM',
}
export const taskName = (t: string) => t.replace(/_/g, ' ')
const LEVELS = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']

function Distribution({ data, total }: { data: Record<string, number>; total: number }) {
  return (
    <div className="space-y-1.5 text-xs">
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="flex items-center gap-2">
          <span className="w-44 truncate text-slate-600" title={k}>{k.replace(/_/g, ' ')}</span>
          <Meter value={v} max={total} />
          <span className="w-8 text-right tabular-nums text-slate-700">{v}</span>
        </div>
      ))}
    </div>
  )
}

export default function ResearcherDashboard() {
  const state = useApi<ResearcherData>('/dashboard/researcher')
  return (
    <div className="space-y-4">
      <PageHeader title="Researcher Dashboard" subtitle="AI / ML analytics — the models, the dataset and how predictions are distributed." />
      <Async state={state} what="the researcher dashboard">{d => (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            <StatCard label="Patients" value={d.n_patients} hint={Object.entries(d.splits).map(([k, v]) => `${k} ${v}`).join(' · ')} />
            <StatCard label="Observations" value={d.n_observations.toLocaleString()} hint={`${d.n_simulated_hours} simulated hours`} />
            <StatCard label="Prediction tasks" value={d.n_prediction_tasks} hint={`${d.n_predictions.toLocaleString()} stored predictions`} />
            <StatCard label="Models available" value={d.models_available} hint={`${d.n_models_evaluated} candidates evaluated`} />
            <StatCard label="Mean macro F1" value={d.mean_val_f1_macro.toFixed(3)} hint="selected models, validation" accent="text-green-700" />
            <StatCard label="Causal features" value={d.n_features} hint={`feature set v${d.feature_version}`} />
          </div>

          <Card title={<span className="flex items-center justify-between">Model performance by prediction task
            <Link to="/model-performance" className="text-xs font-normal text-green-700 hover:underline">Full comparison →</Link></span>}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className={THEAD}>
                  <tr>{['Task', 'Selected model', 'Classes', 'Val macro F1', 'Val macro recall', 'Test macro F1', 'Test ROC-AUC'].map(h => <th key={h} className={TH}>{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {d.prediction_tasks.map(t => (
                    <tr key={t.task} className="hover:bg-slate-50">
                      <td className="px-3 py-2 font-medium capitalize">{taskName(t.task)}</td>
                      <td className="px-3 py-2">{MODEL_NAMES[t.best_model] ?? t.best_model}</td>
                      <td className="px-3 py-2 tabular-nums">{t.n_classes}</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2"><Meter value={t.val_f1_macro} max={1} /><span className="w-12 tabular-nums">{t.val_f1_macro.toFixed(3)}</span></div>
                      </td>
                      <td className="px-3 py-2 tabular-nums">{t.val_recall_macro.toFixed(3)}</td>
                      <td className="px-3 py-2 tabular-nums">{t.test_f1_macro.toFixed(3)}</td>
                      <td className="px-3 py-2 tabular-nums">{t.test_roc_auc != null ? t.test_roc_auc.toFixed(3) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-2 text-[11px] text-slate-500">
              Dataset {d.dataset} · model version {d.model_version} · trained {new Date(d.trained_at).toLocaleString()} ·
              candidates per task: {d.candidate_algorithms.map(a => MODEL_NAMES[a] ?? a).join(', ')}. Metrics are from the
              synthetic held-out patients and will not transfer to real ICU data.
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <Card title={<span className="flex items-center justify-between">Data quality (dataset completeness)
              <Link to="/data-quality" className="text-xs font-normal text-green-700 hover:underline">Per patient →</Link></span>}>
              <div className="space-y-1.5 text-xs">
                {[['vitals', 'Vitals'], ['laboratory', 'Laboratories'], ['fluid_records', 'Fluid records']].map(([k, label]) => (
                  <div key={k} className="flex items-center gap-2">
                    <span className="w-28 text-slate-600">{label}</span>
                    <Meter value={d.data_completeness[k]} />
                    <span className="w-12 text-right tabular-nums text-slate-700">{d.data_completeness[k] ?? '—'}%</span>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-[11px] text-slate-500">Labs are sampled every 4–8 h, so their hourly completeness is low by design.</div>
            </Card>
            <Card title={<span className="flex items-center justify-between">Trajectory analysis
              <Link to="/trajectories" className="text-xs font-normal text-green-700 hover:underline">Open →</Link></span>}>
              <div className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">Predicted recovery trajectory (latest hour)</div>
              <Distribution data={d.recovery_distribution} total={d.n_patients} />
            </Card>
            <Card title="Composite risk score distribution">
              <div className="mb-2 text-xs text-slate-600">Mean score <strong className="tabular-nums">{d.mean_risk_score ?? '—'}</strong> / 100</div>
              <div className="space-y-1.5 text-xs">
                {LEVELS.map(l => (
                  <div key={l} className="flex items-center gap-2">
                    <span className="w-24 text-slate-600">{l}</span>
                    <Meter value={d.risk_levels[l] ?? 0} max={d.n_patients} fill={RISK_FILL[l]} />
                    <span className="w-8 text-right tabular-nums text-slate-700">{d.risk_levels[l] ?? 0}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 mb-2 text-[11px] uppercase tracking-wide text-slate-500">Generator archetypes (ground truth)</div>
              <Distribution data={d.archetypes} total={d.n_patients} />
            </Card>
          </div>
        </>
      )}</Async>
    </div>
  )
}
