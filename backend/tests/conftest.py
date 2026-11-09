"""Las pruebas usan una base aparte (mediagenda_test) que se recrea con los datos demo."""
import os

import psycopg
import pytest

BASE = "postgresql://mediagenda:mediagenda_dev@127.0.0.1:5435"
os.environ["DATABASE_URL"] = f"{BASE}/mediagenda_test"
os.environ["RECORDATORIOS_ACTIVOS"] = "0"

with psycopg.connect(f"{BASE}/mediagenda", autocommit=True) as c:
    if not c.execute("SELECT 1 FROM pg_database WHERE datname='mediagenda_test'").fetchone():
        c.execute("CREATE DATABASE mediagenda_test")

from fastapi.testclient import TestClient  # noqa: E402

from app import seed  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def datos():
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        seed.recrear_esquema(c)
        seed.cargar(c)
        c.commit()


@pytest.fixture(scope="session")
def cliente(datos):
    with TestClient(app) as c:
        yield c


def _login(cliente, email, pw):
    r = cliente.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def admin(cliente):
    return _login(cliente, "admin@mediagenda.com", "admin123")


@pytest.fixture(scope="session")
def medico(cliente):
    return _login(cliente, "dra.fuentes@mediagenda.com", "medico123")


@pytest.fixture(scope="session")
def recepcion(cliente):
    return _login(cliente, "recepcion@mediagenda.com", "recepcion123")


@pytest.fixture(scope="session")
def paciente(cliente):
    return _login(cliente, "maria.gonzalez@correo.com", "paciente123")
