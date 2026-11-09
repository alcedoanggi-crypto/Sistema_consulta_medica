import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import esLocale from '@fullcalendar/core/locales/es'
import { api, fechaHora } from '../api'
import { useUsuario } from '../App'
import { Aviso, Badge, Button, Card, Field, Input, Modal, Select } from '../components/ui'

const aLocal = (d) => {
  const x = new Date(d)
  x.setMinutes(x.getMinutes() - x.getTimezoneOffset())
  return x.toISOString().slice(0, 16)
}

export default function Agenda() {
  const { usuario } = useUsuario()
  const cal = useRef(null)
  const [medicos, setMedicos] = useState([])
  const [consultorios, setConsultorios] = useState([])
  const [servicios, setServicios] = useState([])
  const [pacientes, setPacientes] = useState([])
  const [medico, setMedico] = useState('')
  const [nueva, setNueva] = useState(null)
  const [sel, setSel] = useState(null)
  const [espera, setEspera] = useState([])
  const [sugeridos, setSugeridos] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')

  const recargar = () => cal.current?.getApi().refetchEvents()
  const cargarEspera = () => api('/lista-espera').then(setEspera)

  useEffect(() => {
    api('/medicos').then(setMedicos)
    api('/consultorios').then(setConsultorios)
    api('/servicios').then(setServicios)
    api('/pacientes').then(setPacientes)
    cargarEspera()
  }, [])
  useEffect(() => { recargar() }, [medico])

  const eventos = (info, ok, fail) => {
    const q = new URLSearchParams({ inicio: info.startStr, fin: info.endStr })
    if (medico) q.set('medico_id', medico)
    api(`/citas?${q}`).then((rows) => ok(rows.map((c) => ({
      id: c.id, start: c.inicio, end: c.fin,
      title: c.tipo === 'bloqueo' ? `🔒 ${c.motivo || 'Bloqueado'}` : `${c.paciente}${c.servicio ? ' · ' + c.servicio : ''}`,
      backgroundColor: c.color, borderColor: c.color,
      classNames: [c.tipo === 'bloqueo' ? 'bloqueo' : '', c.estado === 'no_asistio' ? 'opacity-50' : ''],
      extendedProps: c,
    })))).catch(fail)
  }

  // Arrastrar / redimensionar: si se encima, PostgreSQL lo rechaza (409) y se revierte
  const mover = async ({ event, revert }) => {
    setError('')
    try {
      await api(`/citas/${event.id}`, { method: 'PATCH', body: { inicio: event.start.toISOString(), fin: event.end.toISOString() } })
      setAviso('Cita reprogramada')
    } catch (e) { revert(); setError(e.message) }
  }

  const abrirNueva = (info) => {
    const m = medico || (usuario.rol === 'medico' ? usuario.id : medicos[0]?.id)
    setNueva({ tipo: 'cita', medico_id: m, paciente_id: '', servicio_id: '', consultorio_id: '',
      inicio: aLocal(info.start), fin: info.allDay ? '' : aLocal(info.end), motivo: '' })
    setError('')
  }

  const guardar = async (e) => {
    e.preventDefault()
    setError('')
    const n = nueva
    try {
      await api('/citas', { method: 'POST', body: {
        tipo: n.tipo, medico_id: Number(n.medico_id), motivo: n.motivo || null,
        paciente_id: n.paciente_id ? Number(n.paciente_id) : null,
        servicio_id: n.servicio_id ? Number(n.servicio_id) : null,
        consultorio_id: n.consultorio_id ? Number(n.consultorio_id) : null,
        inicio: new Date(n.inicio).toISOString(),
        fin: n.fin && (n.tipo === 'bloqueo' || !n.servicio_id) ? new Date(n.fin).toISOString() : null,
      } })
      setNueva(null); setAviso('Guardado'); recargar()
    } catch (err) { setError(err.message) }
  }

  const cambiarEstado = async (estado) => {
    try {
      const r = await api(`/citas/${sel.id}`, { method: 'PATCH', body: { estado } })
      setSel(null); recargar()
      if (r.lista_espera?.length) setSugeridos(r.lista_espera)
      setAviso(`Cita marcada como ${estado.replace('_', ' ')}`)
    } catch (e) { setError(e.message) }
  }

  const set = (k) => (e) => setNueva({ ...nueva, [k]: e.target.value })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Agenda</h1>
          <p className="text-sm text-slate-500">Seleccione un hueco para agendar o bloquear · arrastre una cita para moverla</p>
        </div>
        {usuario.rol !== 'medico' && (
          <Field label="Médico" className="w-64">
            <Select value={medico} onChange={(e) => setMedico(e.target.value)}>
              <option value="">Todos los médicos</option>
              {medicos.map((m) => <option key={m.id} value={m.id}>{m.nombre} · {m.especialidad}</option>)}
            </Select>
          </Field>
        )}
      </div>
      <Aviso>{!nueva && !sel ? error : ''}</Aviso>
      {aviso && <Aviso tipo="ok">{aviso}</Aviso>}

      <div className="grid gap-4 xl:grid-cols-4">
        <Card className="xl:col-span-3">
          <FullCalendar
            ref={cal}
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            locale={esLocale}
            initialView="timeGridWeek"
            headerToolbar={{ left: 'prev,next today', center: 'title', right: 'timeGridDay,timeGridWeek,dayGridMonth' }}
            slotMinTime="07:00:00" slotMaxTime="19:00:00" allDaySlot={false} weekends={false}
            nowIndicator selectable editable selectMirror height="auto" slotDuration="00:30:00"
            events={eventos} select={abrirNueva} eventDrop={mover} eventResize={mover}
            eventClick={({ event }) => { setError(''); setSel(event.extendedProps) }}
          />
        </Card>
        <Card title="Lista de espera">
          {espera.length === 0 && <p className="text-sm text-slate-400">Nadie en espera</p>}
          <ul className="space-y-3">
            {espera.map((e) => (
              <li key={e.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                <p className="font-medium">{e.paciente}</p>
                <p className="text-slate-500">{e.medico || 'Cualquier médico'} · {e.preferencia}</p>
                <p className="text-slate-500">{e.telefono}</p>
                <button className="mt-1 text-xs font-medium text-teal-700 underline"
                  onClick={() => api(`/lista-espera/${e.id}/atender`, { method: 'POST' }).then(cargarEspera)}>Marcar como atendido</button>
              </li>
            ))}
          </ul>
          <AgregarEspera pacientes={pacientes} medicos={medicos} onAdd={cargarEspera} />
        </Card>
      </div>

      <Modal open={!!nueva} title="Nuevo en agenda" onClose={() => setNueva(null)}>
        {nueva && (
          <form onSubmit={guardar} className="space-y-3">
            <div className="flex gap-2" role="radiogroup">
              {['cita', 'bloqueo'].map((t) => (
                <Button key={t} type="button" variant={nueva.tipo === t ? 'primary' : 'secondary'} onClick={() => setNueva({ ...nueva, tipo: t })}>
                  {t === 'cita' ? 'Cita' : 'Bloquear horario'}
                </Button>
              ))}
            </div>
            <Field label="Médico">
              <Select required value={nueva.medico_id} onChange={set('medico_id')} disabled={usuario.rol === 'medico'}>
                {medicos.map((m) => <option key={m.id} value={m.id}>{m.nombre}</option>)}
              </Select>
            </Field>
            {nueva.tipo === 'cita' && <>
              <Field label="Paciente">
                <Select required value={nueva.paciente_id} onChange={set('paciente_id')}>
                  <option value="">Seleccione…</option>
                  {pacientes.map((p) => <option key={p.id} value={p.id}>{p.apellido}, {p.nombre}</option>)}
                </Select>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Servicio">
                  <Select value={nueva.servicio_id} onChange={set('servicio_id')}>
                    <option value="">—</option>
                    {servicios.map((s) => <option key={s.id} value={s.id}>{s.nombre} ({s.duracion_min} min)</option>)}
                  </Select>
                </Field>
                <Field label="Consultorio">
                  <Select value={nueva.consultorio_id} onChange={set('consultorio_id')}>
                    <option value="">—</option>
                    {consultorios.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                  </Select>
                </Field>
              </div>
            </>}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Inicio"><Input type="datetime-local" required value={nueva.inicio} onChange={set('inicio')} /></Field>
              <Field label={nueva.tipo === 'cita' && nueva.servicio_id ? 'Fin (según servicio)' : 'Fin'}>
                <Input type="datetime-local" value={nueva.fin} onChange={set('fin')} disabled={nueva.tipo === 'cita' && !!nueva.servicio_id} required={nueva.tipo === 'bloqueo'} />
              </Field>
            </div>
            <Field label={nueva.tipo === 'cita' ? 'Motivo' : 'Motivo del bloqueo'}><Input value={nueva.motivo} onChange={set('motivo')} /></Field>
            <Aviso>{error}</Aviso>
            <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setNueva(null)}>Cancelar</Button><Button>Guardar</Button></div>
          </form>
        )}
      </Modal>

      <Modal open={!!sel} title={sel?.tipo === 'bloqueo' ? 'Horario bloqueado' : 'Detalle de la cita'} onClose={() => setSel(null)}>
        {sel && (
          <div className="space-y-3 text-sm">
            {sel.tipo === 'cita' ? <>
              <p className="text-lg font-semibold"><Link className="text-teal-700 hover:underline" to={`/pacientes/${sel.paciente_id}`}>{sel.paciente}</Link></p>
              <p>{fechaHora(sel.inicio)} · {sel.medico} · {sel.consultorio || 'sin consultorio'}</p>
              <p>{sel.servicio || 'Sin servicio'} {sel.motivo && `· ${sel.motivo}`}</p>
              <p className="flex gap-2"><Badge v={sel.estado} /> {sel.origen === 'en_linea' && <Badge v="x">reservada en línea</Badge>}</p>
              <Aviso>{error}</Aviso>
              <div className="flex flex-wrap gap-2 pt-2">
                <Button onClick={() => cambiarEstado('completada')}>Atendida</Button>
                <Button variant="secondary" onClick={() => cambiarEstado('confirmada')}>Confirmada</Button>
                <Button variant="secondary" onClick={() => cambiarEstado('no_asistio')}>No asistió</Button>
                <Button variant="danger" onClick={() => cambiarEstado('cancelada')}>Cancelar cita</Button>
              </div>
            </> : <>
              <p>{fechaHora(sel.inicio)} – {fechaHora(sel.fin)} · {sel.medico}</p>
              <p>{sel.motivo}</p>
              <Button variant="danger" onClick={() => api(`/citas/${sel.id}`, { method: 'DELETE' }).then(() => { setSel(null); recargar() })}>Quitar bloqueo</Button>
            </>}
          </div>
        )}
      </Modal>

      <Modal open={!!sugeridos} title="Horario liberado" onClose={() => setSugeridos(null)}>
        <p className="mb-3 text-sm text-slate-600">Estos pacientes de la lista de espera podrían ocupar el espacio:</p>
        <ul className="space-y-2 text-sm">
          {sugeridos?.map((s) => <li key={s.id} className="rounded-lg bg-slate-50 p-2"><b>{s.paciente}</b> · {s.telefono} · {s.preferencia}</li>)}
        </ul>
      </Modal>
    </div>
  )
}

function AgregarEspera({ pacientes, medicos, onAdd }) {
  const [f, setF] = useState(null)
  if (!f) return <Button variant="ghost" className="mt-3 w-full" onClick={() => setF({ paciente_id: '', medico_id: '', preferencia: '' })}>+ Agregar a la lista</Button>
  return (
    <form className="mt-3 space-y-2" onSubmit={async (e) => {
      e.preventDefault()
      await api('/lista-espera', { method: 'POST', body: { paciente_id: Number(f.paciente_id), medico_id: f.medico_id ? Number(f.medico_id) : null, preferencia: f.preferencia } })
      setF(null); onAdd()
    }}>
      <Select required aria-label="Paciente" value={f.paciente_id} onChange={(e) => setF({ ...f, paciente_id: e.target.value })}>
        <option value="">Paciente…</option>
        {pacientes.map((p) => <option key={p.id} value={p.id}>{p.apellido}, {p.nombre}</option>)}
      </Select>
      <Select aria-label="Médico" value={f.medico_id} onChange={(e) => setF({ ...f, medico_id: e.target.value })}>
        <option value="">Cualquier médico</option>
        {medicos.map((m) => <option key={m.id} value={m.id}>{m.nombre}</option>)}
      </Select>
      <Input aria-label="Preferencia" placeholder="Preferencia de horario" value={f.preferencia} onChange={(e) => setF({ ...f, preferencia: e.target.value })} />
      <div className="flex gap-2"><Button className="flex-1">Agregar</Button><Button type="button" variant="secondary" onClick={() => setF(null)}>×</Button></div>
    </form>
  )
}
