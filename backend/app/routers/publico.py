"""Endpoints sin sesión: login, registro de pacientes, enlaces de correo y verificación de recetas."""
import html
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field

from .. import config
from ..auth import autenticar, crear_token, usuario_actual
from ..db import pool, uno

router = APIRouter(prefix="/api", tags=["publico"])


class Login(BaseModel):
    email: str
    password: str


class Registro(BaseModel):
    nombre: str
    apellido: str
    email: EmailStr
    telefono: str | None = None
    fecha_nacimiento: date | None = None
    password: str = Field(min_length=8)


@router.post("/auth/login")
def login(d: Login):
    u = autenticar(d.email, d.password)
    if not u:
        raise HTTPException(401, "Correo o contraseña incorrectos")
    return {"token": crear_token(u), "usuario": u}


@router.get("/auth/me")
def yo(u=Depends(usuario_actual)):
    return u


@router.post("/auth/registro", status_code=201)
def registro(d: Registro):
    """Autoregistro de pacientes para reservar citas en línea."""
    if uno("SELECT 1 FROM usuarios WHERE lower(email)=lower(%s)", [d.email]):
        raise HTTPException(409, "Ya existe una cuenta con ese correo")
    with pool.connection() as c:
        p = c.execute(
            "INSERT INTO pacientes (nombre, apellido, email, telefono, fecha_nacimiento) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            [d.nombre, d.apellido, d.email, d.telefono, d.fecha_nacimiento],
        ).fetchone()
        u = c.execute(
            """INSERT INTO usuarios (nombre, email, password_hash, rol, paciente_id)
               VALUES (%s,%s,crypt(%s, gen_salt('bf')),'paciente',%s)
               RETURNING id, nombre, email, rol, especialidad, paciente_id""",
            [f"{d.nombre} {d.apellido}", d.email, d.password, p["id"]],
        ).fetchone()
    return {"token": crear_token(u), "usuario": u}


def _pagina(titulo, mensaje, ok=True):
    color = "#0f766e" if ok else "#b91c1c"
    return HTMLResponse(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{titulo} · MediAgenda</title></head>
<body style="font-family:system-ui,sans-serif;background:#f1f5f9;display:grid;place-items:center;min-height:100vh;margin:0;padding:16px">
<main style="background:#fff;border-radius:16px;padding:32px;max-width:440px;box-shadow:0 4px 24px #0001;text-align:center">
<h1 style="color:{color};margin-top:0">{titulo}</h1><p style="color:#334155;line-height:1.5">{mensaje}</p>
<a href="{config.FRONTEND_URL}" style="color:#0f766e">Ir a MediAgenda</a></main></body></html>""")


def _cita_por_token(token: UUID):
    return uno(
        """SELECT c.id, c.estado, lower(c.rango) AS inicio, m.nombre AS medico
           FROM citas c JOIN usuarios m ON m.id = c.medico_id WHERE c.token=%s""",
        [token],
    )


@router.get("/publico/citas/{token}/confirmar", response_class=HTMLResponse)
def confirmar(token: UUID):
    c = _cita_por_token(token)
    if not c or c["estado"] not in ("programada", "confirmada"):
        return _pagina("Enlace no válido", "La cita no existe o ya no se puede confirmar.", ok=False)
    with pool.connection() as conn:
        conn.execute("UPDATE citas SET estado='confirmada' WHERE id=%s", [c["id"]])
    return _pagina("¡Cita confirmada!",
                   f"Le esperamos el {c['inicio']:%d/%m/%Y a las %H:%M} con Dr(a). {html.escape(c['medico'])}.")


@router.get("/publico/citas/{token}/cancelar", response_class=HTMLResponse)
def cancelar(token: UUID):
    c = _cita_por_token(token)
    if not c or c["estado"] not in ("programada", "confirmada"):
        return _pagina("Enlace no válido", "La cita no existe o ya fue cancelada.", ok=False)
    with pool.connection() as conn:
        conn.execute("UPDATE citas SET estado='cancelada' WHERE id=%s", [c["id"]])
    return _pagina("Cita cancelada", "Su horario quedó liberado. Puede reservar otra cita cuando guste.")


@router.get("/publico/recetas/{codigo}", response_class=HTMLResponse)
def verificar_receta(codigo: UUID):
    # Solo se muestran datos mínimos: nunca el contenido de la receta
    r = uno(
        """SELECT r.creado, m.nombre AS medico, m.cedula_profesional,
                  left(p.nombre, 1) || '. ' || left(p.apellido, 1) || '.' AS iniciales
           FROM recetas r JOIN usuarios m ON m.id = r.medico_id JOIN pacientes p ON p.id = r.paciente_id
           WHERE r.codigo_verificacion=%s""",
        [codigo],
    )
    if not r:
        return _pagina("Receta no válida", "Este código no corresponde a ninguna receta emitida.", ok=False)
    return _pagina("Receta auténtica ✓",
                   f"Emitida el {r['creado']:%d/%m/%Y} por Dr(a). {html.escape(r['medico'])} "
                   f"(cédula profesional {html.escape(r['cedula_profesional'])}) "
                   f"para el paciente {html.escape(r['iniciales'])}")
