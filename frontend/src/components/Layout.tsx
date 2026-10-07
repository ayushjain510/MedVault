import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Activity, LogOut } from 'lucide-react'
import { can, getRole, getUsername, signOut } from '../api'
import { NAV } from '../nav'
import { Disclaimer } from './ui'

export default function Layout() {
  const nav = useNavigate()
  const role = getRole() ?? 'clinician'
  const { service, items } = NAV[role] ?? NAV.clinician
  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 flex w-56 flex-col border-r border-slate-200 bg-white p-4">
        <div className="mb-4 flex items-center gap-2">
          <Activity className="h-6 w-6 text-red-600" />
          <div>
            <div className="text-base font-bold text-slate-900">MedVault</div>
            <div className="text-[10px] text-slate-500">Response · Fluid · Recovery</div>
          </div>
        </div>
        <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">{service}</div>
        <nav className="flex-1 space-y-1 overflow-y-auto" aria-label={`${service} navigation`}>
          {items.filter(l => can(l.perm)).map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
                  isActive ? 'bg-green-700 text-white font-medium' : 'text-slate-700 hover:bg-green-50 hover:text-green-800'}`}>
              <Icon className="h-4 w-4" /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-3">
          <div className="text-xs text-slate-500">
            Signed in as <span className="text-slate-700">{getUsername()}</span>
            <span className="ml-1 rounded bg-green-100 px-1.5 py-0.5 text-[10px] uppercase text-green-800">{role}</span>
          </div>
          <button onClick={async () => { await signOut(); nav('/login') }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-800">
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      </aside>
      <main className="ml-56 min-w-0 flex-1 space-y-4 p-6">
        <Disclaimer />
        <Outlet />
      </main>
    </div>
  )
}
