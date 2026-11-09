from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg
import pytest

from app import config

TZ = ZoneInfo("America/Caracas")


def dia_habil_futuro(n=20):
    d = date.today() + timedelta(days=n)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def medico_id(cliente, h, nombre="Elena"):
    return next(m["id"] for m in cliente.get("/api/medicos", headers=h).json() if nombre in m["nombre"])


def iso(dt):
    return dt.isoformat()


# ---- Agenda: EXCLUDE con tstzrange ----------------------------------------
def test_no_permite_citas_encimadas(cliente, recepcion):
    mid = medico_id(cliente, recepcion)
    ini = datetime.combine(dia_habil_futuro(), time(18, 0), TZ)  # fuera del horario sembrado
    base = {"medico_id": mid, "paciente_id": 2, "inicio": iso(ini), "fin": iso(ini + timedelta(minutes=30))}
    assert cliente.post("/api/citas", json=base, headers=recepcion).status_code == 201
    encimada = {**base, "paciente_id": 3, "inicio": iso(ini + timedelta(minutes=15)), "fin": iso(ini + timedelta(minutes=45))}
    r = cliente.post("/api/citas", json=encimada, headers=recepcion)
    assert r.status_code == 409 and "encima" in r.json()["detail"]
    # contigua: el rango [) excluye el fin, así que 18:30 a 19:00 sí se permite
    contigua = {**base, "paciente_id": 3, "inicio": iso(ini + timedelta(minutes=30)), "fin": iso(ini + timedelta(minutes=60))}
    assert cliente.post("/api/citas", json=contigua, headers=recepcion).status_code == 201


def test_bloqueo_impide_citas(cliente, recepcion):
    mid = medico_id(cliente, recepcion, "Marco")
    ini = datetime.combine(dia_habil_futuro(21), time(18, 0), TZ)
    fin = ini + timedelta(hours=1)
    bloqueo = {"tipo": "bloqueo", "medico_id": mid, "inicio": iso(ini), "fin": iso(fin), "motivo": "Congreso"}
    assert cliente.post("/api/citas", headers=recepcion, json=bloqueo).status_code == 201
    cita = {"medico_id": mid, "paciente_id": 4, "inicio": iso(ini + timedelta(minutes=10)), "fin": iso(fin)}
    assert cliente.post("/api/citas", headers=recepcion, json=cita).status_code == 409


def test_cancelada_libera_horario(cliente, recepcion):
    mid = medico_id(cliente, recepcion, "Lucía")
    ini = datetime.combine(dia_habil_futuro(22), time(18, 0), TZ)
    cuerpo = {"medico_id": mid, "paciente_id": 5, "inicio": iso(ini), "fin": iso(ini + timedelta(hours=1))}
    cid = cliente.post("/api/citas", json=cuerpo, headers=recepcion).json()["id"]
    cliente.patch(f"/api/citas/{cid}", json={"estado": "cancelada"}, headers=recepcion)
    assert cliente.post("/api/citas", json=cuerpo, headers=recepcion).status_code == 201


def test_reserva_en_linea_y_disponibilidad(cliente, paciente):
    mid = medico_id(cliente, paciente)
    dia = dia_habil_futuro(25)
    url = f"/api/disponibilidad?medico_id={mid}&fecha={dia}&servicio_id=1"
    slots = cliente.get(url, headers=paciente).json()
    assert slots, "debe haber horarios libres"
    s = slots[0]["inicio"]
    reserva = {"medico_id": mid, "servicio_id": 1, "inicio": s}
    assert cliente.post("/api/portal/citas", json=reserva, headers=paciente).status_code == 201
    # el horario desaparece de la disponibilidad y no se puede volver a tomar
    assert s not in [x["inicio"] for x in cliente.get(url, headers=paciente).json()]
    assert cliente.post("/api/portal/citas", json=reserva, headers=paciente).status_code == 409


# ---- Roles ---------------------------------------------------------------
def test_recepcion_no_ve_contenido_clinico(cliente, recepcion):
    assert cliente.get("/api/pacientes/1/expediente", headers=recepcion).status_code == 403
    assert cliente.get("/api/cie10?q=I10", headers=recepcion).status_code == 403
    datos = cliente.get("/api/pacientes/1", headers=recepcion).json()
    assert "alergias" not in datos and "antecedentes" not in datos
    assert cliente.post("/api/notas", json={"paciente_id": 1}, headers=recepcion).status_code == 403


def test_paciente_no_entra_al_sistema_interno(cliente, paciente):
    assert cliente.get("/api/pacientes", headers=paciente).status_code == 403
    assert cliente.get("/api/pacientes/2/expediente", headers=paciente).status_code == 403


# ---- Expediente ------------------------------------------------------------
def test_abrir_expediente_queda_en_bitacora(cliente, medico, admin):
    antes = len(cliente.get("/api/bitacora?paciente_id=3", headers=admin).json())
    assert cliente.get("/api/pacientes/3/expediente", headers=medico).status_code == 200
    log = cliente.get("/api/bitacora?paciente_id=3", headers=admin).json()
    assert len(log) == antes + 1 and log[0]["accion"] == "abrir_expediente"


def test_nota_firmada_es_inmutable(cliente, medico):
    nota = {"paciente_id": 2, "subjetivo": "Dolor de garganta", "diagnosticos": ["J02.9"], "firmar": True}
    nid = cliente.post("/api/notas", headers=medico, json=nota).json()["id"]
    r = cliente.put(f"/api/notas/{nid}", headers=medico, json={"paciente_id": 2, "subjetivo": "cambiado"})
    assert r.status_code == 409 and "firmada" in r.json()["detail"]
    assert cliente.post(f"/api/notas/{nid}/adendas", headers=medico, json={"texto": "Cultivo negativo"}).status_code == 201
    notas = cliente.get("/api/pacientes/2/expediente", headers=medico).json()["notas"]
    n = next(x for x in notas if x["id"] == nid)
    assert n["subjetivo"] == "Dolor de garganta" and n["adendas"][0]["texto"] == "Cultivo negativo"


@pytest.mark.parametrize("sql", ["DELETE FROM bitacora_acceso", "UPDATE bitacora_acceso SET accion='x'",
                                 "TRUNCATE bitacora_acceso"])
def test_bitacora_no_se_puede_alterar(sql):
    with psycopg.connect(config.DATABASE_URL) as c:
        c.execute("INSERT INTO bitacora_acceso (usuario_id, accion) VALUES (1, 'prueba')")
        with pytest.raises(psycopg.errors.CheckViolation):
            c.execute(sql)


def test_datos_cifrados_en_reposo():
    with psycopg.connect(config.DATABASE_URL) as c:
        crudo = c.execute("SELECT alergias_cif FROM pacientes WHERE id=1").fetchone()[0]
        assert crudo is not None and b"Ninguna" not in crudo and b"Penicilina" not in crudo
        # sin la clave en la sesión no se puede descifrar
        with pytest.raises(psycopg.Error):
            c.execute("SELECT descifrar(alergias_cif) FROM pacientes WHERE id=1")


def test_receta_pdf_y_verificacion(cliente, medico, paciente):
    r = cliente.post("/api/recetas", headers=medico, json={"paciente_id": 1, "medicamentos": "Ibuprofeno 400 mg c/8h"}).json()
    pdf = cliente.get(f"/api/recetas/{r['id']}/pdf", headers=medico)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert cliente.get(f"/api/recetas/{r['id']}/pdf", headers=paciente).status_code == 200  # es de María
    ver = cliente.get(f"/api/publico/recetas/{r['codigo_verificacion']}")
    assert "auténtica" in ver.text and "Ibuprofeno" not in ver.text


# ---- Facturación, inventario y recordatorios -------------------------------
def test_completar_cita_genera_cargo_y_saldo(cliente, recepcion):
    mid = medico_id(cliente, recepcion)
    ini = datetime.combine(dia_habil_futuro(23), time(18, 0), TZ)
    nuevo = cliente.post("/api/pacientes", headers=recepcion, json={"nombre": "Prueba", "apellido": "Saldo"}).json()["id"]
    cita = {"medico_id": mid, "paciente_id": nuevo, "servicio_id": 1, "inicio": iso(ini)}
    cid = cliente.post("/api/citas", headers=recepcion, json=cita).json()["id"]
    cliente.patch(f"/api/citas/{cid}", json={"estado": "completada"}, headers=recepcion)
    saldo = lambda: float(cliente.get(f"/api/pacientes/{nuevo}/cuenta", headers=recepcion).json()["saldo"]["saldo"])  # noqa: E731
    assert saldo() == 40
    cliente.post("/api/pagos", headers=recepcion, json={"paciente_id": nuevo, "monto": 40, "metodo": "efectivo"})
    assert saldo() == 0
    assert cliente.get("/api/caja/corte", headers=recepcion).json()["total"] >= 40


def test_inventario_alertas_y_sin_negativos(cliente, recepcion):
    items = cliente.get("/api/inventario", headers=recepcion).json()
    assert {"caducado", "por_caducar", "stock_bajo"} <= {i["alerta"] for i in items}
    item = items[0]
    r = cliente.post(f"/api/inventario/{item['id']}/ajuste", json={"cantidad": -(item["stock"] + 1)}, headers=recepcion)
    assert r.status_code == 409


def test_recordatorio_y_enlace_de_confirmacion(cliente, recepcion):
    from app import recordatorios
    mid = medico_id(cliente, recepcion, "Marco")
    ini = datetime.now(TZ) + timedelta(hours=3)
    ini = ini.replace(minute=0, second=0, microsecond=0)
    if ini.hour < 17:  # evitar el horario ya ocupado por la demo
        ini = ini.replace(hour=20)
    cuerpo = {"medico_id": mid, "paciente_id": 1, "inicio": iso(ini), "fin": iso(ini + timedelta(minutes=15))}
    cid = cliente.post("/api/citas", headers=recepcion, json=cuerpo).json()["id"]
    if ini - datetime.now(TZ) <= timedelta(hours=24):
        recordatorios.procesar_pendientes()
        assert (config.OUTBOX / f"cita_{cid}.eml").exists()
    with psycopg.connect(config.DATABASE_URL) as c:
        token = c.execute("SELECT token FROM citas WHERE id=%s", [cid]).fetchone()[0]
    assert "confirmada" in cliente.get(f"/api/publico/citas/{token}/confirmar").text
    assert "cancelada" in cliente.get(f"/api/publico/citas/{token}/cancelar").text
