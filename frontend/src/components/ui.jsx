import { useEffect } from 'react'

export function Card({ title, actions, children, className = '' }) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold text-slate-800">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

const variantes = {
  primary: 'bg-teal-700 text-white hover:bg-teal-800',
  secondary: 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50',
  danger: 'bg-white text-red-700 border border-red-200 hover:bg-red-50',
  ghost: 'text-teal-700 hover:bg-teal-50',
}

export function Button({ variant = 'primary', className = '', ...p }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:opacity-50 ${variantes[variant]} ${className}`}
      {...p}
    />
  )
}

export function Field({ label, children, className = '' }) {
  return (
    <label className={`block text-sm ${className}`}>
      <span className="mb-1 block font-medium text-slate-600">{label}</span>
      {children}
    </label>
  )
}

const base = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-teal-600 focus:outline-none'
export const Input = (p) => <input className={base} {...p} />
export const Select = (p) => <select className={base} {...p} />
export const Textarea = (p) => <textarea className={base} rows={3} {...p} />

export function Modal({ open, title, onClose, children, wide }) {
  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onClose()
    if (open) window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-16" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title}
        className={`w-full ${wide ? 'max-w-2xl' : 'max-w-md'} rounded-2xl bg-white p-6 shadow-xl`}
        onMouseDown={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button onClick={onClose} aria-label="Cerrar" className="rounded-lg px-2 text-2xl leading-none text-slate-400 hover:text-slate-700">×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

const coloresBadge = {
  programada: 'bg-sky-100 text-sky-800', confirmada: 'bg-teal-100 text-teal-800', completada: 'bg-emerald-100 text-emerald-800',
  cancelada: 'bg-slate-200 text-slate-600', no_asistio: 'bg-amber-100 text-amber-800', caducado: 'bg-red-100 text-red-800',
  por_caducar: 'bg-amber-100 text-amber-800', stock_bajo: 'bg-orange-100 text-orange-800', firmada: 'bg-emerald-100 text-emerald-800',
  borrador: 'bg-amber-100 text-amber-800',
}
export function Badge({ v, children }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${coloresBadge[v] || 'bg-slate-100 text-slate-700'}`}>
      {children || String(v).replace('_', ' ')}
    </span>
  )
}

export function Kpi({ label, value, hint, tone = 'teal' }) {
  const tonos = { teal: 'text-teal-700', amber: 'text-amber-600', red: 'text-red-600', indigo: 'text-indigo-600' }
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${tonos[tone]}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}

export function Aviso({ tipo = 'error', children }) {
  if (!children) return null
  const c = tipo === 'error' ? 'bg-red-50 text-red-800 border-red-200' : 'bg-teal-50 text-teal-800 border-teal-200'
  return <p role="alert" className={`rounded-lg border px-3 py-2 text-sm ${c}`}>{children}</p>
}

export function Tabla({ cols, rows, vacio = 'Sin registros' }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
          <tr>{cols.map((c) => <th key={c.k} className={`px-2 py-2 font-medium ${c.r ? 'text-right' : ''}`}>{c.t}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.length === 0 && <tr><td colSpan={cols.length} className="px-2 py-6 text-center text-slate-400">{vacio}</td></tr>}
          {rows.map((r, i) => (
            <tr key={r.id ?? i} className="hover:bg-slate-50">
              {cols.map((c) => <td key={c.k} className={`px-2 py-2 ${c.r ? 'text-right tabular-nums' : ''}`}>{c.f ? c.f(r) : r[c.k]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
