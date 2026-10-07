import { Link } from 'react-router-dom'
import { PageHeader, RiskScore } from '../components/ui'
import PatientPicker, { usePatientParam } from '../components/PatientPicker'
import ClinicalTimeline from '../components/ClinicalTimeline'

export default function TimelinePage() {
  const picker = usePatientParam()
  const { pid, current } = picker
  return (
    <div className="space-y-4">
      <PageHeader title="Clinical Timeline"
        subtitle="Chronological record of the meaningful events of a stay: treatment, physiology, model outputs, state and risk changes, alerts.">
        <PatientPicker picker={picker} />
      </PageHeader>
      {current && (
        <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600">
          <span>{current.age}y · {current.sex} · hour {current.last_hour}</span>
          <RiskScore score={current.risk_score} level={current.risk_level} />
          <Link to={`/patients/${pid}`} className="text-green-700 hover:underline">Open patient page →</Link>
        </div>
      )}
      {pid && <ClinicalTimeline pid={pid} />}
    </div>
  )
}
