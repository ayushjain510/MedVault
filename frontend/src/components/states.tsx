import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { AlertTriangle, Inbox, Loader2, Lock, RefreshCw } from 'lucide-react'
import { api, ApiError } from '../api'

/** Fetches `path` and tracks loading / error state. `refreshKey` re-fetches
 *  while keeping the previous data on screen (no flicker during simulation). */
export function useApi<T>(path: string | null, refreshKey: unknown = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(!!path)
  const [nonce, setNonce] = useState(0)

  useEffect(() => { setData(null) }, [path])

  useEffect(() => {
    if (!path) { setLoading(false); return }
    let cancelled = false
    setLoading(true)
    api<T>(path)
      .then(d => { if (!cancelled) { setData(d); setError(null) } })
      .catch(e => { if (!cancelled) setError(e instanceof ApiError ? e : new ApiError(0, String(e))) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [path, refreshKey, nonce])

  const reload = useCallback(() => setNonce(n => n + 1), [])
  return { data, error, loading, reload }
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-4 text-sm text-slate-500" role="status">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  )
}

export function ErrorState({ what, error, onRetry }: { what: string; error: ApiError | null; onRetry?: () => void }) {
  const status = error?.status
  const denied = status === 403
  const message = denied ? `Your role does not have permission to view ${what}.`
    : status === 404 ? `${what[0].toUpperCase()}${what.slice(1)} was not found.`
    : `Unable to load ${what}.`
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-800" role="alert">
      {denied ? <Lock className="h-4 w-4 shrink-0" /> : <AlertTriangle className="h-4 w-4 shrink-0" />}
      <div>
        <div className="font-medium">{message}</div>
        {!denied && error?.message && status !== 404 && <div className="text-xs text-red-700/80">{error.message}</div>}
      </div>
      {onRetry && !denied && (
        <button onClick={onRetry}
          className="ml-auto flex items-center gap-1.5 rounded-md border border-red-300 bg-white px-2.5 py-1 text-xs font-medium text-red-800 hover:bg-red-100">
          <RefreshCw className="h-3 w-3" /> Retry
        </button>
      )}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-2 py-4 text-sm text-slate-500">
      <Inbox className="h-4 w-4" /> {children}
    </div>
  )
}

/** Standard wrapper: loading → error (with retry) → content. One failing
 *  request therefore degrades one card, never the whole page. */
export function Async<T>({ state, what, children }: {
  state: { data: T | null; error: ApiError | null; loading: boolean; reload: () => void }
  what: string
  children: (data: T) => ReactNode
}) {
  if (state.data) return <>{children(state.data)}</>
  if (state.error) return <ErrorState what={what} error={state.error} onRetry={state.reload} />
  return <Loading />
}
