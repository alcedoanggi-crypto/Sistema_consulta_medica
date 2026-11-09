from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from ..auth import CLINICO, requiere, usuario_actual
from ..db import ejecutar, pool, registrar_acceso, todos, uno
from ..pdf import receta_pdf

router = APIRouter(prefix="/api", tags=["expediente"])
solo_medico = requiere("medico")


class Nota(BaseModel):
    paciente_id: int
    cita_id: int | None = None
    subjetivo: str = ""
    objetivo: str = ""
    evaluacion: str = ""
    plan: str = ""
    diagnosticos: list[str] = []
    firmar: bool = False


class Adenda(BaseModel):
    texto: str


class Signos(BaseModel):
    paciente_id: int
    fecha: datetime | None = None
    peso_kg: float | None = None
    talla_cm: float | None = None
    presion_sis: int | None = None
    presion_dia: int | None = None
    frec_cardiaca: int | None = None
    temperatura: float | None = None
    spo2: int | None = None


class Receta(BaseModel):
    paciente_id: int
    nota_id: int | None = None
    medicamentos: str


@router.get("/cie10")
def buscar_cie10(q: str = "", u=Depends(requiere(*CLINICO))):
    return todos(
        "SELECT codigo, descripcion FROM cie10 WHERE codigo ILIKE %s OR descripcion ILIKE %s ORDER BY codigo LIMIT 20",
        [f"{q}%", f"%{q}%"],
    )


def _guardar_diagnosticos(conn, nota_id, codigos):
    conn.execute("DELETE FROM diagnosticos WHERE nota_id=%s", [nota_id])
    for i, cod in enumerate(codigos):
        conn.execute(
            "INSERT INTO diagnosticos (nota_id, codigo, tipo) VALUES (%s,%s,%s)",
            [nota_id, cod, "principal" if i == 0 else "secundario"],
        )


@router.post("/notas", status_code=201)
def crear_nota(n: Nota, u=Depends(solo_medico)):
    with pool.connection() as c:
        nota = c.execute(
            """INSERT INTO notas_clinicas (paciente_id, medico_id, cita_id, subjetivo_cif, objetivo_cif, evaluacion_cif, plan_cif)
               VALUES (%s,%s,%s,cifrar(%s),cifrar(%s),cifrar(%s),cifrar(%s)) RETURNING id""",
            [n.paciente_id, u["id"], n.cita_id, n.subjetivo, n.objetivo, n.evaluacion, n.plan],
        ).fetchone()
        _guardar_diagnosticos(c, nota["id"], n.diagnosticos)
        if n.firmar:
            c.execute("UPDATE notas_clinicas SET firmada=true WHERE id=%s", [nota["id"]])
    return nota


@router.put("/notas/{nid}")
def editar_borrador(nid: int, n: Nota, u=Depends(solo_medico)):
    """Solo borradores. Si la nota ya está firmada, el TRIGGER de PostgreSQL rechaza el UPDATE."""
    actual = uno("SELECT medico_id FROM notas_clinicas WHERE id=%s", [nid])
    if not actual or actual["medico_id"] != u["id"]:
        raise HTTPException(403, "Solo el médico autor puede editar el borrador")
    with pool.connection() as c:
        c.execute(
            """UPDATE notas_clinicas SET subjetivo_cif=cifrar(%s), objetivo_cif=cifrar(%s),
                 evaluacion_cif=cifrar(%s), plan_cif=cifrar(%s) WHERE id=%s""",
            [n.subjetivo, n.objetivo, n.evaluacion, n.plan, nid],
        )
        _guardar_diagnosticos(c, nid, n.diagnosticos)
        if n.firmar:
            c.execute("UPDATE notas_clinicas SET firmada=true WHERE id=%s", [nid])
    return {"ok": True}


@router.post("/notas/{nid}/firmar")
def firmar(nid: int, u=Depends(solo_medico)):
    actual = uno("SELECT medico_id FROM notas_clinicas WHERE id=%s", [nid])
    if not actual or actual["medico_id"] != u["id"]:
        raise HTTPException(403, "Solo el médico autor puede firmar la nota")
    ejecutar("UPDATE notas_clinicas SET firmada=true WHERE id=%s", [nid])
    return {"ok": True}


@router.post("/notas/{nid}/adendas", status_code=201)
def agregar_adenda(nid: int, a: Adenda, u=Depends(solo_medico)):
    return ejecutar(
        "INSERT INTO adendas (nota_id, autor_id, texto_cif) VALUES (%s,%s,cifrar(%s)) RETURNING id",
        [nid, u["id"], a.texto],
    )


@router.post("/signos", status_code=201)
def registrar_signos(s: Signos, u=Depends(requiere(*CLINICO))):
    return ejecutar(
        """INSERT INTO signos_vitales (paciente_id, registrado_por, fecha, peso_kg, talla_cm, presion_sis,
             presion_dia, frec_cardiaca, temperatura, spo2)
           VALUES (%s,%s,COALESCE(%s, now()),%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        [s.paciente_id, u["id"], s.fecha, s.peso_kg, s.talla_cm, s.presion_sis, s.presion_dia,
         s.frec_cardiaca, s.temperatura, s.spo2],
    )


@router.post("/recetas", status_code=201)
def crear_receta(r: Receta, u=Depends(solo_medico)):
    return ejecutar(
        """INSERT INTO recetas (paciente_id, medico_id, nota_id, medicamentos_cif)
           VALUES (%s,%s,%s,cifrar(%s)) RETURNING id, codigo_verificacion""",
        [r.paciente_id, u["id"], r.nota_id, r.medicamentos],
    )


@router.get("/recetas/{rid}/pdf")
def descargar_receta(rid: int, request: Request, u=Depends(usuario_actual)):
    r = uno(
        """SELECT r.id, r.creado, r.codigo_verificacion, r.paciente_id, descifrar(r.medicamentos_cif) AS medicamentos,
                  p.nombre || ' ' || p.apellido AS paciente, p.fecha_nacimiento,
                  m.nombre AS medico, m.especialidad, m.cedula_profesional
           FROM recetas r JOIN pacientes p ON p.id = r.paciente_id JOIN usuarios m ON m.id = r.medico_id
           WHERE r.id=%s""",
        [rid],
    )
    # el paciente solo puede descargar sus propias recetas; recepción ninguna
    if not r or not (u["rol"] in CLINICO or (u["rol"] == "paciente" and u["paciente_id"] == r["paciente_id"])):
        raise HTTPException(404, "Receta no encontrada")
    if u["rol"] in CLINICO:
        registrar_acceso(u["id"], r["paciente_id"], f"ver_receta:{rid}", request.client.host if request.client else None)
    return Response(
        receta_pdf(r),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="receta-{rid}.pdf"'},
    )


@router.get("/bitacora")
def bitacora(paciente_id: int | None = None, u=Depends(requiere("admin"))):
    return todos(
        """SELECT b.id, b.creado, b.accion, host(b.ip) AS ip, us.nombre AS usuario, us.rol,
                  p.nombre || ' ' || p.apellido AS paciente, b.paciente_id
           FROM bitacora_acceso b JOIN usuarios us ON us.id = b.usuario_id
           LEFT JOIN pacientes p ON p.id = b.paciente_id
           WHERE %s::int IS NULL OR b.paciente_id = %s
           ORDER BY b.creado DESC LIMIT 300""",
        [paciente_id, paciente_id],
    )
