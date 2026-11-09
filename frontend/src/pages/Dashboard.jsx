import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, dinero, hora } from '../api'
import { useUsuario } from '../App'
import { Badge, Card, Kpi, Tabla } from '../components/ui'

export default function Dashboard() {
  const { usuario } = useUsuario()
  const [d, setD] = useState(null)
  const [hoy, setHoy] = useState([])
  useEffect(() => {
    api('/dashboard').then(setD)
    api('/citas/hoy').then(setHoy)
  }, [])
  if (!d) return <p className="text-slate-500">Cargando…</p>
  const k = d.kpis
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Hola, {usuario.nombre.split(' ')[0]}</h1>
        <p className="text-slate-500">{new Date().toLocaleDateString('es-VE', { weekday: 'long', day: 'numeric', month: 'long' })}</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Citas de hoy" value={k.citas_hoy} hint={`${k.en_espera} en lista de espera`} />
        <Kpi label="Inasistencia (30 días)" value={`${k.tasa_inasistencia ?? 0}%`} tone="amber" hint="no asistió / atendidas" />
        <Kpi label="Ingresos del mes" value={dinero(k.ingresos_mes)} tone="indigo" hint={`${dinero(k.saldo_pendiente)} por cobrar`} />
        <Kpi label="Pacientes nuevos" value={k.pacientes_nuevos} hint="este mes" />
      </div>
      {k.alertas_inventario > 0 && (
        <Link to="/inventario" className="block rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 hover:bg-amber-100">
          ⚠ {k.alertas_inventario} artículo(s) del inventario caducados, por caducar o con stock bajo. Revisar →
        </Link>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card title="Agenda de hoy" className="lg:col-span-3">
          <Tabla rows={hoy} vacio="No hay citas hoy" cols={[
            { k: 'h', t: 'Hora', f: (r) => hora(r.inicio) },
            { k: 'paciente', t: 'Paciente', f: (r) => <Link className="text-teal-700 hover:underline" to={`/pacientes/${r.paciente_id}`}>{r.paciente}</Link> },
            { k: 'medico', t: 'Médico' },
            { k: 'servicio', t: 'Servicio' },
            { k: 'estado', t: 'Estado', f: (r) => <Badge v={r.estado} /> },
          ]} />
        </Card>
        <Card title="Servicios más solicitados (90 días)" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={d.servicios_top} layout="vertical" margin={{ left: 10 }}>
              <CartesianGrid horizontal={false} stroke="#e2e8f0" />
              <XAxis type="number" allowDecimals={false} fontSize={12} />
              <YAxis type="category" dataKey="nombre" width={130} fontSize={12} />
              <Tooltip />
              <Bar dataKey="total" name="Citas" fill="#0d9488" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card title="Ingresos de los últimos 14 días">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={d.ingresos_dias.map((x) => ({ ...x, total: Number(x.total), dia: x.dia.slice(5) }))}>
            <CartesianGrid vertical={false} stroke="#e2e8f0" />
            <XAxis dataKey="dia" fontSize={12} />
            <YAxis fontSize={12} />
            <Tooltip formatter={(v) => dinero(v)} />
            <Bar dataKey="total" name="Ingresos" fill="#6366f1" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  )
}
