import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import config
from ..auth import CLINICO, STAFF, requiere
from ..db import ejecutar, registrar_acceso, todos, uno

router = APIRouter(prefix="/api", tags=["pacientes"])


class Paciente(BaseModel):
    nombre: str
    apellido: str
    fecha_nacimiento: date | None = None
    sexo: str | None = None
    email: str | None = None
    telefono: str | None = None
    direccion: str | None = None
    documento: str | None = None
    emergencia_nombre: str | None = None
    emergencia_telefono: str | None = None


class Antecedentes(BaseModel):
    alergias: str | None = None
    antecedentes: str | None = None


# Datos generales: NO incluye columnas clínicas, así recepción puede verlos
CAMPOS_GENERALES = """p.id, p.nombre, p.apellido, p.fecha_nacimiento, p.sexo, p.email, p.telefono,
    p.direccion, descifrar(p.documento_cif) AS documento, p.emergencia_nombre, p.emergencia_telefono, p.creado"""


@router.get("/pacientes")
def listar(q: str = "", u=Depends(requiere(*STAFF))):
    return todos(
        f"""SELECT {CAMPOS_GENERALES}, s.saldo FROM pacientes p JOIN v_saldos s ON s.paciente_id = p.id
            WHERE (p.nombre || ' ' || p.apellido) ILIKE %s OR p.email ILIKE %s
            ORDER BY p.apellido, p.nombre LIMIT 200""",
        [f"%{q}%", f"%{q}%"],
    )


@router.post("/pacientes", status_code=201)
def crear(p: Paciente, u=Depends(requiere(*STAFF))):
    return ejecutar(
        """INSERT INTO pacientes (nombre, apellido, fecha_nacimiento, sexo, email, telefono, direccion,
             documento_cif, emergencia_nombre, emergencia_telefono)
           VALUES (%s,%s,%s,%s,%s,%s,%s,cifrar(%s),%s,%s) RETURNING id""",
        [p.nombre, p.apellido, p.fecha_nacimiento, p.sexo, p.email, p.telefono, p.direccion,
         p.documento, p.emergencia_nombre, p.emergencia_telefono],
    )


@router.get("/pacientes/{pid}")
def detalle(pid: int, u=Depends(requiere(*STAFF))):
    p = uno(f"SELECT {CAMPOS_GENERALES} FROM pacientes p WHERE id=%s", [pid])
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    return p


@router.put("/pacientes/{pid}")
def actualizar(pid: int, p: Paciente, u=Depends(requiere(*STAFF))):
    ejecutar(
        """UPDATE pacientes SET nombre=%s, apellido=%s, fecha_nacimiento=%s, sexo=%s, email=%s, telefono=%s,
             direccion=%s, documento_cif=cifrar(%s), emergencia_nombre=%s, emergencia_telefono=%s WHERE id=%s""",
        [p.nombre, p.apellido, p.fecha_nacimiento, p.sexo, p.email, p.telefono, p.direccion,
         p.documento, p.emergencia_nombre, p.emergencia_telefono, pid],
    )
    return {"ok": True}


@router.get("/pacientes/{pid}/expediente")
def expediente(pid: int, request: Request, u=Depends(requiere(*CLINICO))):
    p = uno(
        """SELECT id, nombre, apellido, fecha_nacimiento, sexo,
                  descifrar(alergias_cif) AS alergias, descifrar(antecedentes_cif) AS antecedentes
           FROM pacientes WHERE id=%s""",
        [pid],
    )
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    registrar_acceso(u["id"], pid, "abrir_expediente", request.client.host if request.client else None)

    notas = todos(
        """SELECT n.id, n.creado, n.firmada, n.firmada_en, n.cita_id, n.medico_id, m.nombre AS medico,
                  descifrar(n.subjetivo_cif) AS subjetivo, descifrar(n.objetivo_cif) AS objetivo,
                  descifrar(n.evaluacion_cif) AS evaluacion, descifrar(n.plan_cif) AS plan,
                  COALESCE((SELECT json_agg(json_build_object('codigo', d.codigo, 'descripcion', c.descripcion, 'tipo', d.tipo))
                            FROM diagnosticos d JOIN cie10 c USING (codigo) WHERE d.nota_id = n.id), '[]') AS diagnosticos,
                  COALESCE((SELECT json_agg(json_build_object('id', a.id, 'creado', a.creado, 'autor', ua.nombre,
                                                              'texto', descifrar(a.texto_cif)) ORDER BY a.creado)
                            FROM adendas a JOIN usuarios ua ON ua.id = a.autor_id WHERE a.nota_id = n.id), '[]') AS adendas
           FROM notas_clinicas n JOIN usuarios m ON m.id = n.medico_id
           WHERE n.paciente_id=%s ORDER BY n.creado DESC""",
        [pid],
    )
    signos = todos("SELECT * FROM signos_vitales WHERE paciente_id=%s ORDER BY fecha", [pid])
    recetas = todos(
        """SELECT r.id, r.creado, r.codigo_verificacion, m.nombre AS medico, descifrar(r.medicamentos_cif) AS medicamentos
           FROM recetas r JOIN usuarios m ON m.id = r.medico_id WHERE r.paciente_id=%s ORDER BY r.creado DESC""",
        [pid],
    )
    return {"paciente": p, "notas": notas, "signos": signos, "recetas": recetas}


@router.put("/pacientes/{pid}/antecedentes")
def guardar_antecedentes(pid: int, a: Antecedentes, u=Depends(requiere(*CLINICO))):
    ejecutar(
        "UPDATE pacientes SET alergias_cif=cifrar(%s), antecedentes_cif=cifrar(%s) WHERE id=%s",
        [a.alergias, a.antecedentes, pid],
    )
    return {"ok": True}


# ---- Archivos adjuntos -------------------------------------------------
def _categorias_permitidas(rol):
    return ("documento", "estudio") if rol in CLINICO else ("documento",)


@router.get("/pacientes/{pid}/archivos")
def archivos(pid: int, u=Depends(requiere(*STAFF))):
    return todos(
        """SELECT a.id, a.categoria, a.nombre_original, a.mime, a.creado, us.nombre AS subido_por
           FROM archivos a LEFT JOIN usuarios us ON us.id = a.subido_por
           WHERE a.paciente_id=%s AND a.categoria = ANY(%s) ORDER BY a.creado DESC""",
        [pid, list(_categorias_permitidas(u["rol"]))],
    )


@router.post("/pacientes/{pid}/archivos", status_code=201)
async def subir(pid: int, categoria: str = Form(...), archivo: UploadFile = File(...), u=Depends(requiere(*STAFF))):
    if categoria not in _categorias_permitidas(u["rol"]):
        raise HTTPException(403, "Recepción solo puede adjuntar documentos administrativos")
    contenido = await archivo.read()
    if len(contenido) > 10 * 1024 * 1024:
        raise HTTPException(413, "Máximo 10 MB por archivo")
    carpeta = config.UPLOADS / str(pid)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"{uuid.uuid4().hex}_{archivo.filename.replace('/', '_').replace(chr(92), '_')}"
    (carpeta / nombre).write_bytes(contenido)
    return ejecutar(
        """INSERT INTO archivos (paciente_id, categoria, nombre_original, ruta, mime, subido_por)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        [pid, categoria, archivo.filename, f"{pid}/{nombre}", archivo.content_type, u["id"]],
    )


@router.get("/archivos/{aid}")
def descargar(aid: int, request: Request, u=Depends(requiere(*STAFF))):
    a = uno("SELECT * FROM archivos WHERE id=%s", [aid])
    if not a or a["categoria"] not in _categorias_permitidas(u["rol"]):
        raise HTTPException(404, "Archivo no encontrado")
    if a["categoria"] == "estudio":
        registrar_acceso(u["id"], a["paciente_id"], f"ver_estudio:{aid}", request.client.host if request.client else None)
    return FileResponse(config.UPLOADS / a["ruta"], media_type=a["mime"], filename=a["nombre_original"])
