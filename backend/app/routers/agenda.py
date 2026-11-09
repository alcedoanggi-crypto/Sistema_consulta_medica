from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import STAFF, requiere, usuario_actual
from ..db import ejecutar, pool, todos, uno

router = APIRouter(prefix="/api", tags=["agenda"])


class CitaNueva(BaseModel):
    tipo: str = "cita"
    medico_id: int
    consultorio_id: int | None = None
    paciente_id: int | None = None
    servicio_id: int | None = None
    inicio: datetime
    fin: datetime | None = None
    motivo: str | None = None


class CitaCambio(BaseModel):
    inicio: datetime | None = None
    fin: datetime | None = None
    estado: str | None = None
    consultorio_id: int | None = None


class Espera(BaseModel):
    paciente_id: int
    medico_id: int | None = None
    preferencia: str | None = None


class ReservaEnLinea(BaseModel):
    medico_id: int
    servicio_id: int
    inicio: datetime
    motivo: str | None = None


def _duracion(servicio_id):
    if not servicio_id:
        return 30
    s = uno("SELECT duracion_min FROM servicios WHERE id=%s", [servicio_id])
    return s["duracion_min"] if s else 30


SELECT_EVENTOS = """
    SELECT c.id, c.tipo, c.estado, c.motivo, c.origen, lower(c.rango) AS inicio, upper(c.rango) AS fin,
           c.medico_id, m.nombre AS medico, m.color, c.consultorio_id, co.nombre AS consultorio,
           c.paciente_id, p.nombre || ' ' || p.apellido AS paciente, p.telefono,
           c.servicio_id, s.nombre AS servicio
    FROM citas c JOIN usuarios m ON m.id = c.medico_id
    LEFT JOIN consultorios co ON co.id = c.consultorio_id
    LEFT JOIN pacientes p ON p.id = c.paciente_id
    LEFT JOIN servicios s ON s.id = c.servicio_id
"""


# ---- Catálogos para todos los usuarios autenticados ---------------------
@router.get("/medicos")
def medicos(u=Depends(usuario_actual)):
    return todos("SELECT id, nombre, especialidad, color FROM usuarios WHERE rol='medico' AND activo ORDER BY nombre")


@router.get("/consultorios")
def consultorios(u=Depends(usuario_actual)):
    return todos("SELECT * FROM consultorios ORDER BY nombre")


@router.get("/disponibilidad")
def disponibilidad(medico_id: int, fecha: date, servicio_id: int | None = None, u=Depends(usuario_actual)):
    """Horarios libres calculados en PostgreSQL al momento (sin caché)."""
    return todos("SELECT inicio, fin FROM horarios_disponibles(%s, %s, %s)", [medico_id, fecha, _duracion(servicio_id)])


# ---- Agenda del personal -------------------------------------------------
@router.get("/citas")
def citas(inicio: datetime, fin: datetime, medico_id: int | None = None, u=Depends(requiere(*STAFF))):
    if u["rol"] == "medico":
        medico_id = u["id"]  # cada médico ve su propia agenda
    return todos(
        SELECT_EVENTOS + """ WHERE c.rango && tstzrange(%s, %s) AND c.estado <> 'cancelada'
                             AND (%s::int IS NULL OR c.medico_id = %s) ORDER BY lower(c.rango)""",
        [inicio, fin, medico_id, medico_id],
    )


@router.get("/citas/hoy")
def citas_hoy(u=Depends(requiere(*STAFF))):
    medico = u["id"] if u["rol"] == "medico" else None
    return todos(
        SELECT_EVENTOS + """ WHERE c.tipo='cita' AND lower(c.rango)::date = current_date
                             AND (%s::int IS NULL OR c.medico_id = %s) ORDER BY lower(c.rango)""",
        [medico, medico],
    )


@router.post("/citas", status_code=201)
def crear_cita(c: CitaNueva, u=Depends(requiere(*STAFF))):
    fin = c.fin or c.inicio + timedelta(minutes=_duracion(c.servicio_id))
    # Si se encima con otra cita o bloqueo, PostgreSQL lanza ExclusionViolation → 409 (ver main.py)
    return ejecutar(
        """INSERT INTO citas (tipo, medico_id, consultorio_id, paciente_id, servicio_id, rango, motivo)
           VALUES (%s,%s,%s,%s,%s,tstzrange(%s,%s),%s) RETURNING id""",
        [c.tipo, c.medico_id, c.consultorio_id, c.paciente_id if c.tipo == "cita" else None,
         c.servicio_id, c.inicio, fin, c.motivo],
    )


@router.patch("/citas/{cid}")
def cambiar_cita(cid: int, c: CitaCambio, u=Depends(requiere(*STAFF))):
    actual = uno("SELECT * FROM citas WHERE id=%s", [cid])
    if not actual:
        raise HTTPException(404, "Cita no encontrada")
    with pool.connection() as conn:
        if c.inicio:  # arrastrar y soltar / redimensionar en el calendario
            fin = c.fin or c.inicio + (actual["rango"].upper - actual["rango"].lower)
            conn.execute("UPDATE citas SET rango=tstzrange(%s,%s), recordatorio_enviado=false WHERE id=%s",
                         [c.inicio, fin, cid])
        if c.consultorio_id is not None:
            conn.execute("UPDATE citas SET consultorio_id=%s WHERE id=%s", [c.consultorio_id, cid])
        if c.estado:
            conn.execute("UPDATE citas SET estado=%s WHERE id=%s", [c.estado, cid])
            # Al completar la cita se genera el cargo del servicio automáticamente
            if c.estado == "completada" and actual["servicio_id"] and actual["paciente_id"]:
                conn.execute(
                    """INSERT INTO cargos (paciente_id, servicio_id, cita_id, descripcion, monto)
                       SELECT %s, s.id, %s, s.nombre, s.precio FROM servicios s WHERE s.id=%s
                       AND NOT EXISTS (SELECT 1 FROM cargos WHERE cita_id=%s)""",
                    [actual["paciente_id"], cid, actual["servicio_id"], cid],
                )
    respuesta = {"ok": True}
    if c.estado == "cancelada":
        # sugerir a quién llamar de la lista de espera
        respuesta["lista_espera"] = todos(
            """SELECT e.id, p.nombre || ' ' || p.apellido AS paciente, p.telefono, e.preferencia
               FROM lista_espera e JOIN pacientes p ON p.id = e.paciente_id
               WHERE NOT e.atendida AND (e.medico_id IS NULL OR e.medico_id = %s) ORDER BY e.creado LIMIT 5""",
            [actual["medico_id"]],
        )
    return respuesta


@router.delete("/citas/{cid}")
def quitar_bloqueo(cid: int, u=Depends(requiere(*STAFF))):
    ejecutar("DELETE FROM citas WHERE id=%s AND tipo='bloqueo'", [cid])
    return {"ok": True}


# ---- Lista de espera -----------------------------------------------------
@router.get("/lista-espera")
def lista_espera(u=Depends(requiere(*STAFF))):
    return todos(
        """SELECT e.*, p.nombre || ' ' || p.apellido AS paciente, p.telefono, m.nombre AS medico
           FROM lista_espera e JOIN pacientes p ON p.id = e.paciente_id LEFT JOIN usuarios m ON m.id = e.medico_id
           WHERE NOT e.atendida ORDER BY e.creado"""
    )


@router.post("/lista-espera", status_code=201)
def agregar_espera(e: Espera, u=Depends(requiere(*STAFF))):
    return ejecutar(
        "INSERT INTO lista_espera (paciente_id, medico_id, preferencia) VALUES (%s,%s,%s) RETURNING id",
        [e.paciente_id, e.medico_id, e.preferencia],
    )


@router.post("/lista-espera/{eid}/atender")
def atender_espera(eid: int, u=Depends(requiere(*STAFF))):
    ejecutar("UPDATE lista_espera SET atendida=true WHERE id=%s", [eid])
    return {"ok": True}


# ---- Portal del paciente -------------------------------------------------
solo_paciente = requiere("paciente")


@router.get("/portal/citas")
def mis_citas(u=Depends(solo_paciente)):
    return todos(
        """SELECT c.id, c.estado, lower(c.rango) AS inicio, upper(c.rango) AS fin, m.nombre AS medico,
                  m.especialidad, s.nombre AS servicio, c.token
           FROM citas c JOIN usuarios m ON m.id = c.medico_id LEFT JOIN servicios s ON s.id = c.servicio_id
           WHERE c.paciente_id=%s ORDER BY lower(c.rango) DESC""",
        [u["paciente_id"]],
    )


@router.post("/portal/citas", status_code=201)
def reservar(r: ReservaEnLinea, u=Depends(solo_paciente)):
    if r.inicio <= datetime.now(r.inicio.tzinfo):
        raise HTTPException(400, "Elija un horario futuro")
    fin = r.inicio + timedelta(minutes=_duracion(r.servicio_id))
    # Dos pacientes pueden pedir el mismo horario al mismo tiempo: el EXCLUDE garantiza que solo uno gana
    return ejecutar(
        """INSERT INTO citas (medico_id, paciente_id, servicio_id, rango, motivo, origen)
           VALUES (%s,%s,%s,tstzrange(%s,%s),%s,'en_linea') RETURNING id""",
        [r.medico_id, u["paciente_id"], r.servicio_id, r.inicio, fin, r.motivo],
    )


@router.post("/portal/citas/{cid}/cancelar")
def cancelar_propia(cid: int, u=Depends(solo_paciente)):
    ejecutar(
        "UPDATE citas SET estado='cancelada' WHERE id=%s AND paciente_id=%s AND lower(rango) > now()",
        [cid, u["paciente_id"]],
    )
    return {"ok": True}


@router.get("/portal/recetas")
def mis_recetas(u=Depends(solo_paciente)):
    return todos(
        """SELECT r.id, r.creado, m.nombre AS medico FROM recetas r JOIN usuarios m ON m.id = r.medico_id
           WHERE r.paciente_id=%s ORDER BY r.creado DESC""",
        [u["paciente_id"]],
    )
