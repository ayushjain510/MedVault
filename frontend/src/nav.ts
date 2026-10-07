import {
  Bell, Brain, Database, FlaskConical, Gauge, HeartPulse, History, LayoutDashboard, LineChart,
  PlayCircle, ScrollText, Server, Settings, ShieldCheck, TrendingUp, Users, Boxes,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { Role } from './api'

export interface NavItem { to: string; label: string; icon: LucideIcon; perm: string }

/** One product, three services. Each role gets its own navigation, ordered by
 *  what that role is there to do. `perm` is the permission the page's API
 *  needs: an item is shown only if the API granted it, and the route guard in
 *  App.tsx uses the same value. */
export const NAV: Record<Role, { service: string; items: NavItem[] }> = {
  clinician: {
    service: 'Patient Monitoring',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, perm: 'patients.monitor' },
      { to: '/patients', label: 'Patients', icon: HeartPulse, perm: 'patients.view' },
      { to: '/alerts', label: 'Alerts', icon: Bell, perm: 'alerts.view' },
      { to: '/risk', label: 'Risk Monitoring', icon: Gauge, perm: 'risk.view' },
      { to: '/timeline', label: 'Clinical Timeline', icon: History, perm: 'timeline.view' },
      { to: '/data-quality', label: 'Data Quality', icon: Database, perm: 'data_quality.view' },
      { to: '/simulation', label: 'Scenario Simulation', icon: PlayCircle, perm: 'simulation.run' },
      { to: '/explain', label: 'AI Explainability', icon: Brain, perm: 'explainability.view' },
    ],
  },
  researcher: {
    service: 'AI / ML Analytics',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, perm: 'models.evaluate' },
      { to: '/patients', label: 'Patients', icon: HeartPulse, perm: 'patients.view' },
      { to: '/models', label: 'Model Lab', icon: FlaskConical, perm: 'models.evaluate' },
      { to: '/model-performance', label: 'Model Performance', icon: LineChart, perm: 'models.evaluate' },
      { to: '/explain', label: 'Explainability', icon: Brain, perm: 'explainability.view' },
      { to: '/trajectories', label: 'Trajectory Analysis', icon: TrendingUp, perm: 'trajectory.view' },
      { to: '/data-quality', label: 'Data Quality', icon: Database, perm: 'data_quality.view' },
      { to: '/simulation', label: 'Scenario Simulation', icon: PlayCircle, perm: 'simulation.run' },
    ],
  },
  admin: {
    service: 'System Management',
    items: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, perm: 'system.view' },
      { to: '/admin/users', label: 'Users', icon: Users, perm: 'users.view' },
      { to: '/admin/roles', label: 'Roles & Permissions', icon: ShieldCheck, perm: 'roles.view' },
      { to: '/admin/audit', label: 'Audit Logs', icon: ScrollText, perm: 'audit.view' },
      { to: '/admin/health', label: 'System Health', icon: Server, perm: 'system.view' },
      { to: '/admin/models', label: 'Model Status', icon: Boxes, perm: 'models.view' },
      { to: '/data-quality', label: 'Data Quality', icon: Database, perm: 'data_quality.view' },
      { to: '/admin/settings', label: 'System Settings', icon: Settings, perm: 'system.view' },
    ],
  },
}
