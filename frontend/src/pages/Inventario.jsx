import { useEffect, useState } from 'react'
import { api, fecha } from '../api'
import { Aviso, Badge, Button, Card, Field, Input, Modal, Select, Tabla } from '../components/ui'

const VACIO = { nombre: '', tipo: 'medicamento', unidad: 'caja', lote: '', caducidad: '', stock: 0, stock_minimo: 5 }

export default function Inventario() {
  const [rows, setRows] = useState([])
  const [form, setForm] = useState(null)
  const [error, setError] = useState('')
  const cargar = () => api('/inventario').then(setRows)
  useEffect(() => { cargar() }, [])

  const ajustar = async (r, cantidad) => {
    setError('')
    try { await api(`/inventario/${r.id}/ajuste`, { method: 'POST', body: { cantidad } }); cargar() } catch (e) { setError(e.message) }
  }
  const guardar = async (e) => {
    e.preventDefault(); setError('')
    const body = { ...form, caducidad: form.caducidad || null, lote: form.lote || null, stock: Number(form.stock), stock_minimo: Number(form.stock_minimo) }
    try {
      if (form.id) await api(`/inventario/${form.id}`, { method: 'PUT', body })
      else await api('/inventario', { method: 'POST', body })
      setForm(null); cargar()
    } catch (err) { setError(err.message) }
  }
  const alertas = rows.filter((r) => r.alerta).length
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Inventario</h1>
          <p className="text-sm text-slate-500">{alertas} alerta(s): caducados, por caducar (30 días) o stock bajo</p>
        </div>
        <Button onClick={() => setForm(VACIO)}>+ Nuevo artículo</Button>
      </div>
      <Aviso>{!form && error}</Aviso>
      <Card>
        <Tabla rows={rows} cols={[
          { k: 'nombre', t: 'Artículo', f: (r) => <button className="font-medium text-teal-700 hover:underline" onClick={() => setForm({ ...r, caducidad: r.caducidad || '', lote: r.lote || '' })}>{r.nombre}</button> },
          { k: 'tipo', t: 'Tipo' },
          { k: 'lote', t: 'Lote' },
          { k: 'caducidad', t: 'Caducidad', f: (r) => fecha(r.caducidad) },
          { k: 'stock', t: 'Stock', r: true, f: (r) => `${r.stock} ${r.unidad}` },
          { k: 'alerta', t: 'Alerta', f: (r) => r.alerta ? <Badge v={r.alerta} /> : <span className="text-xs text-slate-400">OK</span> },
          { k: 'aj', t: 'Ajustar', f: (r) => (
            <span className="flex gap-1">
              <Button variant="secondary" className="!px-2 !py-0.5" aria-label={`Restar 1 a ${r.nombre}`} onClick={() => ajustar(r, -1)}>−</Button>
              <Button variant="secondary" className="!px-2 !py-0.5" aria-label={`Sumar 1 a ${r.nombre}`} onClick={() => ajustar(r, 1)}>+</Button>
            </span>) },
        ]} />
      </Card>
      <Modal open={!!form} title={form?.id ? 'Editar artículo' : 'Nuevo artículo'} onClose={() => setForm(null)}>
        {form && (
          <form className="grid grid-cols-2 gap-3" onSubmit={guardar}>
            <Field label="Nombre" className="col-span-2"><Input required value={form.nombre} onChange={set('nombre')} /></Field>
            <Field label="Tipo"><Select value={form.tipo} onChange={set('tipo')}><option value="medicamento">Medicamento</option><option value="insumo">Insumo</option></Select></Field>
            <Field label="Unidad"><Input value={form.unidad} onChange={set('unidad')} /></Field>
            <Field label="Lote"><Input value={form.lote} onChange={set('lote')} /></Field>
            <Field label="Caducidad"><Input type="date" value={form.caducidad} onChange={set('caducidad')} /></Field>
            <Field label="Stock"><Input type="number" min="0" value={form.stock} onChange={set('stock')} /></Field>
            <Field label="Stock mínimo"><Input type="number" min="0" value={form.stock_minimo} onChange={set('stock_minimo')} /></Field>
            <div className="col-span-2"><Aviso>{error}</Aviso></div>
            <div className="col-span-2 flex justify-end"><Button>Guardar</Button></div>
          </form>
        )}
      </Modal>
    </div>
  )
}
