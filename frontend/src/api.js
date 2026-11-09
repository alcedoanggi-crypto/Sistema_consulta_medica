const CLAVE = 'mediagenda_token'

export const sesion = {
  token: () => localStorage.getItem(CLAVE),
  guardar: (t) => localStorage.setItem(CLAVE, t),
  salir: () => localStorage.removeItem(CLAVE),
}

export async function api(ruta, { method = 'GET', body, form, blob } = {}) {
  const headers = {}
  if (sesion.token()) headers.Authorization = `Bearer ${sesion.token()}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const r = await fetch(`/api${ruta}`, {
    method,
    headers,
    body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
  })
  if (r.status === 401 && ruta !== '/auth/login') {
    sesion.salir()
    window.location.href = '/login'
  }
  if (!r.ok) {
    const e = await r.json().catch(() => ({}))
    const msg = Array.isArray(e.detail) ? e.detail.map((d) => d.msg).join('; ') : e.detail
    throw new Error(msg || `Error ${r.status}`)
  }
  if (blob) return r.blob()
  return r.status === 204 ? null : r.json()
}

export async function abrirArchivo(ruta) {
  const b = await api(ruta, { blob: true })
  window.open(URL.createObjectURL(b), '_blank')
}

export const dinero = (n) =>
  Number(n || 0).toLocaleString('es-VE', { style: 'currency', currency: 'USD' })
export const fecha = (d) => (d ? new Date(d).toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: 'numeric' }) : '—')
export const fechaHora = (d) =>
  d ? new Date(d).toLocaleString('es-VE', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'
export const hora = (d) => new Date(d).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' })
