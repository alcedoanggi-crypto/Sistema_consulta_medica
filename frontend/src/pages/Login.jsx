import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { api } from '../api'
import { useUsuario } from '../App'
import { Aviso, Button, Field, Input } from '../components/ui'

const DEMO = [
  ['Administrador', 'admin@mediagenda.com', 'admin123'],
  ['Médico', 'dra.fuentes@mediagenda.com', 'medico123'],
  ['Recepción', 'recepcion@mediagenda.com', 'recepcion123'],
  ['Paciente', 'maria.gonzalez@correo.com', 'paciente123'],
]

export default function Login() {
  const { usuario, entrar } = useUsuario()
  const [modo, setModo] = useState('login')
  const [f, setF] = useState({ email: '', password: '', nombre: '', apellido: '', telefono: '' })
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)
  if (usuario) return <Navigate to={usuario.rol === 'paciente' ? '/portal' : '/'} replace />

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const enviar = async (e, datos = f) => {
    e?.preventDefault()
    setError(''); setCargando(true)
    try {
      entrar(modo === 'login' || !e
        ? await api('/auth/login', { method: 'POST', body: { email: datos.email, password: datos.password } })
        : await api('/auth/registro', { method: 'POST', body: datos }))
    } catch (err) { setError(err.message) } finally { setCargando(false) }
  }

  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <div className="hidden flex-col justify-between bg-gradient-to-br from-teal-800 to-teal-950 p-12 text-teal-50 md:flex">
        <div className="flex items-center gap-2 text-xl font-bold"><img src="/logo.svg" alt="" className="h-9 w-9" /> MediAgenda</div>
        <div>
          <h1 className="text-4xl font-bold leading-tight text-white">Agenda, expediente clínico y cobros en un solo lugar.</h1>
          <p className="mt-4 max-w-md text-teal-200">Para consultorios médicos, dentales y de psicología. Datos sensibles cifrados, notas firmadas inmutables y bitácora de cada acceso.</p>
        </div>
        <p className="text-sm text-teal-300">Python · FastAPI · PostgreSQL · React</p>
      </div>

      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-bold">{modo === 'login' ? 'Iniciar sesión' : 'Crear cuenta de paciente'}</h2>
          <p className="mt-1 text-sm text-slate-500">
            {modo === 'login' ? '¿Eres paciente y no tienes cuenta? ' : '¿Ya tienes cuenta? '}
            <button className="font-medium text-teal-700 underline" onClick={() => { setModo(modo === 'login' ? 'registro' : 'login'); setError('') }}>
              {modo === 'login' ? 'Regístrate para reservar' : 'Inicia sesión'}
            </button>
          </p>
          <form onSubmit={enviar} className="mt-6 space-y-4">
            {modo === 'registro' && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Nombre"><Input required value={f.nombre} onChange={set('nombre')} /></Field>
                <Field label="Apellido"><Input required value={f.apellido} onChange={set('apellido')} /></Field>
                <Field label="Teléfono" className="col-span-2"><Input value={f.telefono} onChange={set('telefono')} /></Field>
              </div>
            )}
            <Field label="Correo"><Input type="email" required autoComplete="username" value={f.email} onChange={set('email')} /></Field>
            <Field label="Contraseña"><Input type="password" required minLength={modo === 'registro' ? 8 : 1} autoComplete="current-password" value={f.password} onChange={set('password')} /></Field>
            <Aviso>{error}</Aviso>
            <Button className="w-full" disabled={cargando}>{cargando ? 'Entrando…' : modo === 'login' ? 'Entrar' : 'Crear cuenta'}</Button>
          </form>

          {modo === 'login' && (
            <div className="mt-8 rounded-xl border border-dashed border-slate-300 p-4">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Cuentas de demostración</p>
              <div className="grid grid-cols-2 gap-2">
                {DEMO.map(([rol, email, password]) => (
                  <Button key={rol} variant="secondary" type="button" disabled={cargando} onClick={() => enviar(null, { email, password })}>{rol}</Button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
