import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import errors

from . import config, recordatorios
from .db import pool
from .routers import agenda, expediente, gestion, pacientes, publico

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    pool.open(wait=True)
    parar = threading.Event()
    if config.RECORDATORIOS_ACTIVOS:
        recordatorios.iniciar(parar)
    yield
    parar.set()
    pool.close()


app = FastAPI(title="MediAgenda API", version="1.0", lifespan=ciclo_vida)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_URL, "http://127.0.0.1:5200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (publico, pacientes, agenda, expediente, gestion):
    app.include_router(r.router)


# Las reglas de negocio las hace cumplir PostgreSQL; aquí solo se traducen a HTTP
@app.exception_handler(errors.ExclusionViolation)
def solape(request: Request, exc):
    return JSONResponse(status_code=409, content={
        "detail": "Ese horario se encima con otra cita o bloqueo del médico o del consultorio."})


@app.exception_handler(errors.CheckViolation)
def regla(request: Request, exc):
    return JSONResponse(status_code=409, content={"detail": exc.diag.message_primary})


@app.exception_handler(errors.UniqueViolation)
def duplicado(request: Request, exc):
    return JSONResponse(status_code=409, content={"detail": "El registro ya existe."})


@app.exception_handler(errors.ForeignKeyViolation)
def referencia(request: Request, exc):
    return JSONResponse(status_code=400, content={"detail": "Referencia inválida (paciente, médico o catálogo)."})


@app.get("/api/salud")
def salud():
    return {"ok": True}
