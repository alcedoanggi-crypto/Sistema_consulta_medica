import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { abrirArchivo, api, dinero, fecha, fechaHora } from '../api'
import { useUsuario } from '../App'
import { Aviso, Badge, Button, Card, Field, Input, Modal, Select, Tabla, Textarea } from '../components/ui'

export function FormPaciente({ inicial = {}, onGuardar }) {
  const [f, setF] = useState({ nombre: '', apellido: '', fecha_nacimiento: '', sexo: '', email: '', telefono: '', direccion: '',
    documento: '', emergencia_nombre: '', emergencia_telefono: '', ...inicial })
  const [error, setError] = useState('')
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={async (e) => {
      e.preventDefault(); setError('')
      try { await onGuardar({ ...f, fecha_nacimiento: f.fecha_nacimiento || null, sexo: f.sexo || null }) } catch (err) { setError(err.message) }
    }}>
      <Field label="Nombre"><Input required value={f.nombre} onChange={set('nombre')} /></Field>
      <Field label="Apellido"><Input required value={f.apellido} onChange={set('apellido')} /></Field>
      <Field label="Documento de identidad 🔒"><Input value={f.documento || ''} onChange={set('documento')} /></Field>
      <Field label="Fecha de nacimiento"><Input type="date" value={f.fecha_nacimiento || ''} onChange={set('fecha_nacimiento')} /></Field>
      <Field label="Sexo"><Select value={f.sexo || ''} onChange={set('sexo')}><option value="">—</option><option value="F">Femenino</option><option value="M">Masculino</option><option value="O">Otro</option></Select></Field>
      <Field label="Teléfono"><Input value={f.telefono || ''} onChange={set('telefono')} /></Field>
      <Field label="Correo" className="sm:col-span-2"><Input type="email" value={f.email || ''} onChange={set('email')} /></Field>
      <Field label="Dirección" className="sm:col-span-2"><Input value={f.direccion || ''} onChange={set('direccion')} /></Field>
      <Field label="Contacto de emergencia"><Input value={f.emergencia_nombre || ''} onChange={set('emergencia_nombre')} /></Field>
      <Field label="Teléfono de emergencia"><Input value={f.emergencia_telefono || ''} onChange={set('emergencia_telefono')} /></Field>
      <div className="sm:col-span-2"><Aviso>{error}</Aviso></div>
      <div className="flex justify-end sm:col-span-2"><Button>Guardar</Button></div>
    </form>
  )
}

export default function Paciente() {
  const { id } = useParams()
  const { usuario } = useUsuario()
  const clinico = ['admin', 'medico'].includes(usuario.rol)
  const [p, setP] = useState(null)
  const [tab, setTab] = useState(clinico ? 'expediente' : 'datos')
  const [editar, setEditar] = useState(false)
  const cargar = () => api(`/pacientes/${id}`).then(setP)
  useEffect(() => { cargar() }, [id])
  if (!p) return <p className="text-slate-500">Cargando…</p>

  const tabs = [clinico && ['expediente', 'Expediente clínico'], ['datos', 'Datos generales'], ['archivos', 'Archivos'],
    usuario.rol !== 'medico' && ['cuenta', 'Cuenta y pagos']].filter(Boolean)
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">{p.nombre} {p.apellido}</h1>
        <p className="text-sm text-slate-500">{p.documento || 'Sin documento'} · {p.telefono || 'sin teléfono'} · nac. {fecha(p.fecha_nacimiento)}</p>
      </div>
      <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {tabs.map(([k, t]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium ${tab === k ? 'border-teal-700 text-teal-800' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>{t}</button>
        ))}
      </div>
      {!clinico && <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">🔒 Como recepción no tiene acceso al contenido clínico de este paciente.</p>}

      {tab === 'datos' && (
        <Card title="Datos generales" actions={<Button variant="secondary" onClick={() => setEditar(true)}>Editar</Button>}>
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
            {[['Correo', p.email], ['Teléfono', p.telefono], ['Dirección', p.direccion], ['Documento', p.documento], ['Sexo', p.sexo],
              ['Contacto de emergencia', `${p.emergencia_nombre || '—'} · ${p.emergencia_telefono || ''}`], ['Registrado', fecha(p.creado)]].map(([k, v]) => (
              <div key={k}><dt className="text-slate-500">{k}</dt><dd className="font-medium">{v || '—'}</dd></div>
            ))}
          </dl>
          <Modal open={editar} title="Editar paciente" wide onClose={() => setEditar(false)}>
            <FormPaciente inicial={p} onGuardar={async (d) => { await api(`/pacientes/${id}`, { method: 'PUT', body: d }); setEditar(false); cargar() }} />
          </Modal>
        </Card>
      )}
      {tab === 'expediente' && clinico && <Expediente pid={Number(id)} />}
      {tab === 'archivos' && <Archivos pid={id} clinico={clinico} />}
      {tab === 'cuenta' && <Cuenta pid={Number(id)} />}
    </div>
  )
}

function Expediente({ pid }) {
  const { usuario } = useUsuario()
  const esMedico = usuario.rol === 'medico'
  const [e, setE] = useState(null)
  const [nota, setNota] = useState(null)
  const [modal, setModal] = useState(null)
  const [error, setError] = useState('')
  const cargar = () => api(`/pacientes/${pid}/expediente`).then(setE)
  useEffect(() => { cargar() }, [pid])
  if (!e) return <p className="text-slate-500">Cargando expediente…</p>

  const signos = e.signos.map((s) => ({ ...s, f: fecha(s.fecha), peso_kg: Number(s.peso_kg) }))
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Card title="Notas de consulta (SOAP)" actions={esMedico && <Button onClick={() => setNota({ subjetivo: '', objetivo: '', evaluacion: '', plan: '', diagnosticos: [] })}>+ Nueva nota</Button>}>
          {e.notas.length === 0 && <p className="text-sm text-slate-400">Sin notas.</p>}
          <ol className="space-y-4">
            {e.notas.map((n) => (
              <li key={n.id} className="rounded-xl border border-slate-200 p-4">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium">{fechaHora(n.creado)} · Dr(a). {n.medico}</p>
                  {n.firmada ? <Badge v="firmada">✔ Firmada {fechaHora(n.firmada_en)}</Badge> : <Badge v="borrador">Borrador</Badge>}
                </div>
                <dl className="grid gap-2 text-sm sm:grid-cols-2">
                  {[['S · Subjetivo', n.subjetivo], ['O · Objetivo', n.objetivo], ['A · Evaluación', n.evaluacion], ['P · Plan', n.plan]].map(([k, v]) => (
                    <div key={k}><dt className="text-xs font-semibold text-teal-800">{k}</dt><dd className="whitespace-pre-line">{v || '—'}</dd></div>
                  ))}
                </dl>
                {n.diagnosticos.length > 0 && (
                  <p className="mt-2 flex flex-wrap gap-1">{n.diagnosticos.map((d) => <Badge key={d.codigo} v="x">{d.codigo} · {d.descripcion}</Badge>)}</p>
                )}
                {n.adendas.map((a) => (
                  <div key={a.id} className="mt-3 border-l-4 border-indigo-300 bg-indigo-50 px-3 py-2 text-sm">
                    <p className="text-xs font-semibold text-indigo-800">Adenda · {fechaHora(a.creado)} · {a.autor}</p>
                    <p>{a.texto}</p>
                  </div>
                ))}
                {esMedico && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {!n.firmada && n.medico_id === usuario.id && <>
                      <Button variant="secondary" onClick={() => setNota({ ...n, diagnosticos: n.diagnosticos.map((d) => d.codigo) })}>Editar borrador</Button>
                      <Button onClick={() => api(`/notas/${n.id}/firmar`, { method: 'POST' }).then(cargar)}>Firmar</Button>
                    </>}
                    {n.firmada && <Button variant="ghost" onClick={() => setModal({ tipo: 'adenda', nota: n.id, texto: '' })}>+ Agregar adenda</Button>}
                    <Button variant="ghost" onClick={() => setModal({ tipo: 'receta', nota: n.id, texto: '' })}>Emitir receta</Button>
                  </div>
                )}
              </li>
            ))}
          </ol>
        </Card>

        <Card title="Evolución de signos vitales" actions={<Button variant="secondary" onClick={() => setModal({ tipo: 'signos' })}>+ Registrar</Button>}>
          {signos.length === 0 ? <p className="text-sm text-slate-400">Sin registros.</p> : (
            <div className="grid gap-4 md:grid-cols-2">
              <Grafica titulo="Presión arterial (mmHg)" data={signos} lineas={[['presion_sis', 'Sistólica', '#e11d48'], ['presion_dia', 'Diastólica', '#6366f1']]} />
              <Grafica titulo="Peso (kg) y frecuencia cardíaca" data={signos} lineas={[['peso_kg', 'Peso', '#0d9488'], ['frec_cardiaca', 'FC', '#f59e0b']]} />
            </div>
          )}
        </Card>
      </div>

      <div className="space-y-4">
        <Antecedentes pid={pid} p={e.paciente} onSave={cargar} />
        <Card title="Recetas">
          {e.recetas.length === 0 && <p className="text-sm text-slate-400">Sin recetas.</p>}
          <ul className="space-y-2 text-sm">
            {e.recetas.map((r) => (
              <li key={r.id} className="rounded-lg border border-slate-200 p-3">
                <p className="font-medium">{fecha(r.creado)} · {r.medico}</p>
                <p className="line-clamp-2 whitespace-pre-line text-slate-600">{r.medicamentos}</p>
                <button className="mt-1 text-xs font-medium text-teal-700 underline" onClick={() => abrirArchivo(`/recetas/${r.id}/pdf`)}>Ver PDF con QR</button>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Modal open={!!nota} title={nota?.id ? 'Editar borrador' : 'Nueva nota SOAP'} wide onClose={() => setNota(null)}>
        {nota && <FormNota pid={pid} nota={nota} onDone={() => { setNota(null); cargar() }} />}
      </Modal>

      <Modal open={modal?.tipo === 'adenda' || modal?.tipo === 'receta'} title={modal?.tipo === 'adenda' ? 'Adenda a nota firmada' : 'Nueva receta'} onClose={() => setModal(null)}>
        {modal && (
          <form className="space-y-3" onSubmit={async (ev) => {
            ev.preventDefault(); setError('')
            try {
              if (modal.tipo === 'adenda') await api(`/notas/${modal.nota}/adendas`, { method: 'POST', body: { texto: modal.texto } })
              else {
                const r = await api('/recetas', { method: 'POST', body: { paciente_id: pid, nota_id: modal.nota, medicamentos: modal.texto } })
                abrirArchivo(`/recetas/${r.id}/pdf`)
              }
              setModal(null); cargar()
            } catch (err) { setError(err.message) }
          }}>
            {modal.tipo === 'adenda' && <p className="text-sm text-slate-500">La nota original no se modifica; la adenda queda registrada con fecha y autor.</p>}
            <Field label={modal.tipo === 'adenda' ? 'Texto de la adenda' : 'Medicamentos e indicaciones'}>
              <Textarea rows={6} required value={modal.texto} onChange={(ev) => setModal({ ...modal, texto: ev.target.value })}
                placeholder={modal.tipo === 'receta' ? 'Amoxicilina 500 mg\n1 cápsula cada 8 horas por 7 días' : ''} />
            </Field>
            <Aviso>{error}</Aviso>
            <div className="flex justify-end"><Button>{modal.tipo === 'adenda' ? 'Agregar adenda' : 'Generar PDF'}</Button></div>
          </form>
        )}
      </Modal>

      <Modal open={modal?.tipo === 'signos'} title="Registrar signos vitales" onClose={() => setModal(null)}>
        <FormSignos pid={pid} onDone={() => { setModal(null); cargar() }} />
      </Modal>
    </div>
  )
}

function Grafica({ titulo, data, lineas }) {
  return (
    <figure>
      <figcaption className="mb-2 text-sm font-medium text-slate-600">{titulo}</figcaption>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data}>
          <CartesianGrid stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="f" fontSize={11} />
          <YAxis fontSize={11} domain={['auto', 'auto']} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {lineas.map(([k, n, c]) => <Line key={k} dataKey={k} name={n} stroke={c} strokeWidth={2} dot={{ r: 3 }} connectNulls />)}
        </LineChart>
      </ResponsiveContainer>
    </figure>
  )
}

function Antecedentes({ pid, p, onSave }) {
  const [f, setF] = useState(null)
  return (
    <Card title="Alergias y antecedentes 🔒" actions={!f && <Button variant="ghost" onClick={() => setF({ alergias: p.alergias || '', antecedentes: p.antecedentes || '' })}>Editar</Button>}>
      {!f ? (
        <dl className="space-y-2 text-sm">
          <div><dt className="text-slate-500">Alergias</dt><dd className={`font-medium ${p.alergias && !/ninguna/i.test(p.alergias) ? 'text-red-700' : ''}`}>{p.alergias || '—'}</dd></div>
          <div><dt className="text-slate-500">Antecedentes</dt><dd className="whitespace-pre-line">{p.antecedentes || '—'}</dd></div>
        </dl>
      ) : (
        <form className="space-y-3" onSubmit={async (e) => { e.preventDefault(); await api(`/pacientes/${pid}/antecedentes`, { method: 'PUT', body: f }); setF(null); onSave() }}>
          <Field label="Alergias"><Input value={f.alergias} onChange={(e) => setF({ ...f, alergias: e.target.value })} /></Field>
          <Field label="Antecedentes"><Textarea value={f.antecedentes} onChange={(e) => setF({ ...f, antecedentes: e.target.value })} /></Field>
          <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setF(null)}>Cancelar</Button><Button>Guardar</Button></div>
        </form>
      )}
    </Card>
  )
}

function FormNota({ pid, nota, onDone }) {
  const [f, setF] = useState(nota)
  const [q, setQ] = useState('')
  const [opciones, setOpciones] = useState([])
  const [error, setError] = useState('')
  useEffect(() => {
    if (!q) return setOpciones([])
    const t = setTimeout(() => api(`/cie10?q=${encodeURIComponent(q)}`).then(setOpciones), 200)
    return () => clearTimeout(t)
  }, [q])
  const guardar = async (firmar) => {
    setError('')
    const body = { paciente_id: pid, subjetivo: f.subjetivo || '', objetivo: f.objetivo || '', evaluacion: f.evaluacion || '', plan: f.plan || '', diagnosticos: f.diagnosticos, firmar }
    try {
      if (f.id) await api(`/notas/${f.id}`, { method: 'PUT', body })
      else await api('/notas', { method: 'POST', body })
      onDone()
    } catch (e) { setError(e.message) }
  }
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {[['subjetivo', 'S · Subjetivo (lo que refiere el paciente)'], ['objetivo', 'O · Objetivo (exploración)'], ['evaluacion', 'A · Evaluación'], ['plan', 'P · Plan']].map(([k, t]) => (
          <Field key={k} label={t}><Textarea value={f[k] || ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>
        ))}
      </div>
      <Field label="Diagnósticos CIE-10">
        <Input placeholder="Buscar código o descripción (ej. I10, migraña)…" value={q} onChange={(e) => setQ(e.target.value)} />
      </Field>
      {opciones.length > 0 && (
        <ul className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 text-sm">
          {opciones.map((o) => (
            <li key={o.codigo}><button type="button" className="w-full px-3 py-1.5 text-left hover:bg-teal-50"
              onClick={() => { if (!f.diagnosticos.includes(o.codigo)) setF({ ...f, diagnosticos: [...f.diagnosticos, o.codigo] }); setQ('') }}>
              <b>{o.codigo}</b> · {o.descripcion}</button></li>
          ))}
        </ul>
      )}
      <p className="flex flex-wrap gap-1">{f.diagnosticos.map((d, i) => (
        <button key={d} type="button" onClick={() => setF({ ...f, diagnosticos: f.diagnosticos.filter((x) => x !== d) })}
          className="rounded-full bg-teal-100 px-2 py-0.5 text-xs text-teal-800 hover:bg-red-100" aria-label={`Quitar ${d}`}>{d}{i === 0 ? ' (principal)' : ''} ×</button>
      ))}</p>
      <Aviso>{error}</Aviso>
      <p className="text-xs text-slate-500">Al firmar, la nota queda sellada: PostgreSQL impide editarla o borrarla; solo se podrán agregar adendas.</p>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={() => guardar(false)}>Guardar borrador</Button>
        <Button onClick={() => guardar(true)}>Guardar y firmar</Button>
      </div>
    </div>
  )
}

function FormSignos({ pid, onDone }) {
  const [f, setF] = useState({})
  const [error, setError] = useState('')
  const campos = [['peso_kg', 'Peso (kg)'], ['talla_cm', 'Talla (cm)'], ['presion_sis', 'Presión sistólica'], ['presion_dia', 'Presión diastólica'],
    ['frec_cardiaca', 'Frec. cardíaca'], ['temperatura', 'Temperatura (°C)'], ['spo2', 'SpO₂ (%)']]
  return (
    <form className="grid grid-cols-2 gap-3" onSubmit={async (e) => {
      e.preventDefault(); setError('')
      const body = { paciente_id: pid }
      campos.forEach(([k]) => { if (f[k]) body[k] = Number(f[k]) })
      try { await api('/signos', { method: 'POST', body }); onDone() } catch (err) { setError(err.message) }
    }}>
      {campos.map(([k, t]) => <Field key={k} label={t}><Input type="number" step="any" value={f[k] || ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>)}
      <div className="col-span-2"><Aviso>{error}</Aviso></div>
      <div className="col-span-2 flex justify-end"><Button>Guardar</Button></div>
    </form>
  )
}

function Archivos({ pid, clinico }) {
  const [rows, setRows] = useState([])
  const [categoria, setCategoria] = useState('documento')
  const [error, setError] = useState('')
  const cargar = () => api(`/pacientes/${pid}/archivos`).then(setRows)
  useEffect(() => { cargar() }, [pid])
  const subir = async (e) => {
    const archivo = e.target.files[0]
    if (!archivo) return
    const form = new FormData()
    form.append('categoria', categoria)
    form.append('archivo', archivo)
    setError('')
    try { await api(`/pacientes/${pid}/archivos`, { method: 'POST', form }); cargar() } catch (err) { setError(err.message) }
    e.target.value = ''
  }
  return (
    <Card title="Archivos adjuntos" actions={
      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label="Categoría" value={categoria} onChange={(e) => setCategoria(e.target.value)}>
          <option value="documento">Documento administrativo</option>
          {clinico && <option value="estudio">Estudio clínico (lab, radiografía)</option>}
        </Select>
        <label className="cursor-pointer rounded-lg bg-teal-700 px-3.5 py-2 text-sm font-medium text-white hover:bg-teal-800">
          Subir archivo<input type="file" className="sr-only" onChange={subir} />
        </label>
      </div>}>
      <Aviso>{error}</Aviso>
      <Tabla rows={rows} vacio="Sin archivos" cols={[
        { k: 'nombre_original', t: 'Archivo', f: (r) => <button className="text-teal-700 hover:underline" onClick={() => abrirArchivo(`/archivos/${r.id}`)}>{r.nombre_original}</button> },
        { k: 'categoria', t: 'Categoría', f: (r) => <Badge v={r.categoria === 'estudio' ? 'confirmada' : 'x'}>{r.categoria}</Badge> },
        { k: 'subido_por', t: 'Subido por' },
        { k: 'creado', t: 'Fecha', f: (r) => fecha(r.creado) },
      ]} />
    </Card>
  )
}

function Cuenta({ pid }) {
  const [c, setC] = useState(null)
  const [servicios, setServicios] = useState([])
  const [pago, setPago] = useState(null)
  const [error, setError] = useState('')
  const cargar = () => api(`/pacientes/${pid}/cuenta`).then(setC)
  useEffect(() => { cargar(); api('/servicios').then(setServicios) }, [pid])
  if (!c) return null
  const accion = async (ruta, body) => {
    setError('')
    try { await api(ruta, { method: 'POST', body }); setPago(null); cargar() } catch (e) { setError(e.message) }
  }
  return (
    <Card title={`Saldo pendiente: ${dinero(c.saldo.saldo)}`} actions={
      <div className="flex gap-2">
        <Button variant="secondary" onClick={() => setPago({ tipo: 'cargo', servicio_id: '', monto: '' })}>+ Cargo</Button>
        <Button onClick={() => setPago({ tipo: 'pago', monto: c.saldo.saldo > 0 ? c.saldo.saldo : '', metodo: 'efectivo', referencia: '' })}>Registrar pago</Button>
      </div>}>
      <Aviso>{error}</Aviso>
      <Tabla rows={c.movimientos} vacio="Sin movimientos" cols={[
        { k: 'creado', t: 'Fecha', f: (r) => fechaHora(r.creado) },
        { k: 'descripcion', t: 'Concepto' },
        { k: 'tipo', t: 'Tipo', f: (r) => <Badge v={r.tipo === 'pago' ? 'completada' : 'programada'}>{r.tipo}</Badge> },
        { k: 'monto', t: 'Monto', r: true, f: (r) => <span className={r.tipo === 'pago' ? 'text-emerald-700' : ''}>{r.tipo === 'pago' ? '−' : ''}{dinero(r.monto)}</span> },
      ]} />
      <Modal open={!!pago} title={pago?.tipo === 'pago' ? 'Registrar pago' : 'Agregar cargo'} onClose={() => setPago(null)}>
        {pago && (
          <form className="space-y-3" onSubmit={(e) => {
            e.preventDefault()
            if (pago.tipo === 'pago') accion('/pagos', { paciente_id: pid, monto: Number(pago.monto), metodo: pago.metodo, referencia: pago.referencia || null })
            else {
              const s = servicios.find((x) => x.id === Number(pago.servicio_id))
              accion('/cargos', { paciente_id: pid, servicio_id: s.id, descripcion: s.nombre, monto: Number(pago.monto || s.precio) })
            }
          }}>
            {pago.tipo === 'cargo' ? (
              <Field label="Servicio">
                <Select required value={pago.servicio_id} onChange={(e) => {
                  const s = servicios.find((x) => x.id === Number(e.target.value))
                  setPago({ ...pago, servicio_id: e.target.value, monto: s?.precio || '' })
                }}>
                  <option value="">Seleccione…</option>
                  {servicios.map((s) => <option key={s.id} value={s.id}>{s.nombre} · {dinero(s.precio)}</option>)}
                </Select>
              </Field>
            ) : (
              <Field label="Método">
                <Select value={pago.metodo} onChange={(e) => setPago({ ...pago, metodo: e.target.value })}>
                  <option value="efectivo">Efectivo</option><option value="tarjeta">Tarjeta</option><option value="transferencia">Transferencia</option>
                </Select>
              </Field>
            )}
            <Field label="Monto"><Input type="number" min="0.01" step="0.01" required value={pago.monto} onChange={(e) => setPago({ ...pago, monto: e.target.value })} /></Field>
            {pago.tipo === 'pago' && pago.metodo !== 'efectivo' && <Field label="Referencia"><Input value={pago.referencia} onChange={(e) => setPago({ ...pago, referencia: e.target.value })} /></Field>}
            <Aviso>{error}</Aviso>
            <div className="flex justify-end"><Button>Guardar</Button></div>
          </form>
        )}
      </Modal>
    </Card>
  )
}
