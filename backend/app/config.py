import os
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
CLAVE_CIFRADO = os.environ["CLAVE_CIFRADO"]
JWT_SECRET = os.environ["JWT_SECRET"]
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8010")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5200")
CLINICA_NOMBRE = os.getenv("CLINICA_NOMBRE", "MediAgenda")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "recordatorios@mediagenda.local")
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "")
RECORDATORIOS_ACTIVOS = os.getenv("RECORDATORIOS_ACTIVOS", "1") == "1"

UPLOADS = BASE / "uploads"
OUTBOX = BASE / "outbox"
