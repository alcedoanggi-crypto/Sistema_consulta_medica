# Cómo se hizo MediAgenda

Este documento explica, paso a paso, cómo está construido el sistema y qué hace cada parte del código. Está pensado para que cualquier persona (reclutador, desarrollador o estudiante) pueda entender el proyecto completo sin tener que leer todos los archivos.

---

## Índice

1. [Objetivo y decisiones de diseño](#1-objetivo-y-decisiones-de-diseño)
2. [Arquitectura](#2-arquitectura)
3. [Paso 1 · Infraestructura con Docker](#3-paso-1--infraestructura-con-docker)
4. [Paso 2 · La base de datos (el corazón del proyecto)](#4-paso-2--la-base-de-datos)
5. [Paso 3 · El backend con FastAPI](#5-paso-3--el-backend-con-fastapi)
6. [Paso 4 · El frontend con React](#6-paso-4--el-frontend-con-react)
7. [Paso 5 · Datos de demostración](#7-paso-5--datos-de-demostración)
8. [Paso 6 · Pruebas automáticas](#8-paso-6--pruebas-automáticas)
9. [Problemas encontrados y cómo se resolvieron](#9-problemas-encontrados-y-cómo-se-resolvieron)
10. [Lo que aprendí](#10-lo-que-aprendí)

---

## 1. Objetivo y decisiones de diseño

El objetivo era un sistema para consultorios médicos, dentales o de psicología con agenda, expediente clínico, recetas, cobros e inventario, **poniendo el foco en la seguridad de los datos de salud**.

Las decisiones principales fueron:

| Decisión | Motivo |
|---|---|
| **Las reglas críticas viven en PostgreSQL** | Si la regla solo estuviera en la API, un error de programación, un script o un acceso directo a la base podría saltársela. En la base de datos se cumple siempre. |
| **SQL directo con psycopg 3 (sin ORM)** | El proyecto usa funciones avanzadas de PostgreSQL (rangos de tiempo, `EXCLUDE`, `pgcrypto`, triggers) que se ven y se entienden mejor en SQL puro. |
| **FastAPI** | Valida los datos con Pydantic y genera documentación interactiva automática en `/docs`. |
| **React + Vite + Tailwind** | Desarrollo rápido, recarga instantánea y estilos consistentes sin escribir CSS a mano. |
| **FullCalendar** | Es el calendario más completo para arrastrar y soltar, con vistas de día, semana y mes. |
| **Docker solo para la base de datos** | El backend y el frontend corren normal en la máquina para facilitar el desarrollo; PostgreSQL y los respaldos van en contenedores. |

---

## 2. Arquitectura

```
┌────────────────────┐   /api (proxy de Vite)    ┌────────────────────┐    SQL     ┌──────────────────────┐
│  React + Vite      │ ────────────────────────▶ │  FastAPI           │ ─────────▶ │  PostgreSQL 17       │
│  puerto 5200       │ ◀──────── JSON ────────── │  puerto 8010       │ ◀───────── │  puerto 5435         │
│  FullCalendar,     │                           │  JWT, roles,       │            │  pgcrypto, EXCLUDE,  │
│  Recharts          │                           │  PDF, recordatorios│            │  triggers, vistas    │
└────────────────────┘                           └─────────┬──────────┘            └──────────┬───────────┘
                                                           │ correo / .eml                    │ pg_dump diario
                                                           ▼                                  ▼
                                                     Paciente (enlaces                 ./backups (7 últimos)
                                                     confirmar/cancelar)
```

**Flujo de una petición típica** (por ejemplo, abrir un expediente):

1. React llama a `GET /api/pacientes/1/expediente` y envía el token JWT en la cabecera `Authorization`.
2. FastAPI valida el token y comprueba que el rol sea médico o administrador.
3. Se registra el acceso en la bitácora.
4. PostgreSQL descifra los campos usando la clave de la sesión y devuelve los datos.
5. React dibuja las notas, las gráficas y las recetas.

---

## 3. Paso 1 · Infraestructura con Docker

**Archivo:** [`docker-compose.yml`](../docker-compose.yml)

Se definen dos servicios:

- **`db`**: PostgreSQL 17. Al arrancar por primera vez ejecuta automáticamente los archivos de `db/init/` (el esquema y el catálogo CIE-10). Solo escucha en `127.0.0.1:5435`, así que no queda expuesto a la red. Tiene un *healthcheck* para saber cuándo está listo.
- **`backup`**: usa la misma imagen de PostgreSQL solo para tener `pg_dump`. Espera a que `db` esté sano y ejecuta [`db/backup.sh`](../db/backup.sh):

```sh
while true; do
  f="/backups/mediagenda_$(date +%Y%m%d_%H%M%S).dump"
  pg_dump -Fc -f "$f"                                         # formato comprimido, se restaura con pg_restore
  ls -1t /backups/*.dump | tail -n +8 | xargs -r rm -f         # rotación: conserva los 7 más recientes
  sleep "${BACKUP_INTERVAL:-86400}"                           # cada 24 h
done
```

El intervalo se puede cambiar con la variable `BACKUP_INTERVAL`, por ejemplo 3600 para hacer un respaldo cada hora.

---

## 4. Paso 2 · La base de datos

**Archivos:** [`db/init/001_schema.sql`](../db/init/001_schema.sql) y [`db/init/002_cie10.sql`](../db/init/002_cie10.sql)

### 4.1 Extensiones

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- cifrado (pgp_sym_encrypt) y hash de contraseñas (crypt)
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- permite usar "=" sobre enteros en un índice GiST
```

### 4.2 Cifrado de datos sensibles

Se crearon dos funciones para no repetir la lógica en cada consulta:

```sql
CREATE FUNCTION cifrar(t text) RETURNS bytea AS $$
  SELECT CASE WHEN t IS NULL OR t = '' THEN NULL
              ELSE pgp_sym_encrypt(t, current_setting('app.clave_cifrado'), 'cipher-algo=aes256') END
$$ LANGUAGE sql;

CREATE FUNCTION descifrar(b bytea) RETURNS text AS $$
  SELECT CASE WHEN b IS NULL THEN NULL
              ELSE pgp_sym_decrypt(b, current_setting('app.clave_cifrado')) END
$$ LANGUAGE sql;
```

**¿De dónde sale la clave?** No está en la base de datos. El backend la tiene en su archivo `.env` y la entrega al abrir cada conexión:

```python
conn.execute("SELECT set_config('app.clave_cifrado', %s, false)", [config.CLAVE_CIFRADO])
```

Así, quien robe un respaldo `.dump` o entre a la base con otro programa solo ve bytes ilegibles. Si la clave no está configurada, `current_setting()` lanza un error: el sistema **falla cerrado**, nunca muestra el dato sin cifrar por accidente.

Las columnas cifradas llevan el sufijo `_cif` y son de tipo `bytea`. En el [README](../README.md#1-cifrado-en-reposo-con-pgcrypto) está la tabla con qué se cifra y por qué.

**Contraseñas:** no se cifran (eso sería reversible). Se guardan con un *hash* bcrypt de pgcrypto y la comparación también ocurre en la base:

```sql
-- al crear el usuario
INSERT INTO usuarios (..., password_hash) VALUES (..., crypt('admin123', gen_salt('bf')));
-- al iniciar sesión
SELECT ... FROM usuarios WHERE email = $1 AND password_hash = crypt($2, password_hash);
```

### 4.3 Agenda sin citas encimadas (`EXCLUDE` + `tstzrange`)

La tabla `citas` guarda el horario como **un solo valor de tipo rango**, no como dos columnas `inicio` y `fin`:

```sql
CREATE TABLE citas (
  id        serial PRIMARY KEY,
  tipo      text NOT NULL DEFAULT 'cita' CHECK (tipo IN ('cita','bloqueo')),
  medico_id int  NOT NULL REFERENCES usuarios(id),
  rango     tstzrange NOT NULL,                 -- ej: ['2026-11-10 09:00-04', '2026-11-10 09:30-04')
  estado    text NOT NULL DEFAULT 'programada',
  ...
  CONSTRAINT cita_sin_solape_medico
    EXCLUDE USING gist (medico_id WITH =, rango WITH &&)
    WHERE (estado <> 'cancelada')
);
```

Cómo se lee la restricción: *«Rechaza cualquier fila nueva si ya existe otra con el **mismo** `medico_id` (`=`) **y** un `rango` que se **solape** (`&&`), sin contar las canceladas».*

- `[inicio, fin)` incluye el inicio y excluye el fin, por eso dos citas seguidas (9:00–9:30 y 9:30–10:00) **sí** se permiten.
- El índice GiST hace la verificación rápida aunque haya miles de citas.
- **Los bloqueos de horario** (almuerzo, congresos) están en la misma tabla con `tipo = 'bloqueo'`, así que la misma restricción impide agendar encima de ellos sin escribir código adicional.
- Existe una segunda restricción igual para `consultorio_id`, para que un consultorio no tenga dos citas a la vez.
- **Concurrencia:** si dos pacientes intentan reservar el mismo horario en el mismo instante, PostgreSQL deja pasar a uno y al otro le devuelve el error `exclusion_violation`. Revisar disponibilidad en la API («¿está libre?» y luego «insertar») no evita esa carrera; la restricción sí.

**Horarios disponibles calculados en SQL:**

```sql
CREATE FUNCTION horarios_disponibles(p_medico int, p_fecha date, p_duracion int DEFAULT 30)
RETURNS TABLE (inicio timestamptz, fin timestamptz) AS $$
  SELECT s, s + make_interval(mins => p_duracion)
  FROM generate_series(<08:00 de ese día>, <17:00 - duración>, <duración>) AS s   -- todos los turnos posibles
  WHERE s > now()                                                                  -- solo futuros
    AND NOT EXISTS (SELECT 1 FROM citas c                                          -- que no choquen
                    WHERE c.medico_id = p_medico AND c.estado <> 'cancelada'
                      AND c.rango && tstzrange(s, s + make_interval(mins => p_duracion)))
$$ LANGUAGE sql STABLE;
```

`generate_series` genera todos los turnos del día y el `NOT EXISTS` descarta los que se solapan con algo. Lo usa el portal del paciente.

### 4.4 Notas clínicas firmadas inmutables

```sql
CREATE FUNCTION proteger_nota_firmada() RETURNS trigger AS $$
BEGIN
  IF OLD.firmada THEN
    RAISE EXCEPTION 'La nota % está firmada: no se puede % (agregue una adenda)', OLD.id, lower(TG_OP)
      USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  IF NEW.firmada THEN NEW.firmada_en := now(); END IF;      -- sella la fecha de la firma
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_nota_firmada BEFORE UPDATE OR DELETE ON notas_clinicas
  FOR EACH ROW EXECUTE FUNCTION proteger_nota_firmada();
```

- Mientras la nota es **borrador**, se puede editar.
- En el momento de firmarla (`UPDATE ... SET firmada = true`) el trigger todavía lo permite, porque `OLD.firmada` es falso, y guarda la hora en `firmada_en`.
- A partir de ahí cualquier `UPDATE` o `DELETE` falla.
- Las **adendas** tienen dos triggers. Uno solo permite insertarlas si la nota está firmada; el otro bloquea siempre su modificación o borrado.
- Los **diagnósticos** de una nota firmada tampoco se pueden cambiar.

Se usó `ERRCODE = 'check_violation'` a propósito: así el backend reconoce el error y lo devuelve al usuario como un mensaje claro (HTTP 409).

### 4.5 Bitácora de acceso

```sql
CREATE TABLE bitacora_acceso (
  id bigserial PRIMARY KEY, usuario_id int NOT NULL, paciente_id int,
  accion text NOT NULL, ip inet, creado timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_bitacora_inmutable    BEFORE UPDATE OR DELETE ON bitacora_acceso FOR EACH ROW       EXECUTE FUNCTION bloquear_modificacion();
CREATE TRIGGER trg_bitacora_sin_truncate BEFORE TRUNCATE         ON bitacora_acceso FOR EACH STATEMENT EXECUTE FUNCTION bloquear_modificacion();
```

Es de **solo inserción**. El trigger de `TRUNCATE` es necesario porque `TRUNCATE` no dispara triggers por fila: sin él se podría vaciar la tabla de un golpe. La función `bloquear_modificacion()` se reutiliza también en `adendas` y `recetas`.

### 4.6 Facturación e inventario con vistas

En lugar de guardar el saldo en una columna (que se puede desincronizar), se calcula siempre con una **vista**:

```sql
CREATE VIEW v_saldos AS
SELECT p.id AS paciente_id, ..., COALESCE(c.total,0) - COALESCE(g.total,0) AS saldo
FROM pacientes p
LEFT JOIN (SELECT paciente_id, sum(monto) total FROM cargos GROUP BY 1) c ON ...
LEFT JOIN (SELECT paciente_id, sum(monto) total FROM pagos  GROUP BY 1) g ON ...;
```

Las alertas de inventario se resuelven igual, con la vista `v_alertas_inventario`, que clasifica cada artículo en `caducado`, `por_caducar` (30 días o menos) o `stock_bajo`. El `CHECK (stock >= 0)` de la tabla impide sacar más unidades de las que hay.

### 4.7 Zona horaria

Todas las fechas se guardan como `timestamptz` (con zona horaria). La base se configura con la zona `America/Caracas` para que funciones como `current_date` o `::date` (citas de hoy, corte de caja) usen la hora local y no la UTC.

---

## 5. Paso 3 · El backend con FastAPI

**Carpeta:** [`backend/app/`](../backend/app)

### 5.1 Configuración: `config.py`

Lee el archivo `.env` con `python-dotenv`. Ahí van la URL de la base, la clave de cifrado, el secreto JWT, los datos SMTP y la URL pública que se usa en los QR y en los enlaces de los correos. El `.env` real **no se sube** a GitHub; solo `.env.example`.

### 5.2 Conexión: `db.py`

```python
pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=10,
                      kwargs={"row_factory": dict_row},   # cada fila llega como diccionario → JSON directo
                      configure=_configurar,              # se ejecuta al crear cada conexión: envía la clave
                      open=False)
```

Se crearon tres funciones de ayuda, `todos()`, `uno()` y `ejecutar()`, para que los *routers* queden cortos. Cuando hay que hacer varias operaciones en una misma transacción se usa `with pool.connection() as c:`: todo se confirma junto al salir del bloque, o se revierte junto si ocurre un error.

`registrar_acceso()` escribe en la bitácora. Antes valida la IP con el módulo `ipaddress`, porque la columna es de tipo `inet` y no acepta textos cualquiera.

### 5.3 Autenticación y roles: `auth.py`

- `autenticar()` verifica el correo y la contraseña con `crypt()` dentro de PostgreSQL.
- `crear_token()` firma un JWT (HS256) con el id y el rol del usuario, válido por 10 horas.
- `usuario_actual()` es una **dependencia** de FastAPI: lee el token, lo valida y busca al usuario. Si está desactivado, rechaza la petición.
- `requiere(*roles)` devuelve una dependencia que exige ciertos roles. Se usa así:

```python
STAFF   = ("admin", "medico", "recepcion")
CLINICO = ("admin", "medico")          # recepción NUNCA ve contenido clínico

@router.get("/pacientes/{pid}/expediente")
def expediente(pid: int, request: Request, u=Depends(requiere(*CLINICO))):
    ...
```

### 5.4 Routers (los endpoints)

| Archivo | Endpoints principales | Detalles |
|---|---|---|
| [`publico.py`](../backend/app/routers/publico.py) | `POST /auth/login`, `POST /auth/registro`, `GET /publico/citas/{token}/confirmar\|cancelar`, `GET /publico/recetas/{codigo}` | Son los únicos endpoints sin sesión. Los enlaces del correo usan un `token` UUID aleatorio de cada cita, no su id, para que no se puedan adivinar. La verificación de recetas solo muestra las iniciales del paciente y nunca los medicamentos. |
| [`pacientes.py`](../backend/app/routers/pacientes.py) | CRUD de pacientes, `GET /pacientes/{id}/expediente`, archivos | La consulta de datos generales **no selecciona** las columnas clínicas. El expediente junta notas, adendas y diagnósticos en **una sola consulta** con `json_agg` y registra el acceso. Archivos: recepción solo puede subir o ver `documento`, nunca `estudio`. |
| [`agenda.py`](../backend/app/routers/agenda.py) | `GET/POST/PATCH /citas`, `/disponibilidad`, `/lista-espera`, `/portal/*` | El `PATCH` sirve tanto para arrastrar y soltar (cambia el rango) como para cambiar el estado. Al marcar una cita como **completada** se crea el cargo del servicio automáticamente; al **cancelarla** se devuelven sugerencias de la lista de espera. Cada médico solo ve su propia agenda. |
| [`expediente.py`](../backend/app/routers/expediente.py) | `/notas`, `/notas/{id}/firmar`, `/notas/{id}/adendas`, `/signos`, `/recetas`, `/recetas/{id}/pdf`, `/cie10`, `/bitacora` | Solo el médico autor puede editar o firmar su borrador. El PDF lo puede descargar el personal clínico o el propio paciente dueño de la receta. |
| [`gestion.py`](../backend/app/routers/gestion.py) | `/servicios`, `/cargos`, `/pagos`, `/saldos`, `/caja/corte`, `/inventario`, `/dashboard`, `/usuarios` | El dashboard calcula todos los indicadores en una sola consulta con subconsultas. La tasa de inasistencia usa `count(*) FILTER (WHERE ...)`. Los ingresos por día usan `generate_series` para que los días sin pagos aparezcan en 0. |

### 5.5 Errores de PostgreSQL → respuestas HTTP: `main.py`

Como las reglas las hace cumplir la base de datos, la API solo tiene que **traducir** sus errores:

```python
@app.exception_handler(errors.ExclusionViolation)       # cita encimada
def solape(request, exc):
    return JSONResponse(status_code=409, content={"detail": "Ese horario se encima con otra cita..."})

@app.exception_handler(errors.CheckViolation)           # nota firmada, stock negativo, etc.
def regla(request, exc):
    return JSONResponse(status_code=409, content={"detail": exc.diag.message_primary})
```

`main.py` también abre el pool al arrancar y lanza el hilo de recordatorios usando el `lifespan` de FastAPI.

### 5.6 Recetas en PDF: `pdf.py`

Se dibujan con **ReportLab** sobre un *canvas* tamaño carta:

1. Encabezado de color con el nombre de la clínica, el médico, su especialidad y su **cédula profesional**.
2. Datos del paciente con la edad calculada y la fecha.
3. El símbolo «Rx» y las indicaciones, con las líneas largas cortadas a 85 caracteres.
4. Un **código QR** generado con la librería `qrcode` que apunta a `/api/publico/recetas/{codigo_verificacion}`.
5. La línea de firma.

El código de verificación es un UUID que genera PostgreSQL (`gen_random_uuid()`), así que es imposible de adivinar.

### 5.7 Recordatorios automáticos: `recordatorios.py`

Un hilo en segundo plano revisa cada 60 segundos:

```sql
SELECT ... FROM citas c ...
WHERE c.tipo='cita' AND c.estado='programada' AND NOT c.recordatorio_enviado
  AND lower(c.rango) BETWEEN now() AND now() + interval '24 hours'
```

Para cada cita arma un correo con los enlaces de **confirmar** y **cancelar**.

- Si hay SMTP configurado, lo envía. Si no, lo guarda como archivo `.eml` en `backend/outbox/` para poder revisarlo en desarrollo.
- Si existe `WHATSAPP_API_URL`, también envía el mensaje a ese servicio.
- Después marca `recordatorio_enviado = true` para no repetirlo.
- Si se reprograma la cita arrastrándola en el calendario, la marca vuelve a `false` y se enviará un recordatorio nuevo.

---

## 6. Paso 4 · El frontend con React

**Carpeta:** [`frontend/src/`](../frontend/src)

### 6.1 Configuración

- [`vite.config.js`](../frontend/vite.config.js): plugins de React y Tailwind 4, y un **proxy**: todo lo que empieza con `/api` se reenvía al backend en el puerto 8010. Así el navegador cree que todo viene del mismo origen y no hay problemas de CORS.
- [`index.css`](../frontend/src/index.css): `@import "tailwindcss"`, un foco visible para navegar con teclado y la adaptación de los colores de FullCalendar a la paleta de la app. Los bloqueos se ven con rayas diagonales.

### 6.2 `api.js`: cliente HTTP

Una sola función `api(ruta, opciones)`:

- agrega el token automáticamente;
- convierte el cuerpo a JSON o envía `FormData` cuando se suben archivos;
- si la respuesta es 401, cierra la sesión y lleva al login;
- si hay error, lanza el mensaje que vino de la API para mostrarlo en pantalla.

`abrirArchivo()` descarga PDFs y adjuntos como *blob* (con el token) y los abre en otra pestaña. También están ahí los formateadores de dinero y de fechas en español.

### 6.3 `App.jsx`: rutas, sesión y menú

- Un **Context** de React guarda el usuario conectado y las funciones `entrar` y `salir`.
- `<Protegida roles=[...]>` es un componente que redirige si el usuario no tiene sesión o no tiene el rol adecuado. El paciente, por ejemplo, siempre termina en `/portal`.
- El menú lateral se filtra según el rol y en el celular se convierte en un menú desplegable. Incluye un enlace oculto «Saltar al contenido» para lectores de pantalla.

### 6.4 `components/ui.jsx`: componentes reutilizables

`Card`, `Button` (variantes primary, secondary, danger y ghost), `Field`, `Input`, `Select`, `Textarea`, `Modal` (se cierra con Escape o haciendo clic fuera, y tiene `role="dialog"`), `Badge` (color según el estado), `Kpi`, `Aviso` (con `role="alert"`) y `Tabla` (recibe columnas con formateadores opcionales).

### 6.5 Páginas

| Página | Qué hace y cómo |
|---|---|
| **Login** | Iniciar sesión o registrarse como paciente. Tiene botones de cuentas demo que entran con un clic. |
| **Dashboard** | Indicadores, agenda de hoy y dos gráficas de barras con Recharts (servicios más pedidos e ingresos de 14 días). |
| **Agenda** | FullCalendar con `timeGridDay`, `timeGridWeek` y `dayGridMonth`. Los eventos se piden a la API según el rango visible. `select` abre el formulario de cita o bloqueo. `eventDrop` y `eventResize` envían el `PATCH`; si la API responde 409, se llama a `revert()` y la cita vuelve a su lugar. Al lado está la lista de espera. |
| **Pacientes / Paciente** | Búsqueda con *debounce* de 250 ms. La ficha tiene pestañas: el **expediente** (solo médico y admin) muestra las notas SOAP con su estado (borrador o firmada), las adendas, la búsqueda CIE-10, las gráficas de signos vitales con `LineChart`, las recetas y las alergias resaltadas en rojo. Las pestañas de **archivos** y **cuenta** registran pagos y cargos. |
| **Caja** | Corte del día por método de pago, lista de pagos y saldos pendientes. Se puede imprimir. |
| **Inventario** | Tabla con alertas, ajuste rápido con los botones + y −, y formulario de alta o edición. |
| **Bitácora** | Solo para el administrador: quién abrió qué expediente, cuándo y desde qué IP. |
| **Portal (paciente)** | Elige especialista, servicio y fecha, y ve los horarios libres, que se vuelven a consultar cada 15 s con `setInterval`. Desde ahí reserva, cancela y descarga sus recetas. |

---

## 7. Paso 5 · Datos de demostración

**Archivo:** [`backend/app/seed.py`](../backend/app/seed.py). Se ejecuta con `python -m app.seed --reset`.

1. `--reset` borra el esquema `public` y vuelve a ejecutar los SQL de `db/init/`.
2. Crea 3 consultorios, 6 servicios, 6 usuarios del personal y 20 pacientes con datos cifrados.
3. Genera la agenda de 45 días atrás y 10 días adelante, de lunes a viernes. Avanza turno por turno, salta el bloqueo del almuerzo y ocupa cerca del 55 % de los turnos. Las citas pasadas quedan completadas, como inasistencias o canceladas; las completadas generan su cargo, y cerca del 85 % tienen su pago, para que haya saldos pendientes que mostrar.
4. Crea el expediente completo de María González: 3 notas SOAP firmadas con diagnósticos CIE-10, una adenda, un borrador, 6 registros de signos vitales que muestran la mejora de su presión arterial, y una receta.
5. Carga el inventario con artículos caducados, por caducar y con poco stock, y la lista de espera.

Se usa `random.seed(7)` para que la demo salga siempre igual.

---

## 8. Paso 6 · Pruebas automáticas

**Carpeta:** [`backend/tests/`](../backend/tests)

- `conftest.py` crea una base **aparte**, `mediagenda_test`, la recrea con el *seed* y entrega fixtures con el token de cada rol.
- `test_reglas.py` tiene 16 pruebas que usan el `TestClient` de FastAPI y, en algunos casos, conexión directa a PostgreSQL para comprobar que la regla se cumple **aunque se salte la API**:

| Prueba | Qué demuestra |
|---|---|
| `test_no_permite_citas_encimadas` | Un solape devuelve 409, pero una cita contigua sí se permite. |
| `test_bloqueo_impide_citas` | No se puede agendar encima de un bloqueo. |
| `test_cancelada_libera_horario` | Cancelar una cita libera el horario. |
| `test_reserva_en_linea_y_disponibilidad` | El horario reservado desaparece de la disponibilidad y una segunda reserva igual recibe 409. |
| `test_recepcion_no_ve_contenido_clinico` | Recepción recibe 403 en expediente, CIE-10 y notas, y los datos generales no incluyen alergias. |
| `test_paciente_no_entra_al_sistema_interno` | El paciente recibe 403 en el sistema interno. |
| `test_abrir_expediente_queda_en_bitacora` | Abrir un expediente agrega una fila a la bitácora. |
| `test_nota_firmada_es_inmutable` | Editar una nota firmada devuelve 409; la adenda funciona y el texto original se conserva. |
| `test_bitacora_no_se_puede_alterar` (×3) | `DELETE`, `UPDATE` y `TRUNCATE` directos en SQL fallan. |
| `test_datos_cifrados_en_reposo` | Los bytes guardados no contienen el texto y sin la clave no se pueden descifrar. |
| `test_receta_pdf_y_verificacion` | El PDF es válido, la paciente puede descargarlo y la página de verificación no revela los medicamentos. |
| `test_completar_cita_genera_cargo_y_saldo` | El cargo es automático, el saldo vuelve a 0 después del pago y el corte de caja lo incluye. |
| `test_inventario_alertas_y_sin_negativos` | Aparecen las tres alertas y el stock no puede quedar negativo. |
| `test_recordatorio_y_enlace_de_confirmacion` | Se genera el `.eml` y los enlaces de confirmar y cancelar funcionan. |

```
16 passed in 14.04s
```

---

## 9. Problemas encontrados y cómo se resolvieron

| Problema | Causa | Solución |
|---|---|---|
| El contenedor de la base salía *unhealthy* la primera vez | La primera inicialización en un equipo lento tardaba más que el *healthcheck* | Se subieron los reintentos a 30 y se agregó `start_period: 60s`. |
| La carga de datos demo se quedaba colgada | Una conexión anterior quedó abierta («idle in transaction») y bloqueaba el `DROP SCHEMA` | Se cierran las sesiones abiertas con `pg_terminate_backend` y se detiene la API antes de recargar. Después de eso la carga tarda unos 25 s. |
| Error `invalid input syntax for type inet: "testclient"` | En las pruebas, el cliente de FastAPI no tiene una IP real | `registrar_acceso()` valida la IP con `ipaddress` y guarda `NULL` si no es válida. |
| La prueba de «no se puede borrar la bitácora» no fallaba | Un `DELETE` sobre una tabla vacía no dispara triggers por fila, y además `TRUNCATE` no los dispara nunca | La prueba inserta una fila antes, y se agregó un trigger `BEFORE TRUNCATE ... FOR EACH STATEMENT`. |
| El script `ALTER DATABASE mediagenda` no servía para la base de pruebas | El nombre de la base estaba escrito a mano | Se usa `EXECUTE format('ALTER DATABASE %I ...', current_database())`. |

---

## 10. Lo que aprendí

- **Las restricciones de la base de datos son la última línea de defensa.** `EXCLUDE` resuelve en una línea un problema de concurrencia que en código sería frágil.
- Los **rangos de tiempo** (`tstzrange`) simplifican mucho la lógica de agendas: solape, contigüidad e índices vienen incluidos.
- **Cifrar no es todo o nada:** hay que decidir campo por campo, equilibrando la privacidad con la necesidad de buscar y contactar.
- Un registro clínico necesita **trazabilidad**: notas inmutables, adendas con autor y fecha, y una bitácora que nadie puede borrar.
- Las pruebas deben comprobar las reglas **también saltándose la API**, conectándose directo a la base, para demostrar que de verdad están en la base de datos.
