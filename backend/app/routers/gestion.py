"""Facturación, inventario, dashboard y usuarios (sin contenido clínico)."""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import STAFF, requiere, usuario_actual
from ..db import ejecutar, todos, uno

router = APIRouter(prefix="/api", tags=["gestion"])
staff = requiere(*STAFF)
admin = requiere("admin")


class Servicio(BaseModel):
    nombre: str
    precio: float
    duracion_min: int = 30
    activo: bool = True


class Cargo(BaseModel):
    paciente_id: int
    servicio_id: int | None = None
    descripcion: str
    monto: float


class Pago(BaseModel):
    paciente_id: int
    monto: float
    metodo: str
    referencia: str | None = None


class Insumo(BaseModel):
    nombre: str
    tipo: str
    unidad: str = "unidad"
    lote: str | None = None
    caducidad: date | None = None
    stock: int = 0
    stock_minimo: int = 5


class Ajuste(BaseModel):
    cantidad: int  # positivo = entrada, negativo = salida


class UsuarioNuevo(BaseModel):
    nombre: str
    email: str
    password: str
    rol: str
    especialidad: str | None = None
    cedula_profesional: str | None = None
    color: str | None = "#0d9488"


# ---- Servicios ------------------------------------------------------------
@router.get("/servicios")
def servicios(u=Depends(usuario_actual)):
    return todos("SELECT * FROM servicios WHERE activo OR %s ORDER BY nombre", [u["rol"] == "admin"])


@router.post("/servicios", status_code=201)
def crear_servicio(s: Servicio, u=Depends(admin)):
    return ejecutar(
        "INSERT INTO servicios (nombre, precio, duracion_min, activo) VALUES (%s,%s,%s,%s) RETURNING id",
        [s.nombre, s.precio, s.duracion_min, s.activo],
    )


@router.put("/servicios/{sid}")
def editar_servicio(sid: int, s: Servicio, u=Depends(admin)):
    ejecutar("UPDATE servicios SET nombre=%s, precio=%s, duracion_min=%s, activo=%s WHERE id=%s",
             [s.nombre, s.precio, s.duracion_min, s.activo, sid])
    return {"ok": True}


# ---- Cobros ---------------------------------------------------------------
@router.get("/pacientes/{pid}/cuenta")
def cuenta(pid: int, u=Depends(staff)):
    movimientos = todos(
        """SELECT 'cargo' AS tipo, id, creado, descripcion, monto FROM cargos WHERE paciente_id=%s
           UNION ALL
           SELECT 'pago', id, creado, 'Pago ' || metodo || COALESCE(' · ' || referencia, ''), monto FROM pagos WHERE paciente_id=%s
           ORDER BY creado DESC""",
        [pid, pid],
    )
    return {"saldo": uno("SELECT * FROM v_saldos WHERE paciente_id=%s", [pid]), "movimientos": movimientos}


@router.post("/cargos", status_code=201)
def crear_cargo(c: Cargo, u=Depends(staff)):
    return ejecutar(
        "INSERT INTO cargos (paciente_id, servicio_id, descripcion, monto) VALUES (%s,%s,%s,%s) RETURNING id",
        [c.paciente_id, c.servicio_id, c.descripcion, c.monto],
    )


@router.post("/pagos", status_code=201)
def crear_pago(p: Pago, u=Depends(staff)):
    return ejecutar(
        "INSERT INTO pagos (paciente_id, monto, metodo, referencia, recibido_por) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        [p.paciente_id, p.monto, p.metodo, p.referencia, u["id"]],
    )


@router.get("/saldos")
def saldos_pendientes(u=Depends(staff)):
    return todos("SELECT * FROM v_saldos WHERE saldo > 0 ORDER BY saldo DESC")


@router.get("/caja/corte")
def corte_caja(fecha: date | None = None, u=Depends(staff)):
    fecha = fecha or date.today()
    pagos = todos(
        """SELECT g.id, g.creado, g.monto, g.metodo, g.referencia, p.nombre || ' ' || p.apellido AS paciente,
                  us.nombre AS recibido_por
           FROM pagos g JOIN pacientes p ON p.id = g.paciente_id LEFT JOIN usuarios us ON us.id = g.recibido_por
           WHERE g.creado::date = %s ORDER BY g.creado""",
        [fecha],
    )
    por_metodo = todos(
        "SELECT metodo, count(*) AS cantidad, sum(monto) AS total FROM pagos WHERE creado::date = %s GROUP BY metodo ORDER BY metodo",
        [fecha],
    )
    return {"fecha": fecha, "pagos": pagos, "por_metodo": por_metodo,
            "total": sum(float(m["total"]) for m in por_metodo)}


# ---- Inventario -------------------------------------------------------------
@router.get("/inventario")
def inventario(u=Depends(staff)):
    return todos(
        """SELECT i.*, a.alerta FROM inventario i LEFT JOIN v_alertas_inventario a ON a.id = i.id
           ORDER BY a.alerta IS NULL, i.caducidad NULLS LAST, i.nombre"""
    )


@router.post("/inventario", status_code=201)
def crear_insumo(i: Insumo, u=Depends(staff)):
    return ejecutar(
        """INSERT INTO inventario (nombre, tipo, unidad, lote, caducidad, stock, stock_minimo)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        [i.nombre, i.tipo, i.unidad, i.lote, i.caducidad, i.stock, i.stock_minimo],
    )


@router.put("/inventario/{iid}")
def editar_insumo(iid: int, i: Insumo, u=Depends(staff)):
    ejecutar(
        """UPDATE inventario SET nombre=%s, tipo=%s, unidad=%s, lote=%s, caducidad=%s, stock=%s, stock_minimo=%s
           WHERE id=%s""",
        [i.nombre, i.tipo, i.unidad, i.lote, i.caducidad, i.stock, i.stock_minimo, iid],
    )
    return {"ok": True}


@router.post("/inventario/{iid}/ajuste")
def ajustar_stock(iid: int, a: Ajuste, u=Depends(staff)):
    # CHECK (stock >= 0) en la tabla impide sacar más de lo que hay
    return ejecutar("UPDATE inventario SET stock = stock + %s WHERE id=%s RETURNING stock", [a.cantidad, iid])


# ---- Dashboard ------------------------------------------------------------
@router.get("/dashboard")
def dashboard(u=Depends(staff)):
    kpis = uno(
        """SELECT
             (SELECT count(*) FROM citas WHERE tipo='cita' AND estado <> 'cancelada'
                AND lower(rango)::date = current_date) AS citas_hoy,
             (SELECT round(100.0 * count(*) FILTER (WHERE estado='no_asistio')
                     / NULLIF(count(*) FILTER (WHERE estado IN ('completada','no_asistio')), 0), 1)
                FROM citas WHERE tipo='cita' AND lower(rango) >= now() - interval '30 days') AS tasa_inasistencia,
             (SELECT COALESCE(sum(monto), 0) FROM pagos
                WHERE date_trunc('month', creado) = date_trunc('month', now())) AS ingresos_mes,
             (SELECT count(*) FROM pacientes
                WHERE date_trunc('month', creado) = date_trunc('month', now())) AS pacientes_nuevos,
             (SELECT count(*) FROM v_alertas_inventario) AS alertas_inventario,
             (SELECT COALESCE(sum(saldo), 0) FROM v_saldos WHERE saldo > 0) AS saldo_pendiente,
             (SELECT count(*) FROM lista_espera WHERE NOT atendida) AS en_espera"""
    )
    servicios_top = todos(
        """SELECT s.nombre, count(*) AS total FROM citas c JOIN servicios s ON s.id = c.servicio_id
           WHERE c.tipo='cita' AND c.estado <> 'cancelada' AND lower(c.rango) >= now() - interval '90 days'
           GROUP BY s.nombre ORDER BY total DESC LIMIT 6"""
    )
    ingresos_dias = todos(
        """SELECT d::date AS dia, COALESCE(sum(p.monto), 0) AS total
           FROM generate_series(current_date - 13, current_date, interval '1 day') d
           LEFT JOIN pagos p ON p.creado::date = d::date GROUP BY d ORDER BY d"""
    )
    return {"kpis": kpis, "servicios_top": servicios_top, "ingresos_dias": ingresos_dias}


# ---- Usuarios -------------------------------------------------------------
@router.get("/usuarios")
def usuarios(u=Depends(admin)):
    return todos(
        """SELECT id, nombre, email, rol, especialidad, cedula_profesional, color, activo FROM usuarios
           WHERE rol <> 'paciente' ORDER BY rol, nombre"""
    )


@router.post("/usuarios", status_code=201)
def crear_usuario(n: UsuarioNuevo, u=Depends(admin)):
    return ejecutar(
        """INSERT INTO usuarios (nombre, email, password_hash, rol, especialidad, cedula_profesional, color)
           VALUES (%s,%s,crypt(%s, gen_salt('bf')),%s,%s,%s,%s) RETURNING id""",
        [n.nombre, n.email, n.password, n.rol, n.especialidad, n.cedula_profesional, n.color],
    )
