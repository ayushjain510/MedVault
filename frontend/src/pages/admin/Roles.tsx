import { Check, Minus } from 'lucide-react'
import { Card, PageHeader, TH, THEAD } from '../../components/ui'
import { Async, useApi } from '../../components/states'

interface Matrix {
  roles: { role: string; description: string; permissions: string[] }[]
  permissions: ({ key: string; description: string } & Record<string, boolean | string>)[]
}

export default function Roles() {
  const state = useApi<Matrix>('/admin/roles')
  return (
    <div className="space-y-4">
      <PageHeader title="Roles & Permissions"
        subtitle="The live permission map the API enforces. Each endpoint requires exactly one permission; a role without it receives 403." />
      <Async state={state} what="the permission matrix">{d => {
        const groups = [...new Set(d.permissions.map(p => p.key.split('.')[0]))]
        return (
          <>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {d.roles.map(r => (
                <Card key={r.role} title={<span className="capitalize">{r.role}</span>}>
                  <p className="text-sm text-slate-700">{r.description}</p>
                  <div className="mt-2 text-xs text-slate-500">{r.permissions.length} permissions</div>
                </Card>
              ))}
            </div>
            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full text-sm">
                <thead className={THEAD}>
                  <tr>
                    <th className={TH}>Permission</th><th className={TH}>Allows</th>
                    {d.roles.map(r => <th key={r.role} className={`${TH} text-center capitalize`}>{r.role}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {groups.map(g => d.permissions.filter(p => p.key.startsWith(`${g}.`)).map((p, i) => (
                    <tr key={p.key} className={`hover:bg-slate-50 ${i === 0 ? 'border-t-2 border-slate-200' : 'border-t border-slate-100'}`}>
                      <td className="px-3 py-2"><code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{p.key}</code></td>
                      <td className="px-3 py-2 text-xs text-slate-600">{p.description}</td>
                      {d.roles.map(r => (
                        <td key={r.role} className="px-3 py-2 text-center">
                          {p[r.role]
                            ? <Check className="mx-auto h-4 w-4 text-green-700" aria-label="allowed" />
                            : <Minus className="mx-auto h-4 w-4 text-slate-300" aria-label="not allowed" />}
                        </td>
                      ))}
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
            <div className="text-[11px] text-slate-500">
              The mapping is defined once in <code>backend/app/services/permissions.py</code> and is read-only here.
              Assign a different role to a user on the Users page.
            </div>
          </>
        )
      }}</Async>
    </div>
  )
}
