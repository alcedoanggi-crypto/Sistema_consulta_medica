import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, dinero } from '../api'
import { Button, Card, Input, Modal, Tabla } from '../components/ui'
import { FormPaciente } from './Paciente'

export default function Pacientes() {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [nuevo, setNuevo] = useState(false)
  const nav = useNavigate()

  useEffect(() => {
    const t = setTimeout(() => api(`/pacientes?q=${encodeURIComponent(q)}`).then(setRows), 250)
    return () => clearTimeout(t)
  }, [q])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Pacientes</h1>
        <Button onClick={() => setNuevo(true)}>+ Nuevo paciente</Button>
      </div>
      <Card>
        <div className="mb-4 max-w-sm"><Input type="search" aria-label="Buscar" placeholder="Buscar por nombre o correo…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <Tabla rows={rows} cols={[
          { k: 'n', t: 'Paciente', f: (r) => <Link className="font-medium text-teal-700 hover:underline" to={`/pacientes/${r.id}`}>{r.apellido}, {r.nombre}</Link> },
          { k: 'documento', t: 'Documento' },
          { k: 'telefono', t: 'Teléfono' },
          { k: 'email', t: 'Correo' },
          { k: 'saldo', t: 'Saldo', r: true, f: (r) => <span className={r.saldo > 0 ? 'font-medium text-red-600' : 'text-slate-500'}>{dinero(r.saldo)}</span> },
        ]} />
      </Card>
      <Modal open={nuevo} title="Nuevo paciente" wide onClose={() => setNuevo(false)}>
        <FormPaciente onGuardar={async (d) => { const r = await api('/pacientes', { method: 'POST', body: d }); nav(`/pacientes/${r.id}`) }} />
      </Modal>
    </div>
  )
}
