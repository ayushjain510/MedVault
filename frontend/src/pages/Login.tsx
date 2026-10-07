import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { login } from '../api'
import { Disclaimer } from '../components/ui'

export default function Login() {
  const [username, setUsername] = useState('clinician')
  const [password, setPassword] = useState('clin123')
  const [error, setError] = useState('')
  const nav = useNavigate()

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    try { await login(username, password); nav('/') }
    catch (err) { setError(err instanceof Error ? err.message : 'Invalid username or password') }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-4">
        <div className="flex items-center justify-center gap-2">
          <Activity className="h-8 w-8 text-red-600" />
          <h1 className="text-2xl font-bold">MedVault</h1>
        </div>
        <p className="text-center text-sm text-slate-600">
          Antibiotic Response • Fluid Status • Recovery Intelligence
        </p>
        <form onSubmit={submit} className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-5">
          <input value={username} onChange={e => setUsername(e.target.value)} placeholder="Username"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-green-500 focus:outline-none" />
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Password"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-green-500 focus:outline-none" />
          {error && <div className="text-sm text-red-600" role="alert">{error}</div>}
          <button className="w-full rounded-lg bg-green-700 text-white py-2 text-sm font-semibold hover:bg-green-600">Sign in</button>
          <div className="text-[11px] text-slate-500">
            Demo accounts — each role opens a different service:
          </div>
          <div className="grid grid-cols-3 gap-1.5 text-[11px]">
            {([['clinician', 'clin123', 'Patient monitoring'], ['researcher', 'res123', 'AI / ML analytics'],
              ['admin', 'admin123', 'System management']] as const).map(([u, p, what]) => (
              <button key={u} type="button" onClick={() => { setUsername(u); setPassword(p); setError('') }}
                className={`rounded-lg border px-2 py-1.5 text-left transition hover:border-green-500 ${username === u ? 'border-green-500 bg-green-50' : 'border-slate-300 bg-white'}`}>
                <div className="font-semibold capitalize text-slate-800">{u}</div>
                <div className="text-slate-500">{what}</div>
              </button>
            ))}
          </div>
        </form>
        <Disclaimer />
      </div>
    </div>
  )
}
