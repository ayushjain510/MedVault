import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { can, getRole, getToken } from './api'
import Layout from './components/Layout'
import Login from './pages/Login'
import Patients from './pages/Patients'
import PatientDetail from './pages/PatientDetail'
import Alerts from './pages/Alerts'
import Explain from './pages/Explain'
import Models from './pages/Models'
import DataQuality from './pages/DataQuality'
import RiskMonitoring from './pages/RiskMonitoring'
import TimelinePage from './pages/TimelinePage'
import SimulationPage from './pages/SimulationPage'
import ModelPerformance from './pages/ModelPerformance'
import TrajectoryAnalysis from './pages/TrajectoryAnalysis'
import ClinicianDashboard from './pages/dashboards/ClinicianDashboard'
import ResearcherDashboard from './pages/dashboards/ResearcherDashboard'
import AdminDashboard from './pages/dashboards/AdminDashboard'
import Users from './pages/admin/Users'
import Roles from './pages/admin/Roles'
import AuditLogs from './pages/admin/AuditLogs'
import SystemHealth from './pages/admin/SystemHealth'
import ModelStatus from './pages/admin/ModelStatus'
import SystemSettings from './pages/admin/SystemSettings'

function Protected({ children }: { children: React.ReactNode }) {
  return getToken() ? <>{children}</> : <Navigate to="/login" replace />
}

function NotPermitted() {
  return (
    <div className="mx-auto mt-16 max-w-md rounded-xl border border-slate-200 bg-white p-6 text-center shadow-sm">
      <Lock className="mx-auto h-8 w-8 text-slate-400" />
      <h1 className="mt-3 text-lg font-bold">Not available for your role</h1>
      <p className="mt-1 text-sm text-slate-600">
        This service is not part of the <strong>{getRole()}</strong> role. The API enforces the same rule,
        so the page would only show a 403 error.
      </p>
      <Link to="/" className="mt-4 inline-block text-sm font-medium text-green-700 hover:underline">Back to your dashboard</Link>
    </div>
  )
}

/** Client-side permission guard. It mirrors the permission each page's API
 *  requires so users are not dropped onto a 403 — but it is a UX guard only:
 *  the API checks the permission again on every request. */
function Need({ perm, children }: { perm: string; children: React.ReactNode }) {
  return can(perm) ? <>{children}</> : <NotPermitted />
}

/** "/" is a different service for each role. */
function Home() {
  const role = getRole()
  if (role === 'admin') return <Need perm="system.view"><AdminDashboard /></Need>
  if (role === 'researcher') return <Need perm="models.evaluate"><ResearcherDashboard /></Need>
  return <Need perm="patients.monitor"><ClinicianDashboard /></Need>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Protected><Layout /></Protected>}>
          <Route path="/" element={<Home />} />
          <Route path="/patients" element={<Need perm="patients.view"><Patients /></Need>} />
          <Route path="/patients/:pid" element={<Need perm="patients.view"><PatientDetail /></Need>} />
          <Route path="/alerts" element={<Need perm="alerts.view"><Alerts /></Need>} />
          <Route path="/risk" element={<Need perm="risk.view"><RiskMonitoring /></Need>} />
          <Route path="/timeline" element={<Need perm="timeline.view"><TimelinePage /></Need>} />
          <Route path="/simulation" element={<Need perm="simulation.run"><SimulationPage /></Need>} />
          <Route path="/data-quality" element={<Need perm="data_quality.view"><DataQuality /></Need>} />
          <Route path="/explain" element={<Need perm="explainability.view"><Explain /></Need>} />
          <Route path="/models" element={<Need perm="models.evaluate"><Models /></Need>} />
          <Route path="/model-performance" element={<Need perm="models.evaluate"><ModelPerformance /></Need>} />
          <Route path="/trajectories" element={<Need perm="trajectory.view"><TrajectoryAnalysis /></Need>} />
          <Route path="/admin/users" element={<Need perm="users.view"><Users /></Need>} />
          <Route path="/admin/roles" element={<Need perm="roles.view"><Roles /></Need>} />
          <Route path="/admin/audit" element={<Need perm="audit.view"><AuditLogs /></Need>} />
          <Route path="/admin/health" element={<Need perm="system.view"><SystemHealth /></Need>} />
          <Route path="/admin/models" element={<Need perm="models.view"><ModelStatus /></Need>} />
          <Route path="/admin/settings" element={<Need perm="system.view"><SystemSettings /></Need>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
