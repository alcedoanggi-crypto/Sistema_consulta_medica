import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, dinero, hora } from '../api'
import { Card, Field, Input, Kpi, Tabla } from '../components/ui'

const hoyISO = () => new Date().toLocaleDateString('en-CA')

export default function Caja() {
  const [fecha, setFecha] = useState(hoyISO())
  const [corte, setCorte] = useState(null)
  const [saldos, setSaldos] = useState([])
  useEffect(() => { api(`/caja/corte?fecha=${fecha}`).then(setCorte) }, [fecha])
  useEffect(() => { api('/saldos').then(setSaldos) }, [])

  const metodo = (m) => corte?.por_metodo.find((x) => x.metodo === m)?.total || 0
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-bold">Cobros y corte de caja</h1>
        <Field label="Fecha del corte"><Input type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} /></Field>
      </div>
      {corte && <>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Kpi label="Total del día" value={dinero(corte.total)} tone="indigo" hint={`${corte.pagos.length} pagos`} />
          <Kpi label="Efectivo" value={dinero(metodo('efectivo'))} />
          <Kpi label="Tarjeta" value={dinero(metodo('tarjeta'))} />
          <Kpi label="Transferencia" value={dinero(metodo('transferencia'))} />
        </div>
        <Card title="Pagos del día" actions={<button className="text-sm text-teal-700 underline print:hidden" onClick={() => window.print()}>Imprimir corte</button>}>
          <Tabla rows={corte.pagos} vacio="No hubo pagos este día" cols={[
            { k: 'h', t: 'Hora', f: (r) => hora(r.creado) },
            { k: 'paciente', t: 'Paciente' },
            { k: 'metodo', t: 'Método' },
            { k: 'referencia', t: 'Referencia' },
            { k: 'recibido_por', t: 'Recibió' },
            { k: 'monto', t: 'Monto', r: true, f: (r) => dinero(r.monto) },
          ]} />
        </Card>
      </>}
      <Card title="Saldos pendientes">
        <Tabla rows={saldos} vacio="Nadie debe 🎉" cols={[
          { k: 'paciente', t: 'Paciente', f: (r) => <Link className="text-teal-700 hover:underline" to={`/pacientes/${r.paciente_id}`}>{r.paciente}</Link> },
          { k: 'cargos', t: 'Cargos', r: true, f: (r) => dinero(r.cargos) },
          { k: 'pagos', t: 'Pagado', r: true, f: (r) => dinero(r.pagos) },
          { k: 'saldo', t: 'Saldo', r: true, f: (r) => <b className="text-red-600">{dinero(r.saldo)}</b> },
        ]} />
      </Card>
    </div>
  )
}
