import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fechaHora } from '../api'
import { Badge, Card, Tabla } from '../components/ui'

export default function Bitacora() {
  const [rows, setRows] = useState([])
  useEffect(() => { api('/bitacora').then(setRows) }, [])
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Bitácora de acceso</h1>
        <p className="text-sm text-slate-500">Cada apertura de expediente, estudio o receta queda registrada. La tabla es de solo inserción: nadie puede editar ni borrar registros.</p>
      </div>
      <Card>
        <Tabla rows={rows} vacio="Sin accesos registrados" cols={[
          { k: 'creado', t: 'Fecha', f: (r) => fechaHora(r.creado) },
          { k: 'usuario', t: 'Usuario', f: (r) => <>{r.usuario} <Badge v="x">{r.rol}</Badge></> },
          { k: 'accion', t: 'Acción', f: (r) => <code className="text-xs">{r.accion}</code> },
          { k: 'paciente', t: 'Paciente', f: (r) => r.paciente_id ? <Link className="text-teal-700 hover:underline" to={`/pacientes/${r.paciente_id}`}>{r.paciente}</Link> : '—' },
          { k: 'ip', t: 'IP' },
        ]} />
      </Card>
    </div>
  )
}
