"""Recordatorios automáticos: cada minuto busca citas en las próximas 24 h
sin recordatorio y envía correo (SMTP o archivo .eml) y, opcionalmente, WhatsApp."""
import json
import logging
import smtplib
import threading
import urllib.request
from email.message import EmailMessage

from . import config
from .db import ejecutar, todos

log = logging.getLogger("recordatorios")


def _mensaje(c):
    base = f"{config.PUBLIC_URL}/api/publico/citas/{c['token']}"
    texto = (
        f"Hola {c['paciente']},\n\n"
        f"Le recordamos su cita de {c['servicio'] or 'consulta'} con Dr(a). {c['medico']} "
        f"el {c['inicio']:%d/%m/%Y a las %H:%M}.\n\n"
        f"Confirmar: {base}/confirmar\nCancelar:  {base}/cancelar\n\n{config.CLINICA_NOMBRE}"
    )
    m = EmailMessage()
    m["Subject"] = f"Recordatorio de cita · {c['inicio']:%d/%m %H:%M}"
    m["From"] = config.SMTP_FROM
    m["To"] = c["email"]
    m.set_content(texto)
    return m, texto


def _enviar_correo(m, cita_id):
    if config.SMTP_HOST:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as s:
            s.starttls()
            if config.SMTP_USER:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
            s.send_message(m)
    else:  # modo desarrollo: queda en backend/outbox para revisarlo
        config.OUTBOX.mkdir(exist_ok=True)
        (config.OUTBOX / f"cita_{cita_id}.eml").write_bytes(bytes(m))


def _enviar_whatsapp(telefono, texto):
    """Punto de integración con el módulo de mensajería por WhatsApp (opcional)."""
    if not (config.WHATSAPP_API_URL and telefono):
        return
    req = urllib.request.Request(
        config.WHATSAPP_API_URL,
        data=json.dumps({"telefono": telefono, "mensaje": texto}).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)


def procesar_pendientes():
    pendientes = todos(
        """SELECT c.id, c.token, lower(c.rango) AS inicio, p.nombre AS paciente, p.email, p.telefono,
                  m.nombre AS medico, s.nombre AS servicio
           FROM citas c JOIN pacientes p ON p.id = c.paciente_id JOIN usuarios m ON m.id = c.medico_id
           LEFT JOIN servicios s ON s.id = c.servicio_id
           WHERE c.tipo='cita' AND c.estado='programada' AND NOT c.recordatorio_enviado
             AND lower(c.rango) BETWEEN now() AND now() + interval '24 hours'"""
    )
    for c in pendientes:
        try:
            if c["email"]:
                m, texto = _mensaje(c)
                _enviar_correo(m, c["id"])
                _enviar_whatsapp(c["telefono"], texto)
            ejecutar("UPDATE citas SET recordatorio_enviado=true WHERE id=%s", [c["id"]])
            log.info("Recordatorio enviado para la cita %s", c["id"])
        except Exception:
            log.exception("No se pudo enviar el recordatorio de la cita %s", c["id"])
    return len(pendientes)


def iniciar(parar: threading.Event):
    def ciclo():
        while not parar.is_set():
            try:
                procesar_pendientes()
            except Exception:
                log.exception("Fallo en el ciclo de recordatorios")
            parar.wait(60)

    threading.Thread(target=ciclo, daemon=True, name="recordatorios").start()
