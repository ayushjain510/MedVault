import { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { PatientSummary } from '../types'
import { INPUT } from './ui'
import { ErrorState, useApi } from './states'

/** Patient selector bound to the `?pid=` query parameter. Defaults to the
 *  first patient the API returns, never to a hardcoded ID. */
export function usePatientParam(refreshKey: unknown = 0) {
  const [params, setParams] = useSearchParams()
  const list = useApi<{ patients: PatientSummary[] }>('/patients', refreshKey)
  const pid = params.get('pid') ?? ''
  const patients = useMemo(() => list.data?.patients ?? [], [list.data])

  useEffect(() => {
    if (!pid && patients.length) setParams({ pid: patients[0].patient_id }, { replace: true })
  }, [pid, patients, setParams])

  const current = patients.find(p => p.patient_id === pid) ?? null
  return { pid, setPid: (v: string) => setParams({ pid: v }), patients, current, list }
}

export default function PatientPicker({ picker }: { picker: ReturnType<typeof usePatientParam> }) {
  const { pid, setPid, patients, list } = picker
  if (list.error && !list.data) return <ErrorState what="the patient list" error={list.error} onRetry={list.reload} />
  return (
    <label className="flex items-center gap-2 text-xs text-slate-600">
      Patient
      <select value={pid} onChange={e => setPid(e.target.value)} className={INPUT} aria-label="Select patient">
        {!patients.length && <option value="">Loading…</option>}
        {patients.map(p => (
          <option key={p.patient_id} value={p.patient_id}>
            {p.patient_id} — risk {p.risk_score ?? '—'} {p.risk_level ? `(${p.risk_level})` : ''}
          </option>
        ))}
      </select>
    </label>
  )
}
