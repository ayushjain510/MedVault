// Same-origin '/api' by default (dev proxy and the nginx/Docker deployment both
// serve the API under the same host). Set VITE_API_BASE at build time when the
// frontend is hosted separately from the API, e.g. "https://medvault-api.example.com".
const ROOT = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')
const BASE = ROOT ? `${ROOT}/api` : '/api'

export type Role = 'admin' | 'clinician' | 'researcher'

export function getToken() { return localStorage.getItem('token') }
export function getRole() { return localStorage.getItem('role') as Role | null }
export function getUsername() { return localStorage.getItem('username') }

/** Permissions granted to the signed-in role, as issued by the API at login.
 *  They shape navigation and hide controls; the API re-checks every request,
 *  so editing localStorage only produces 403 responses. */
export function getPermissions(): string[] {
  try { return JSON.parse(localStorage.getItem('permissions') ?? '[]') } catch { return [] }
}
export function can(permission: string) { return getPermissions().includes(permission) }

export function logout() {
  for (const k of ['token', 'role', 'username', 'permissions']) localStorage.removeItem(k)
}

/** Records the sign-out in the audit log (best effort), then clears the session. */
export async function signOut() {
  try { await api('/auth/logout', { method: 'POST' }) } catch { /* token may already be invalid */ }
  logout()
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function login(username: string, password: string) {
  const body = new URLSearchParams({ username, password })
  const r = await fetch(`${BASE}/auth/login`, { method: 'POST', body })
  if (!r.ok) {
    throw new ApiError(r.status, r.status === 403
      ? 'This account has been deactivated' : 'Invalid username or password')
  }
  const d = await r.json()
  localStorage.setItem('token', d.access_token)
  localStorage.setItem('role', d.role)
  localStorage.setItem('username', d.username)
  localStorage.setItem('permissions', JSON.stringify(d.permissions ?? []))
  return d
}

function detailOf(body: unknown): string | null {
  const d = (body as { detail?: unknown } | null)?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d.map(e => `${(e.loc ?? []).slice(1).join('.')}: ${e.msg}`).join('; ')
  }
  return null
}

export async function api<T = unknown>(path: string, opts: RequestInit = {}): Promise<T> {
  let r: Response
  try {
    r = await fetch(`${BASE}${path}`, {
      ...opts,
      headers: {
        ...(opts.headers || {}),
        Authorization: `Bearer ${getToken()}`,
        ...(opts.body ? { 'Content-Type': 'application/json' } : {}),
      },
    })
  } catch {
    throw new ApiError(0, 'The MedVault API is not reachable')
  }
  if (r.status === 401) { logout(); window.location.href = '/login'; throw new ApiError(401, 'Unauthorized') }
  if (!r.ok) {
    const body = await r.json().catch(() => null)
    throw new ApiError(r.status, detailOf(body) ?? `API error ${r.status}`)
  }
  return r.json()
}
