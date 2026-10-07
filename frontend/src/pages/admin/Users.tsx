import { useState } from 'react'
import { KeyRound, UserPlus, X } from 'lucide-react'
import { api, ApiError, can, getUsername } from '../../api'
import type { Role } from '../../api'
import { Badge, BTN_DANGER, BTN_PRIMARY, BTN_SECONDARY, Card, GREEN, INPUT, NEUTRAL, PageHeader, TH, THEAD } from '../../components/ui'
import { Async, Empty, useApi } from '../../components/states'

interface UserRow { id: number; username: string; role: Role; is_active: boolean; created_at: string | null }
const ROLES: Role[] = ['clinician', 'researcher', 'admin']
type Pending =
  | { kind: 'role'; user: UserRow; role: Role }
  | { kind: 'active'; user: UserRow; is_active: boolean }
  | { kind: 'password'; user: UserRow }

function ConfirmDialog({ pending, onClose, onDone }: { pending: Pending; onClose: () => void; onDone: (msg: string) => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const u = pending.user
  const text = pending.kind === 'role' ? `Change ${u.username}'s role from ${u.role} to ${pending.role}? Their services and permissions change the next time they sign in.`
    : pending.kind === 'active' ? (pending.is_active ? `Reactivate ${u.username}? They will be able to sign in again.`
      : `Deactivate ${u.username}? They are signed out immediately and cannot sign in until reactivated. The account and its audit history are kept.`)
    : `Set a new password for ${u.username}.`

  async function confirm() {
    setBusy(true); setError('')
    const body = pending.kind === 'role' ? { role: pending.role }
      : pending.kind === 'active' ? { is_active: pending.is_active } : { password }
    try {
      await api(`/admin/users/${u.id}`, { method: 'PATCH', body: JSON.stringify(body) })
      onDone(pending.kind === 'role' ? `${u.username} is now ${pending.role}.`
        : pending.kind === 'active' ? `${u.username} ${pending.is_active ? 'reactivated' : 'deactivated'}.`
        : `Password reset for ${u.username}.`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Request failed')
      setBusy(false)
    }
  }
  const destructive = pending.kind === 'active' && !pending.is_active

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true" aria-label="Confirm change">
      <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between">
          <h2 className="text-base font-bold">Confirm change</h2>
          <button onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-700"><X className="h-4 w-4" /></button>
        </div>
        <p className="mt-2 text-sm text-slate-700">{text}</p>
        {pending.kind === 'password' && (
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoFocus
            placeholder="New password (min. 8 characters)" autoComplete="new-password" className={`${INPUT} mt-3 w-full`} />
        )}
        {error && <div className="mt-2 text-sm text-red-600" role="alert">{error}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className={BTN_SECONDARY}>Cancel</button>
          <button onClick={confirm} disabled={busy || (pending.kind === 'password' && password.length < 8)}
            className={destructive ? BTN_DANGER : BTN_PRIMARY}>
            {destructive ? 'Deactivate' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  )
}

function CreateUser({ onCreated }: { onCreated: (msg: string) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('clinician')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      await api('/admin/users', { method: 'POST', body: JSON.stringify({ username, password, role }) })
      onCreated(`User ${username} created as ${role}.`)
      setUsername(''); setPassword('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Request failed')
    } finally { setBusy(false) }
  }

  return (
    <Card title="Create user">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-600"><span className="mb-1 block font-medium">Username</span>
          <input value={username} onChange={e => setUsername(e.target.value)} required minLength={3} maxLength={32}
            pattern="[A-Za-z0-9_.\-]+" autoComplete="off" className={INPUT} /></label>
        <label className="text-xs text-slate-600"><span className="mb-1 block font-medium">Password</span>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8}
            autoComplete="new-password" className={INPUT} /></label>
        <label className="text-xs text-slate-600"><span className="mb-1 block font-medium">Role</span>
          <select value={role} onChange={e => setRole(e.target.value as Role)} className={INPUT}>
            {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
          </select></label>
        <button disabled={busy} className={BTN_PRIMARY}><UserPlus className="h-4 w-4" /> Create user</button>
      </form>
      <div className="mt-2 text-[11px] text-slate-500">3–32 characters (letters, digits, . _ -). Passwords need at least 8 characters and are stored as bcrypt hashes.</div>
      {error && <div className="mt-2 text-sm text-red-600" role="alert">{error}</div>}
    </Card>
  )
}

export default function Users() {
  const state = useApi<{ users: UserRow[] }>('/admin/users')
  const [pending, setPending] = useState<Pending | null>(null)
  const [notice, setNotice] = useState('')
  const me = getUsername()
  const editable = can('users.update')
  const done = (msg: string) => { setNotice(msg); setPending(null); state.reload() }

  return (
    <div className="space-y-4">
      <PageHeader title="Users" subtitle="Create accounts, assign roles, deactivate access. Accounts are never deleted, so the audit trail stays intact." />
      {notice && <div className="rounded-lg border border-green-300 bg-green-50 px-3 py-2 text-sm text-green-800" role="status">{notice}</div>}
      {can('users.create') && <CreateUser onCreated={done} />}
      <Async state={state} what="the user list">{d => d.users.length === 0 ? <Empty>No users.</Empty> : (
        <div className="overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-sm">
            <thead className={THEAD}><tr>{['User', 'Role', 'Status', 'Created', 'Actions'].map(h => <th key={h} className={TH}>{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-200">
              {d.users.map(u => (
                <tr key={u.id} className="hover:bg-slate-50">
                  <td className="px-3 py-2 font-medium">{u.username}{u.username === me && <span className="ml-2 text-[10px] uppercase text-slate-400">you</span>}</td>
                  <td className="px-3 py-2">
                    <select value={u.role} disabled={!editable || u.username === me} aria-label={`Role of ${u.username}`}
                      onChange={e => setPending({ kind: 'role', user: u, role: e.target.value as Role })} className={`${INPUT} py-1`}>
                      {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2"><Badge label={u.is_active ? 'active' : 'deactivated'} palette={{ active: GREEN, deactivated: NEUTRAL }} /></td>
                  <td className="px-3 py-2 text-xs text-slate-600">{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                  <td className="px-3 py-2">
                    {editable && (
                      <div className="flex gap-2">
                        <button onClick={() => setPending({ kind: 'password', user: u })} className={`${BTN_SECONDARY} px-2 py-1 text-xs`}><KeyRound className="h-3 w-3" /> Reset password</button>
                        {u.username !== me && (
                          <button onClick={() => setPending({ kind: 'active', user: u, is_active: !u.is_active })} className={`${BTN_SECONDARY} px-2 py-1 text-xs`}>
                            {u.is_active ? 'Deactivate' : 'Reactivate'}
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}</Async>
      {pending && <ConfirmDialog pending={pending} onClose={() => setPending(null)} onDone={done} />}
    </div>
  )
}
