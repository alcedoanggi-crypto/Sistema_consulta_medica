"""Pool de conexiones. Cada conexión recibe la clave de cifrado como
parámetro de sesión (app.clave_cifrado); la clave nunca se guarda en la BD."""
import ipaddress

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config


def _configurar(conn):
    conn.execute("SELECT set_config('app.clave_cifrado', %s, false)", [config.CLAVE_CIFRADO])
    conn.commit()


pool = ConnectionPool(
    config.DATABASE_URL,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
    configure=_configurar,
    open=False,
)


def todos(sql, params=None):
    with pool.connection() as c:
        return c.execute(sql, params).fetchall()


def uno(sql, params=None):
    with pool.connection() as c:
        return c.execute(sql, params).fetchone()


def ejecutar(sql, params=None):
    """INSERT/UPDATE; devuelve la primera fila si hay RETURNING."""
    with pool.connection() as c:
        cur = c.execute(sql, params)
        return cur.fetchone() if cur.description else None


def registrar_acceso(usuario_id, paciente_id, accion, ip=None):
    try:
        ip = str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        ip = None
    ejecutar(
        "INSERT INTO bitacora_acceso (usuario_id, paciente_id, accion, ip) VALUES (%s,%s,%s,%s)",
        [usuario_id, paciente_id, accion, ip],
    )
