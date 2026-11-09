"""Datos de demostración.

    python -m app.seed --reset    # borra todo, recrea el esquema y carga la demo
"""
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg

from . import config

TZ = ZoneInfo("America/Caracas")
INIT = Path(__file__).resolve().parents[2] / "db" / "init"
random.seed(7)

NOMBRES = [("María", "González", "F"), ("José", "Rodríguez", "M"), ("Ana", "Martínez", "F"), ("Luis", "Hernández", "M"),
           ("Carmen", "López", "F"), ("Pedro", "Díaz", "M"), ("Laura", "Pérez", "F"), ("Miguel", "Sánchez", "M"),
           ("Sofía", "Ramírez", "F"), ("Andrés", "Torres", "M"), ("Valentina", "Flores", "F"), ("Diego", "Rivas", "M"),
           ("Isabel", "Mendoza", "F"), ("Carlos", "Castillo", "M"), ("Gabriela", "Rojas", "F"), ("Jorge", "Medina", "M"),
           ("Daniela", "Vargas", "F"), ("Ricardo", "Silva", "M"), ("Paula", "Romero", "F"), ("Fernando", "Herrera", "M")]
ALERGIAS = ["Penicilina", "Ninguna conocida", "AINES (ibuprofeno)", "Ninguna conocida", "Látex", "Sulfas", "Ninguna conocida"]
ANTECEDENTES = ["Hipertensión controlada", "Sin antecedentes relevantes", "Diabetes tipo 2", "Asma en la infancia",
                "Apendicectomía (2015)", "Sin antecedentes relevantes", "Ansiedad tratada en 2022"]


def recrear_esquema(c):
    c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    for f in sorted(INIT.glob("*.sql")):
        c.execute(f.read_text(encoding="utf-8"))


def cargar(c):
    c.execute("SELECT set_config('app.clave_cifrado', %s, false)", [config.CLAVE_CIFRADO])
    c.execute("INSERT INTO consultorios (nombre) VALUES ('Consultorio 1'), ('Consultorio 2'), ('Consultorio 3')")
    servicios = [("Consulta general", 40, 30), ("Control / seguimiento", 25, 30), ("Limpieza dental", 50, 60),
                 ("Resina dental", 80, 60), ("Sesión de psicología", 60, 60), ("Certificado médico", 20, 30)]
    for s in servicios:
        c.execute("INSERT INTO servicios (nombre, precio, duracion_min) VALUES (%s,%s,%s)", s)

    def usuario(nombre, email, pw, rol, esp=None, ced=None, color=None, paciente=None):
        return c.execute(
            """INSERT INTO usuarios (nombre, email, password_hash, rol, especialidad, cedula_profesional, color, paciente_id)
               VALUES (%s,%s,crypt(%s, gen_salt('bf')),%s,%s,%s,COALESCE(%s,'#0d9488'),%s) RETURNING id""",
            [nombre, email, pw, rol, esp, ced, color, paciente]).fetchone()[0]

    usuario("Administración", "admin@mediagenda.com", "admin123", "admin")
    usuario("Rosa Blanco", "recepcion@mediagenda.com", "recepcion123", "recepcion")
    medicos = {
        "general": usuario("Elena Fuentes", "dra.fuentes@mediagenda.com", "medico123", "medico",
                           "Medicina general", "MPPS-58421", "#0d9488"),
        "dental": usuario("Marco Ibarra", "dr.ibarra@mediagenda.com", "medico123", "medico",
                          "Odontología", "COV-12873", "#6366f1"),
        "psico": usuario("Lucía Navarro", "psic.navarro@mediagenda.com", "medico123", "medico",
                         "Psicología clínica", "FPV-7731", "#e11d48"),
    }
    servicio_de = {"general": [1, 2, 6], "dental": [3, 4], "psico": [5]}
    consultorio_de = {"general": 1, "dental": 2, "psico": 3}

    pacientes = []
    hoy = date.today()
    for i, (n, a, s) in enumerate(NOMBRES):
        creado = datetime.now(TZ) - timedelta(days=random.randint(0, 120))
        pid = c.execute(
            """INSERT INTO pacientes (nombre, apellido, fecha_nacimiento, sexo, email, telefono, direccion, documento_cif,
                 emergencia_nombre, emergencia_telefono, alergias_cif, antecedentes_cif, creado)
               VALUES (%s,%s,%s,%s,%s,%s,%s,cifrar(%s),%s,%s,cifrar(%s),cifrar(%s),%s) RETURNING id""",
            [n, a, date(1960 + random.randint(0, 45), random.randint(1, 12), random.randint(1, 28)), s,
             f"{n.lower().replace('í', 'i').replace('é', 'e').replace('á', 'a')}.{a.lower()}@correo.com",
             f"+58 412 {random.randint(1000000, 9999999)}", "Caracas, Venezuela", f"V-{random.randint(8, 30)}{random.randint(100000, 999999)}",
             f"Familiar de {n}", f"+58 414 {random.randint(1000000, 9999999)}",
             random.choice(ALERGIAS), random.choice(ANTECEDENTES), creado]).fetchone()[0]
        pacientes.append(pid)
    # El primer paciente tiene acceso al portal
    usuario("María González", "maria.gonzalez@correo.com", "paciente123", "paciente", paciente=pacientes[0])

    # Agenda: 45 días atrás + 10 adelante, de lunes a viernes
    for d in range(-45, 11):
        dia = hoy + timedelta(days=d)
        if dia.weekday() >= 5:
            continue
        for clave, mid in medicos.items():
            # bloqueo de almuerzo
            ini = datetime.combine(dia, time(12, 0), TZ)
            c.execute("INSERT INTO citas (tipo, medico_id, rango, motivo) VALUES ('bloqueo',%s,tstzrange(%s,%s),'Almuerzo')",
                      [mid, ini, ini + timedelta(hours=1)])
            hora = datetime.combine(dia, time(8, 0), TZ)
            fin_dia = datetime.combine(dia, time(17, 0), TZ)
            while hora < fin_dia:
                sid = random.choice(servicio_de[clave])
                dur = next(s[2] for i, s in enumerate(servicios, 1) if i == sid)
                fin = hora + timedelta(minutes=dur)
                if time(12, 0) <= hora.time() < time(13, 0) or (hora.time() < time(12, 0) < fin.time()):
                    hora = datetime.combine(dia, time(13, 0), TZ)
                    continue
                if fin > fin_dia:
                    break
                if random.random() < (0.55 if d < 0 else 0.4):
                    pid = random.choice(pacientes)
                    if d < 0:
                        estado = random.choices(["completada", "no_asistio", "cancelada"], [80, 12, 8])[0]
                    elif d == 0 and hora < datetime.now(TZ):
                        estado = "completada"
                    else:
                        estado = random.choice(["programada", "programada", "confirmada"])
                    cid = c.execute(
                        """INSERT INTO citas (medico_id, consultorio_id, paciente_id, servicio_id, rango, estado, origen,
                             creado, recordatorio_enviado)
                           VALUES (%s,%s,%s,%s,tstzrange(%s,%s),%s,%s,%s,%s) RETURNING id""",
                        [mid, consultorio_de[clave], pid, sid, hora, fin, estado,
                         random.choice(["recepcion", "recepcion", "en_linea"]), hora - timedelta(days=3), d < 0]).fetchone()[0]
                    if estado == "completada":
                        precio = next(s[1] for i, s in enumerate(servicios, 1) if i == sid)
                        c.execute(
                            "INSERT INTO cargos (paciente_id, servicio_id, cita_id, descripcion, monto, creado) VALUES (%s,%s,%s,%s,%s,%s)",
                            [pid, sid, cid, servicios[sid - 1][0], precio, fin])
                        if random.random() < 0.85:  # ~15% queda con saldo pendiente
                            c.execute(
                                "INSERT INTO pagos (paciente_id, monto, metodo, recibido_por, creado) VALUES (%s,%s,%s,2,%s)",
                                [pid, precio, random.choice(["efectivo", "tarjeta", "transferencia"]), fin + timedelta(minutes=5)])
                hora = fin

    # Expediente de María: notas SOAP firmadas, adenda, signos y receta
    mg, mid = pacientes[0], medicos["general"]
    for k, (fecha, s, o, a, p, dx) in enumerate([
        (hoy - timedelta(days=60), "Cefalea frontal de 3 días, empeora por la tarde.", "TA 138/88, FC 78. Sin signos meníngeos.",
         "Cefalea tensional. Cifras tensionales limítrofes.", "Paracetamol 500 mg c/8h por 3 días. Control de TA.", ["G44.2", "I10"]),
        (hoy - timedelta(days=30), "Acude a control de presión. Refiere menos cefalea.", "TA 132/84, FC 74, peso 71.2 kg.",
         "Hipertensión esencial en control con cambios de estilo de vida.", "Dieta baja en sodio, caminar 30 min diarios.", ["I10"]),
        (hoy - timedelta(days=7), "Control. Sin cefalea. Buena adherencia.", "TA 124/80, FC 70, peso 69.8 kg.",
         "Evolución favorable.", "Continuar indicaciones. Control en 2 meses.", ["I10"]),
    ]):
        nid = c.execute(
            """INSERT INTO notas_clinicas (paciente_id, medico_id, subjetivo_cif, objetivo_cif, evaluacion_cif, plan_cif, creado)
               VALUES (%s,%s,cifrar(%s),cifrar(%s),cifrar(%s),cifrar(%s),%s) RETURNING id""",
            [mg, mid, s, o, a, p, datetime.combine(fecha, time(9, 30), TZ)]).fetchone()[0]
        for j, cod in enumerate(dx):
            c.execute("INSERT INTO diagnosticos (nota_id, codigo, tipo) VALUES (%s,%s,%s)",
                      [nid, cod, "principal" if j == 0 else "secundario"])
        # Solo en la demo: se desactivan los triggers un instante para fechar la firma en el pasado
        c.execute("SET session_replication_role = replica")
        c.execute("UPDATE notas_clinicas SET firmada=true, firmada_en=creado + interval '25 minutes' WHERE id=%s", [nid])
        c.execute("SET session_replication_role = DEFAULT")
        if k == 0:
            c.execute("INSERT INTO adendas (nota_id, autor_id, texto_cif, creado) VALUES (%s,%s,cifrar(%s),%s)",
                      [nid, mid, "Se recibió laboratorio: perfil lipídico dentro de rangos normales.",
                       datetime.combine(fecha + timedelta(days=4), time(16, 10), TZ)])
            c.execute("INSERT INTO recetas (paciente_id, medico_id, nota_id, medicamentos_cif, creado) VALUES (%s,%s,%s,cifrar(%s),%s)",
                      [mg, mid, nid, "Paracetamol 500 mg tabletas\nTomar 1 tableta cada 8 horas por 3 días.\n\nMedir presión arterial en casa 3 veces por semana.",
                       datetime.combine(fecha, time(9, 50), TZ)])
    # borrador sin firmar
    c.execute("""INSERT INTO notas_clinicas (paciente_id, medico_id, subjetivo_cif, plan_cif)
                 VALUES (%s,%s,cifrar('Paciente solicita certificado médico para gimnasio.'),cifrar('Pendiente completar exploración.'))""",
              [mg, mid])
    for k, (sis, dia, fc, peso) in enumerate([(142, 90, 80, 72.5), (138, 88, 78, 72.0), (135, 86, 76, 71.6),
                                              (132, 84, 74, 71.2), (128, 82, 72, 70.4), (124, 80, 70, 69.8)]):
        c.execute(
            """INSERT INTO signos_vitales (paciente_id, registrado_por, fecha, peso_kg, talla_cm, presion_sis, presion_dia,
                 frec_cardiaca, temperatura, spo2) VALUES (%s,%s,%s,%s,163,%s,%s,%s,%s,%s)""",
            [mg, mid, datetime.combine(hoy - timedelta(days=75 - k * 14), time(9, 0), TZ), peso, sis, dia, fc,
             round(36.4 + random.random() * 0.5, 1), random.randint(96, 99)])

    for nombre, tipo, unidad, lote, cad, stock, minimo in [
        ("Paracetamol 500 mg", "medicamento", "caja", "PA-2291", hoy + timedelta(days=240), 40, 10),
        ("Ibuprofeno 400 mg", "medicamento", "caja", "IB-1180", hoy + timedelta(days=18), 12, 10),
        ("Amoxicilina 500 mg", "medicamento", "caja", "AM-0457", hoy - timedelta(days=5), 6, 5),
        ("Lidocaína 2% cartucho", "medicamento", "cartucho", "LD-7720", hoy + timedelta(days=150), 3, 20),
        ("Guantes de nitrilo M", "insumo", "caja", None, None, 25, 10),
        ("Jeringas 5 ml", "insumo", "unidad", "JR-332", hoy + timedelta(days=600), 180, 50),
        ("Gasas estériles", "insumo", "paquete", "GS-118", hoy + timedelta(days=25), 30, 15),
        ("Resina compuesta A2", "insumo", "jeringa", "RC-A2-09", hoy + timedelta(days=90), 4, 5),
        ("Alcohol al 70%", "insumo", "litro", None, None, 8, 4),
    ]:
        c.execute("""INSERT INTO inventario (nombre, tipo, unidad, lote, caducidad, stock, stock_minimo)
                     VALUES (%s,%s,%s,%s,%s,%s,%s)""", [nombre, tipo, unidad, lote, cad, stock, minimo])

    c.execute("INSERT INTO lista_espera (paciente_id, medico_id, preferencia) VALUES (%s,%s,'Mañanas, lo antes posible'), (%s,%s,'Cualquier tarde')",
              [pacientes[5], medicos["dental"], pacientes[9], medicos["psico"]])


def main():
    with psycopg.connect(config.DATABASE_URL, autocommit=False) as c:
        if "--reset" in sys.argv:
            recrear_esquema(c)
        cargar(c)
        c.commit()
    print("Datos demo cargados.")


if __name__ == "__main__":
    main()
