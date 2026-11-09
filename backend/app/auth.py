from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config
from .db import uno

STAFF = ("admin", "medico", "recepcion")
CLINICO = ("admin", "medico")  # recepción NUNCA ve contenido clínico

_bearer = HTTPBearer(auto_error=False)


def crear_token(usuario):
    datos = {
        "sub": str(usuario["id"]),
        "rol": usuario["rol"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=10),
    }
    return jwt.encode(datos, config.JWT_SECRET, algorithm="HS256")


def autenticar(email, password):
    # La contraseña se verifica dentro de PostgreSQL con crypt() (bcrypt de pgcrypto)
    return uno(
        """SELECT id, nombre, email, rol, especialidad, paciente_id FROM usuarios
           WHERE lower(email) = lower(%s) AND activo AND password_hash = crypt(%s, password_hash)""",
        [email, password],
    )


def usuario_actual(cred: HTTPAuthorizationCredentials = Depends(_bearer)):
    if not cred:
        raise HTTPException(401, "No autenticado")
    try:
        datos = jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Sesión inválida o expirada")
    u = uno(
        "SELECT id, nombre, email, rol, especialidad, cedula_profesional, paciente_id FROM usuarios WHERE id=%s AND activo",
        [int(datos["sub"])],
    )
    if not u:
        raise HTTPException(401, "Usuario inactivo")
    return u


def requiere(*roles):
    def dep(u=Depends(usuario_actual)):
        if u["rol"] not in roles:
            raise HTTPException(403, "No tiene permiso para esta sección")
        return u
    return dep
