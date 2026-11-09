import { useEffect, useState } from 'react'
import { abrirArchivo, api, fecha, fechaHora, hora } from '../api'
import { Aviso, Badge, Button, Card, Field, Input, Select } from '../components/ui'

const manana = () => { const d = new Date(); d.setDate(d.getDate() + 1); return d.toLocaleDateString('en-CA') }

export default function Portal() {
  const [medicos, setMedicos] = useState([])
  const [servicios, setServicios] = useState([])
  const [f, setF] = useState({ medico_id: '', servicio_id: '', fecha: manana() })
  const [slots, setSlots] = useState([])
  const [citas, setCitas] = useState([])
  const [recetas, setRecetas] = useState([])
  const [msg, setMsg] = useState({})

  const cargarMias = () => { api('/portal/citas').then(setCitas); api('/portal/recetas').then(setRecetas) }
  useEffect(() => { api('/medicos').then(setMedicos); api('/servicios').then(setServicios); cargarMias() }, [])

  // Disponibilidad en tiempo real: se consulta al cambiar filtros y cada 15 s
  useEffect(() => {
    if (!f.medico_id || !f.servicio_id) return setSlots([])
    const cargar = () => api(`/disponibilidad?medico_id=${f.medico_id}&fecha=${f.fecha}&servicio_id=${f.servicio_id}`).then(setSlots)
    cargar()
    const t = setInterval(cargar, 15000)
    return () => clearInterval(t)
  }, [f])

  const reservar = async (s) => {
    setMsg({})
    try {
      await api('/portal/citas', { method: 'POST', body: { medico_id: Number(f.medico_id), servicio_id: Number(f.servicio_id), inicio: s.inicio } })
      setMsg({ ok: `¡Listo! Cita reservada para el ${fechaHora(s.inicio)}. Te enviaremos un recordatorio por correo.` })
      cargarMias()
    } catch (e) { setMsg({ error: e.message }) }
    setF({ ...f })
  }

  const serviciosMedico = servicios.filter((s) => {
    const m = medicos.find((x) => x.id === Number(f.medico_id))
    if (!m) return true
    if (m.especialidad === 'Odontología') return /dental/i.test(s.nombre)
    if (/Psicolog/.test(m.especialidad)) return /psicolog/i.test(s.nombre)
    return !/dental|psicolog/i.test(s.nombre)
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Reservar una cita</h1>
      <Card>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Especialista">
            <Select value={f.medico_id} onChange={(e) => setF({ ...f, medico_id: e.target.value, servicio_id: '' })}>
              <option value="">Seleccione…</option>
              {medicos.map((m) => <option key={m.id} value={m.id}>{m.nombre} · {m.especialidad}</option>)}
            </Select>
          </Field>
          <Field label="Servicio">
            <Select value={f.servicio_id} onChange={(e) => setF({ ...f, servicio_id: e.target.value })} disabled={!f.medico_id}>
              <option value="">Seleccione…</option>
              {serviciosMedico.map((s) => <option key={s.id} value={s.id}>{s.nombre} ({s.duracion_min} min)</option>)}
            </Select>
          </Field>
          <Field label="Fecha"><Input type="date" min={new Date().toLocaleDateString('en-CA')} value={f.fecha} onChange={(e) => setF({ ...f, fecha: e.target.value })} /></Field>
        </div>
        <div className="mt-5">
          {f.medico_id && f.servicio_id ? (
            slots.length ? (
              <>
                <p className="mb-2 text-sm text-slate-500">Horarios disponibles (se actualizan en tiempo real):</p>
                <div className="flex flex-wrap gap-2">
                  {slots.map((s) => <Button key={s.inicio} variant="secondary" onClick={() => reservar(s)}>{hora(s.inicio)}</Button>)}
                </div>
              </>
            ) : <p className="text-sm text-slate-500">No hay horarios libres ese día. Pruebe otra fecha.</p>
          ) : <p className="text-sm text-slate-400">Elija especialista y servicio para ver horarios.</p>}
        </div>
        <div className="mt-4"><Aviso>{msg.error}</Aviso>{msg.ok && <Aviso tipo="ok">{msg.ok}</Aviso>}</div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Mis citas" className="lg:col-span-2">
          <ul className="divide-y divide-slate-100">
            {citas.length === 0 && <li className="py-4 text-sm text-slate-400">Aún no tienes citas.</li>}
            {citas.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                <div>
                  <p className="font-medium">{fechaHora(c.inicio)} · {c.servicio}</p>
                  <p className="text-slate-500">{c.medico} · {c.especialidad}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge v={c.estado} />
                  {['programada', 'confirmada'].includes(c.estado) && new Date(c.inicio) > new Date() && (
                    <Button variant="danger" className="!py-1" onClick={() => api(`/portal/citas/${c.id}/cancelar`, { method: 'POST' }).then(cargarMias)}>Cancelar</Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Mis recetas">
          {recetas.length === 0 && <p className="text-sm text-slate-400">Sin recetas.</p>}
          <ul className="space-y-2 text-sm">
            {recetas.map((r) => (
              <li key={r.id} className="flex items-center justify-between rounded-lg border border-slate-200 p-3">
                <span>{fecha(r.creado)} · {r.medico}</span>
                <button className="text-teal-700 underline" onClick={() => abrirArchivo(`/recetas/${r.id}/pdf`)}>PDF</button>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  )
}
