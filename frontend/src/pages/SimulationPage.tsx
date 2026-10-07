import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../components/ui'
import PatientPicker, { usePatientParam } from '../components/PatientPicker'
import SimulationPanel from '../components/SimulationPanel'
import RiskCard from '../components/RiskCard'
import DataQualityCard from '../components/DataQualityCard'
import ClinicalTimeline from '../components/ClinicalTimeline'

/** Simulation workspace: the controls next to everything they change. */
export default function SimulationPage() {
  const [version, setVersion] = useState(0)
  const picker = usePatientParam(version)
  const { pid, current } = picker
  return (
    <div className="space-y-4">
      <PageHeader title="Scenario Simulation"
        subtitle="Advance a patient through synthetic hours and watch the pipeline respond: predictions, risk score, state, alerts and timeline.">
        <PatientPicker picker={picker} />
      </PageHeader>
      {pid && (
        <>
          <SimulationPanel pid={pid} currentHour={current?.last_hour ?? null} onAdvanced={() => setVersion(v => v + 1)} />
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
            <RiskCard pid={pid} refreshKey={version} className="xl:col-span-2" />
            <DataQualityCard pid={pid} refreshKey={version} />
          </div>
          <ClinicalTimeline pid={pid} refreshKey={version} />
          <Link to={`/patients/${pid}`} className="inline-block text-sm text-green-700 hover:underline">
            Open the full patient page for {pid} →
          </Link>
        </>
      )}
    </div>
  )
}
