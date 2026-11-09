import { createContext, useContext, useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { api, sesion } from './api'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Agenda from './pages/Agenda'
import Pacientes from './pages/Pacientes'
import Paciente from './pages/Paciente'
import Caja from './pages/Caja'
import Inventario from './pages/Inventario'
import Bitacora from './pages/Bitacora'
import Portal from './pages/Portal'

const Ctx = createContext(null)
export const useUsuario = () => useContext(Ctx)

const MENU = [
  { to: '/', t: 'Dashboard', roles: ['admin', 'medico', 'recepcion'] },
  { to: '/agenda', t: 'Agenda', roles: ['admin', 'medico', 'recepcion'] },
  { to: '/pacientes', t: 'Pacientes', roles: ['admin', 'medico', 'recepcion'] },
  { to: '/caja', t: 'Cobros y caja', roles: ['admin', 'recepcion'] },
  { to: '/inventario', t: 'Inventario', roles: ['admin', 'medico', 'recepcion'] },
  { to: '/bitacora', t: 'Bitácora de acceso', roles: ['admin'] },
  { to: '/portal', t: 'Mis citas', roles: ['paciente'] },
]
const ROL = { admin: 'Administrador', medico: 'Médico', recepcion: 'Recepción', paciente: 'Paciente' }

function Layout({ children }) {
  const { usuario, salir } = useUsuario()
  const [abierto, setAbierto] = useState(false)
  const items = MENU.filter((m) => m.roles.includes(usuario.rol))
  return (
    <div className="min-h-screen md:flex">
      <a href="#contenido" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-white focus:p-2">
        Saltar al contenido
      </a>
      <aside className={`${abierto ? 'block' : 'hidden'} fixed inset-0 z-40 w-64 bg-teal-900 text-teal-50 md:sticky md:top-0 md:block md:h-screen`}>
        <div className="flex items-center gap-2 px-5 py-5">
          <img src="/logo.svg" alt="" className="h-8 w-8" />
          <span className="text-lg font-bold tracking-tight">MediAgenda</span>
        </div>
        <nav aria-label="Principal" className="space-y-1 px-3">
          {items.map((m) => (
            <NavLink key={m.to} to={m.to} end={m.to === '/'} onClick={() => setAbierto(false)}
              className={({ isActive }) => `block rounded-lg px-3 py-2 text-sm font-medium ${isActive ? 'bg-teal-700 text-white' : 'text-teal-100 hover:bg-teal-800'}`}>
              {m.t}
            </NavLink>
          ))}
        </nav>
        <div className="absolute bottom-0 w-full border-t border-teal-800 p-4 text-sm">
          <p className="font-medium">{usuario.nombre}</p>
          <p className="text-teal-300">{ROL[usuario.rol]}{usuario.especialidad ? ` · ${usuario.especialidad}` : ''}</p>
          <button onClick={salir} className="mt-2 text-teal-200 underline hover:text-white">Cerrar sesión</button>
        </div>
      </aside>
      <div className="flex-1">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden">
          <span className="font-bold text-teal-800">MediAgenda</span>
          <button onClick={() => setAbierto(!abierto)} className="rounded-lg border px-3 py-1 text-sm" aria-expanded={abierto}>Menú</button>
        </header>
        <main id="contenido" className="mx-auto max-w-7xl p-4 md:p-8">{children}</main>
      </div>
    </div>
  )
}

function Protegida({ roles, children }) {
  const { usuario } = useUsuario()
  if (!usuario) return <Navigate to="/login" replace />
  if (roles && !roles.includes(usuario.rol)) return <Navigate to={usuario.rol === 'paciente' ? '/portal' : '/'} replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  const [usuario, setUsuario] = useState(undefined)
  const nav = useNavigate()

  useEffect(() => {
    if (!sesion.token()) return setUsuario(null)
    api('/auth/me').then(setUsuario).catch(() => setUsuario(null))
  }, [])

  const entrar = ({ token, usuario }) => {
    sesion.guardar(token)
    setUsuario(usuario)
    nav(usuario.rol === 'paciente' ? '/portal' : '/')
  }
  const salir = () => { sesion.salir(); setUsuario(null); nav('/login') }

  if (usuario === undefined) return <p className="p-8 text-slate-500">Cargando…</p>
  const staff = ['admin', 'medico', 'recepcion']
  return (
    <Ctx.Provider value={{ usuario, entrar, salir }}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Protegida roles={staff}><Dashboard /></Protegida>} />
        <Route path="/agenda" element={<Protegida roles={staff}><Agenda /></Protegida>} />
        <Route path="/pacientes" element={<Protegida roles={staff}><Pacientes /></Protegida>} />
        <Route path="/pacientes/:id" element={<Protegida roles={staff}><Paciente /></Protegida>} />
        <Route path="/caja" element={<Protegida roles={['admin', 'recepcion']}><Caja /></Protegida>} />
        <Route path="/inventario" element={<Protegida roles={staff}><Inventario /></Protegida>} />
        <Route path="/bitacora" element={<Protegida roles={['admin']}><Bitacora /></Protegida>} />
        <Route path="/portal" element={<Protegida roles={['paciente']}><Portal /></Protegida>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Ctx.Provider>
  )
}
