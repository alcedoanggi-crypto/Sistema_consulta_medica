"""Receta médica en PDF con código QR de verificación."""
import io
from datetime import date

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from . import config

TEAL = colors.HexColor("#0f766e")


def _edad(nac):
    if not nac:
        return "—"
    hoy = date.today()
    return str(hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day)))


def receta_pdf(r) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    ancho, alto = letter
    c.setTitle(f"Receta {r['id']}")

    # Encabezado con datos del médico
    c.setFillColor(TEAL)
    c.rect(0, alto - 3.2 * cm, ancho, 3.2 * cm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2 * cm, alto - 1.5 * cm, config.CLINICA_NOMBRE)
    c.setFont("Helvetica", 11)
    c.drawString(2 * cm, alto - 2.2 * cm, f"Dr(a). {r['medico']}  ·  {r['especialidad'] or ''}")
    c.drawString(2 * cm, alto - 2.8 * cm, f"Cédula profesional: {r['cedula_profesional']}")

    # Paciente
    c.setFillColor(colors.black)
    y = alto - 4.5 * cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(2 * cm, y, "Paciente:")
    c.drawString(12.5 * cm, y, "Fecha:")
    c.setFont("Helvetica", 11)
    c.drawString(4 * cm, y, f"{r['paciente']}   (edad: {_edad(r['fecha_nacimiento'])})")
    c.drawString(14 * cm, y, r["creado"].strftime("%d/%m/%Y %H:%M"))
    c.setStrokeColor(TEAL)
    c.line(2 * cm, y - 0.4 * cm, ancho - 2 * cm, y - 0.4 * cm)

    # Indicaciones
    y -= 1.4 * cm
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(TEAL)
    c.drawString(2 * cm, y, "Rx")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    y -= 1 * cm
    for linea in r["medicamentos"].splitlines():
        for trozo in [linea[i:i + 85] for i in range(0, max(len(linea), 1), 85)]:
            c.drawString(2.4 * cm, y, trozo)
            y -= 0.6 * cm

    # QR de verificación pública
    url = f"{config.PUBLIC_URL}/api/publico/recetas/{r['codigo_verificacion']}"
    img = io.BytesIO()
    qrcode.make(url, box_size=6, border=1).save(img, format="PNG")
    img.seek(0)
    c.drawImage(ImageReader(img), 2 * cm, 2 * cm, 3.6 * cm, 3.6 * cm)
    c.setFont("Helvetica", 8)
    c.drawString(6 * cm, 4.6 * cm, "Verifique la autenticidad escaneando el código QR")
    c.drawString(6 * cm, 4.2 * cm, f"Folio: {r['codigo_verificacion']}")

    # Firma
    c.line(ancho - 8 * cm, 3 * cm, ancho - 2 * cm, 3 * cm)
    c.setFont("Helvetica", 9)
    c.drawCentredString(ancho - 5 * cm, 2.5 * cm, f"Dr(a). {r['medico']}")
    c.drawCentredString(ancho - 5 * cm, 2.1 * cm, f"Céd. Prof. {r['cedula_profesional']}")

    c.showPage()
    c.save()
    return buf.getvalue()
