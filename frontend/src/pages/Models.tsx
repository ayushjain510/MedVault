import { useEffect, useState } from 'react'
import { api } from '../api'
import { Card } from '../components/ui'

interface Metrics {
  accuracy: number; precision_macro: number; recall_macro: number
  f1_macro: number; f1_weighted: number; roc_auc: number | null
  pr_auc?: number; brier?: number; sensitivity?: number; specificity?: number
  confusion_matrix: number[][]
}
interface TaskReport {
  classes: string[]; best_model: string
  models: Record<string, { val: Metrics; test: Metrics }>
}
interface Perf {
  report: Record<string, TaskReport>
  global_importance: Record<string, { model: string; top_features: { label: string; importance: number }[] }>
  trained_at: string; dataset: string
}

const MODEL_NAMES: Record<string, string> = {
  logistic_regression: 'Logistic Regression', random_forest: 'Random Forest', xgboost: 'XGBoost', lightgbm: 'LightGBM',
}

function Matrix({ m, classes }: { m: number[][]; classes: string[] }) {
  const max = Math.max(...m.flat(), 1)
  return (
    <div className="overflow-x-auto">
      <table className="text-[10px]">
        <thead><tr><th className="p-1 text-slate-500">true \ pred</th>
          {classes.map(c => <th key={c} className="p-1 text-slate-500 max-w-16 truncate" title={c}>{c.slice(0, 8)}</th>)}</tr></thead>
        <tbody>
          {m.map((row, i) => (
            <tr key={i}><td className="p-1 text-slate-500 max-w-24 truncate" title={classes[i]}>{classes[i]?.slice(0, 12)}</td>
              {row.map((v, j) => (
                <td key={j} className="p-0.5">
                  <div className={`flex h-7 w-10 items-center justify-center rounded tabular-nums ${i === j ? 'text-green-700' : 'text-slate-700'}`}
                    style={{ background: `rgba(${i === j ? '16,185,129' : '239,68,68'},${0.08 + 0.5 * (v / max)})` }}>
                    {v}
                  </div>
                </td>))}
            </tr>))}
        </tbody>
      </table>
    </div>
  )
}

export default function Models() {
  const [perf, setPerf] = useState<Perf | null>(null)
  const [task, setTask] = useState('sepsis_state')
  const [err, setErr] = useState('')

  useEffect(() => {
    api<Perf>('/model-performance').then(setPerf).catch(() => setErr(
      'Model performance data is restricted to the researcher role. '
      + 'Sign in as researcher / res123 to view the Model Lab.'))
  }, [])

  if (err) return (
    <div className="rounded-xl border border-red-400 bg-red-50 p-4">
      <div className="font-semibold text-red-600">Access restricted</div>
      <p className="mt-1 text-sm text-slate-700">{err}</p>
    </div>
  )
  if (!perf) return <div className="text-slate-600">Loading…</div>
  const t = perf.report[task]
  const imp = perf.global_importance[task]
  const maxImp = Math.max(...imp.top_features.map(f => f.importance), 0.001)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">Model Lab</h1>
        <span className="text-xs text-slate-500">dataset: {perf.dataset} · trained {new Date(perf.trained_at).toLocaleString()}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {Object.keys(perf.report).map(k => (
          <button key={k} onClick={() => setTask(k)}
            className={`rounded-lg px-3 py-1.5 text-sm ${task === k ? 'bg-green-700 text-white font-semibold' : 'bg-slate-200 text-slate-600 hover:bg-slate-300'}`}>
            {k.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      <Card title={`Model comparison — validation set (best: ${MODEL_NAMES[t.best_model]})`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr>{['Model', 'Accuracy', 'Precision (macro)', 'Recall (macro)', 'F1 (macro)', 'F1 (weighted)', 'ROC-AUC', 'PR-AUC', 'Sens.', 'Spec.', 'Brier'].map(h => <th key={h} className="px-2 py-2">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {Object.entries(t.models).map(([name, r]) => (
                <tr key={name} className={name === t.best_model ? 'bg-green-50' : ''}>
                  <td className="px-2 py-2 font-medium">{MODEL_NAMES[name]}{name === t.best_model && <span className="ml-2 rounded bg-green-100 px-1.5 text-[10px] text-green-700">SELECTED</span>}</td>
                  {[r.val.accuracy, r.val.precision_macro, r.val.recall_macro, r.val.f1_macro, r.val.f1_weighted,
                    r.val.roc_auc, r.val.pr_auc, r.val.sensitivity, r.val.specificity, r.val.brier].map((v, i) =>
                    <td key={i} className="px-2 py-2 tabular-nums text-slate-700">{v != null ? v.toFixed(3) : '—'}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 text-[11px] text-slate-500">
          Selection prioritizes macro recall + macro F1 (missing a deteriorating patient is costlier than a false alarm),
          not raw accuracy.
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title={`Held-out test confusion matrix — ${MODEL_NAMES[t.best_model]}`}>
          <Matrix m={t.models[t.best_model].test.confusion_matrix} classes={t.classes} />
          <div className="mt-2 text-[11px] text-slate-500">Patient-level split: no patient appears in both train and test.</div>
        </Card>
        <Card title={`Global feature importance (${imp.model.replace(/_/g, ' ')})`}>
          <div className="space-y-1.5">
            {imp.top_features.slice(0, 15).map(f => (
              <div key={f.label} className="flex items-center gap-2 text-xs">
                <div className="w-52 truncate text-slate-700">{f.label}</div>
                <div className="h-3 flex-1 rounded bg-slate-200">
                  <div className="h-full rounded bg-green-600" style={{ width: `${(f.importance / maxImp) * 100}%` }} />
                </div>
                <div className="w-14 text-right tabular-nums text-slate-500">{f.importance.toFixed(3)}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
