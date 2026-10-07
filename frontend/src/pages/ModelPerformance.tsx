import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, INPUT, PageHeader, TH, THEAD } from '../components/ui'
import { Async, useApi } from '../components/states'
import { MODEL_NAMES, taskName } from './dashboards/ResearcherDashboard'

type Metrics = Record<string, number | null> & { f1_macro: number; recall_macro: number; accuracy: number }
interface Perf {
  report: Record<string, { classes: string[]; best_model: string; models: Record<string, { val: Metrics; test: Metrics }> }>
  trained_at: string; dataset: string
}
const METRICS: [string, string][] = [
  ['f1_macro', 'Macro F1'], ['recall_macro', 'Macro recall'], ['precision_macro', 'Macro precision'],
  ['accuracy', 'Accuracy'], ['roc_auc', 'ROC-AUC'],
]
// One fixed colour per algorithm across every chart on the page.
const ALGO_COLOR: Record<string, string> = {
  logistic_regression: '#94a3b8', random_forest: '#15803d', xgboost: '#b91c1c', lightgbm: '#1d4ed8',
}

/** Cross-task summary. The per-task deep dive (confusion matrix, importances) is the Model Lab. */
export default function ModelPerformance() {
  const state = useApi<Perf>('/model-performance')
  const [metric, setMetric] = useState('f1_macro')
  const [split, setSplit] = useState<'val' | 'test'>('val')

  return (
    <div className="space-y-4">
      <PageHeader title="Model Performance" subtitle="All seven prediction tasks side by side: which algorithm was selected, and by how much.">
        <select value={metric} onChange={e => setMetric(e.target.value)} className={INPUT} aria-label="Metric">
          {METRICS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <select value={split} onChange={e => setSplit(e.target.value as 'val' | 'test')} className={INPUT} aria-label="Data split">
          <option value="val">Validation set</option>
          <option value="test">Held-out test set</option>
        </select>
      </PageHeader>
      <Async state={state} what="model performance">{perf => {
        const tasks = Object.entries(perf.report)
        const algos = Object.keys(tasks[0][1].models)
        const chart = tasks.map(([task, t]) => ({
          task: taskName(task),
          ...Object.fromEntries(algos.map(a => [a, t.models[a][split][metric]])),
        }))
        const label = METRICS.find(([k]) => k === metric)![1]
        return (
          <>
            <Card title={`${label} by task and algorithm — ${split === 'val' ? 'validation' : 'held-out test'} set`}>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
                    <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="task" tick={{ fontSize: 10, fill: '#64748b' }} interval={0} />
                    <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#64748b' }} />
                    <Tooltip contentStyle={{ background: '#fff', border: '1px solid #cbd5e1', borderRadius: 8, fontSize: 12 }}
                      formatter={(v, name) => [typeof v === 'number' ? v.toFixed(3) : '—', MODEL_NAMES[String(name)] ?? String(name)]} />
                    <Legend formatter={v => MODEL_NAMES[String(v)] ?? String(v)} wrapperStyle={{ fontSize: 12 }} />
                    {algos.map(a => <Bar key={a} dataKey={a} fill={ALGO_COLOR[a] ?? '#64748b'} isAnimationActive={false} />)}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full text-sm">
                <thead className={THEAD}>
                  <tr>
                    <th className={TH}>Task</th><th className={TH}>Selected</th>
                    {algos.map(a => <th key={a} className={TH}>{MODEL_NAMES[a] ?? a}</th>)}
                    <th className={TH}>Margin over runner-up</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {tasks.map(([task, t]) => {
                    const vals = algos.map(a => t.models[a][split][metric]).filter((v): v is number => v != null).sort((a, b) => b - a)
                    const best = t.models[t.best_model][split][metric]
                    const others = algos.filter(a => a !== t.best_model).map(a => t.models[a][split][metric]).filter((v): v is number => v != null)
                    const margin = best != null && others.length ? best - Math.max(...others) : null
                    return (
                      <tr key={task} className="hover:bg-slate-50">
                        <td className="px-3 py-2 font-medium capitalize">{taskName(task)}</td>
                        <td className="px-3 py-2">{MODEL_NAMES[t.best_model]}</td>
                        {algos.map(a => {
                          const v = t.models[a][split][metric]
                          return (
                            <td key={a} className={`px-3 py-2 tabular-nums ${a === t.best_model ? 'bg-green-50 font-semibold text-green-800' : 'text-slate-700'}`}>
                              {v != null ? v.toFixed(3) : '—'}{v != null && v === vals[0] && a !== t.best_model && <span className="ml-1 text-[10px] text-slate-500">top</span>}
                            </td>
                          )
                        })}
                        <td className={`px-3 py-2 tabular-nums ${margin != null && margin < 0 ? 'text-red-600' : 'text-slate-700'}`}>
                          {margin != null ? `${margin >= 0 ? '+' : ''}${margin.toFixed(3)}` : '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="text-[11px] text-slate-500">
              The selected model (green) maximises 0.55 × macro recall + 0.45 × macro F1 on the validation set, so it is not
              always the top value for a single metric — a negative margin means another algorithm scores higher on the
              metric shown. Dataset {perf.dataset}; splits are patient-level. For confusion matrices and feature importance
              open the <Link to="/models" className="text-green-700 hover:underline">Model Lab</Link>.
            </div>
          </>
        )
      }}</Async>
    </div>
  )
}
