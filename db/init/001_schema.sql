-- =====================================================================
-- MediAgenda · Esquema PostgreSQL
-- Las reglas críticas viven en la base de datos (no solo en la API):
--   * cifrado en reposo con pgcrypto
--   * EXCLUDE con tstzrange contra citas encimadas
--   * notas clínicas firmadas inmutables (solo adendas)
--   * bitácora de acceso de solo inserción
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- cifrado y hashing
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- permite "=" sobre enteros dentro de un índice GiST

DO $$ BEGIN
  EXECUTE format('ALTER DATABASE %I SET timezone = %L', current_database(), 'America/Caracas');
END $$;
SET timezone = 'America/Caracas';

-- ---------------------------------------------------------------------
-- Cifrado: la clave NO se guarda en la base. La API la envía en cada
-- conexión con  SELECT set_config('app.clave_cifrado', <clave>, false).
-- Si falta, current_setting() lanza error: falla cerrada, nunca en claro.
-- ---------------------------------------------------------------------
CREATE FUNCTION cifrar(t text) RETURNS bytea LANGUAGE sql AS $$
  SELECT CASE WHEN t IS NULL OR t = '' THEN NULL
              ELSE pgp_sym_encrypt(t, current_setting('app.clave_cifrado'), 'cipher-algo=aes256') END
$$;

CREATE FUNCTION descifrar(b bytea) RETURNS text LANGUAGE sql AS $$
  SELECT CASE WHEN b IS NULL THEN NULL
              ELSE pgp_sym_decrypt(b, current_setting('app.clave_cifrado')) END
$$;

-- Función genérica para tablas de solo inserción
CREATE FUNCTION bloquear_modificacion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'La tabla % es de solo inserción: no se permite %', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'check_violation';
END $$;

-- ---------------------------------------------------------------------
-- Catálogos
-- ---------------------------------------------------------------------
CREATE TABLE consultorios (
  id     serial PRIMARY KEY,
  nombre text NOT NULL UNIQUE
);

CREATE TABLE servicios (
  id           serial PRIMARY KEY,
  nombre       text NOT NULL UNIQUE,
  precio       numeric(10,2) NOT NULL CHECK (precio >= 0),
  duracion_min int NOT NULL DEFAULT 30 CHECK (duracion_min > 0),
  activo       boolean NOT NULL DEFAULT true
);

CREATE TABLE cie10 (
  codigo      text PRIMARY KEY,
  descripcion text NOT NULL
);

-- ---------------------------------------------------------------------
-- Pacientes (campos sensibles cifrados: sufijo _cif, tipo bytea)
-- ---------------------------------------------------------------------
CREATE TABLE pacientes (
  id                  serial PRIMARY KEY,
  nombre              text NOT NULL,
  apellido            text NOT NULL,
  fecha_nacimiento    date,
  sexo                text CHECK (sexo IN ('F','M','O')),
  email               text,
  telefono            text,
  direccion           text,
  documento_cif       bytea,   -- cédula / pasaporte: robo de identidad
  emergencia_nombre   text,
  emergencia_telefono text,
  alergias_cif        bytea,   -- dato clínico
  antecedentes_cif    bytea,   -- dato clínico
  creado              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON pacientes (lower(apellido), lower(nombre));

-- ---------------------------------------------------------------------
-- Usuarios y roles. Contraseñas con crypt() + bcrypt de pgcrypto.
-- ---------------------------------------------------------------------
CREATE TABLE usuarios (
  id                 serial PRIMARY KEY,
  nombre             text NOT NULL,
  email              text NOT NULL UNIQUE,
  password_hash      text NOT NULL,
  rol                text NOT NULL CHECK (rol IN ('admin','medico','recepcion','paciente')),
  especialidad       text,
  cedula_profesional text,
  color              text DEFAULT '#0d9488',
  paciente_id        int REFERENCES pacientes(id),
  activo             boolean NOT NULL DEFAULT true,
  CHECK (rol <> 'paciente' OR paciente_id IS NOT NULL),
  CHECK (rol <> 'medico' OR cedula_profesional IS NOT NULL)
);

-- ---------------------------------------------------------------------
-- Agenda: citas y bloqueos de horario en UNA tabla, para que la misma
-- restricción EXCLUDE impida encimar una cita sobre un bloqueo.
-- ---------------------------------------------------------------------
CREATE TABLE citas (
  id                   serial PRIMARY KEY,
  tipo                 text NOT NULL DEFAULT 'cita' CHECK (tipo IN ('cita','bloqueo')),
  medico_id            int  NOT NULL REFERENCES usuarios(id),
  consultorio_id       int  REFERENCES consultorios(id),
  paciente_id          int  REFERENCES pacientes(id),
  servicio_id          int  REFERENCES servicios(id),
  rango                tstzrange NOT NULL,          -- [inicio, fin)  fin excluido
  estado               text NOT NULL DEFAULT 'programada'
                       CHECK (estado IN ('programada','confirmada','completada','cancelada','no_asistio')),
  motivo               text,
  origen               text NOT NULL DEFAULT 'recepcion' CHECK (origen IN ('recepcion','en_linea')),
  token                uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,  -- enlace de confirmar/cancelar
  recordatorio_enviado boolean NOT NULL DEFAULT false,
  creado               timestamptz NOT NULL DEFAULT now(),

  CHECK (tipo = 'bloqueo' OR paciente_id IS NOT NULL),
  CHECK (NOT isempty(rango) AND lower_inc(rango) AND NOT upper_inc(rango)),

  -- Ningún médico puede tener dos citas/bloqueos activos que se solapen
  CONSTRAINT cita_sin_solape_medico
    EXCLUDE USING gist (medico_id WITH =, rango WITH &&)
    WHERE (estado <> 'cancelada'),

  -- Ni un consultorio dos citas a la vez
  CONSTRAINT cita_sin_solape_consultorio
    EXCLUDE USING gist (consultorio_id WITH =, rango WITH &&)
    WHERE (estado <> 'cancelada' AND consultorio_id IS NOT NULL)
);
CREATE INDEX ON citas (paciente_id);

CREATE TABLE lista_espera (
  id          serial PRIMARY KEY,
  paciente_id int NOT NULL REFERENCES pacientes(id),
  medico_id   int REFERENCES usuarios(id),
  preferencia text,
  atendida    boolean NOT NULL DEFAULT false,
  creado      timestamptz NOT NULL DEFAULT now()
);

-- Horarios libres de un médico en un día (08:00-17:00, hora local)
CREATE FUNCTION horarios_disponibles(p_medico int, p_fecha date, p_duracion int DEFAULT 30)
RETURNS TABLE (inicio timestamptz, fin timestamptz) LANGUAGE sql STABLE AS $$
  SELECT s, s + make_interval(mins => p_duracion)
  FROM generate_series(
         (p_fecha + time '08:00')::timestamp AT TIME ZONE 'America/Caracas',
         (p_fecha + time '17:00')::timestamp AT TIME ZONE 'America/Caracas' - make_interval(mins => p_duracion),
         make_interval(mins => p_duracion)) AS s
  WHERE s > now()
    AND NOT EXISTS (
      SELECT 1 FROM citas c
      WHERE c.medico_id = p_medico AND c.estado <> 'cancelada'
        AND c.rango && tstzrange(s, s + make_interval(mins => p_duracion)))
$$;

-- ---------------------------------------------------------------------
-- Expediente clínico
-- ---------------------------------------------------------------------
CREATE TABLE notas_clinicas (
  id             serial PRIMARY KEY,
  paciente_id    int NOT NULL REFERENCES pacientes(id),
  medico_id      int NOT NULL REFERENCES usuarios(id),
  cita_id        int REFERENCES citas(id),
  subjetivo_cif  bytea,   -- S: lo que refiere el paciente
  objetivo_cif   bytea,   -- O: exploración
  evaluacion_cif bytea,   -- A: análisis / impresión diagnóstica
  plan_cif       bytea,   -- P: tratamiento
  firmada        boolean NOT NULL DEFAULT false,
  firmada_en     timestamptz,
  creado         timestamptz NOT NULL DEFAULT now()
);

-- Una nota firmada es inmutable: ni UPDATE ni DELETE.
-- Mientras es borrador se puede editar; al firmarla se sella la fecha.
CREATE FUNCTION proteger_nota_firmada() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.firmada THEN
    RAISE EXCEPTION 'La nota % está firmada: no se puede % (agregue una adenda)', OLD.id, lower(TG_OP)
      USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  IF NEW.firmada THEN NEW.firmada_en := now(); END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_nota_firmada BEFORE UPDATE OR DELETE ON notas_clinicas
  FOR EACH ROW EXECUTE FUNCTION proteger_nota_firmada();

CREATE TABLE adendas (
  id        serial PRIMARY KEY,
  nota_id   int NOT NULL REFERENCES notas_clinicas(id),
  autor_id  int NOT NULL REFERENCES usuarios(id),
  texto_cif bytea NOT NULL,
  creado    timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION adenda_solo_nota_firmada() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT (SELECT firmada FROM notas_clinicas WHERE id = NEW.nota_id) THEN
    RAISE EXCEPTION 'Las adendas solo aplican a notas firmadas; edite el borrador'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_adenda_insert BEFORE INSERT ON adendas
  FOR EACH ROW EXECUTE FUNCTION adenda_solo_nota_firmada();
CREATE TRIGGER trg_adenda_inmutable BEFORE UPDATE OR DELETE ON adendas
  FOR EACH ROW EXECUTE FUNCTION bloquear_modificacion();

CREATE TABLE diagnosticos (
  id      serial PRIMARY KEY,
  nota_id int  NOT NULL REFERENCES notas_clinicas(id) ON DELETE CASCADE,
  codigo  text NOT NULL REFERENCES cie10(codigo),
  tipo    text NOT NULL DEFAULT 'principal' CHECK (tipo IN ('principal','secundario')),
  UNIQUE (nota_id, codigo)
);
CREATE FUNCTION diagnostico_nota_abierta() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT firmada FROM notas_clinicas WHERE id = COALESCE(NEW.nota_id, OLD.nota_id)) THEN
    RAISE EXCEPTION 'No se pueden cambiar diagnósticos de una nota firmada'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN COALESCE(NEW, OLD);
END $$;
CREATE TRIGGER trg_diagnostico BEFORE INSERT OR UPDATE OR DELETE ON diagnosticos
  FOR EACH ROW EXECUTE FUNCTION diagnostico_nota_abierta();

CREATE TABLE signos_vitales (
  id             serial PRIMARY KEY,
  paciente_id    int NOT NULL REFERENCES pacientes(id),
  registrado_por int REFERENCES usuarios(id),
  fecha          timestamptz NOT NULL DEFAULT now(),
  peso_kg        numeric(5,1) CHECK (peso_kg BETWEEN 0.5 AND 400),
  talla_cm       numeric(5,1) CHECK (talla_cm BETWEEN 20 AND 250),
  presion_sis    int CHECK (presion_sis BETWEEN 50 AND 260),
  presion_dia    int CHECK (presion_dia BETWEEN 30 AND 160),
  frec_cardiaca  int CHECK (frec_cardiaca BETWEEN 20 AND 250),
  temperatura    numeric(4,1) CHECK (temperatura BETWEEN 30 AND 45),
  spo2           int CHECK (spo2 BETWEEN 50 AND 100)
);

-- 'documento' = administrativo (cédula, seguro): visible a recepción.
-- 'estudio'   = clínico (laboratorio, radiografía): solo personal médico.
CREATE TABLE archivos (
  id              serial PRIMARY KEY,
  paciente_id     int NOT NULL REFERENCES pacientes(id),
  categoria       text NOT NULL CHECK (categoria IN ('documento','estudio')),
  nombre_original text NOT NULL,
  ruta            text NOT NULL,
  mime            text,
  subido_por      int REFERENCES usuarios(id),
  creado          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE recetas (
  id                  serial PRIMARY KEY,
  paciente_id         int NOT NULL REFERENCES pacientes(id),
  medico_id           int NOT NULL REFERENCES usuarios(id),
  nota_id             int REFERENCES notas_clinicas(id),
  medicamentos_cif    bytea NOT NULL,
  codigo_verificacion uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
  creado              timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_receta_inmutable BEFORE UPDATE OR DELETE ON recetas
  FOR EACH ROW EXECUTE FUNCTION bloquear_modificacion();

-- ---------------------------------------------------------------------
-- Bitácora de acceso: cada apertura de expediente queda registrada.
-- Solo inserción: ni siquiera el administrador puede borrar huellas.
-- ---------------------------------------------------------------------
CREATE TABLE bitacora_acceso (
  id          bigserial PRIMARY KEY,
  usuario_id  int NOT NULL REFERENCES usuarios(id),
  paciente_id int REFERENCES pacientes(id),
  accion      text NOT NULL,
  ip          inet,
  creado      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON bitacora_acceso (paciente_id, creado DESC);
CREATE TRIGGER trg_bitacora_inmutable BEFORE UPDATE OR DELETE ON bitacora_acceso
  FOR EACH ROW EXECUTE FUNCTION bloquear_modificacion();
CREATE TRIGGER trg_bitacora_sin_truncate BEFORE TRUNCATE ON bitacora_acceso
  FOR EACH STATEMENT EXECUTE FUNCTION bloquear_modificacion();

-- ---------------------------------------------------------------------
-- Facturación
-- ---------------------------------------------------------------------
CREATE TABLE cargos (
  id          serial PRIMARY KEY,
  paciente_id int NOT NULL REFERENCES pacientes(id),
  servicio_id int REFERENCES servicios(id),
  cita_id     int REFERENCES citas(id),
  descripcion text NOT NULL,
  monto       numeric(10,2) NOT NULL CHECK (monto > 0),
  creado      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE pagos (
  id           serial PRIMARY KEY,
  paciente_id  int NOT NULL REFERENCES pacientes(id),
  monto        numeric(10,2) NOT NULL CHECK (monto > 0),
  metodo       text NOT NULL CHECK (metodo IN ('efectivo','tarjeta','transferencia')),
  referencia   text,
  recibido_por int REFERENCES usuarios(id),
  creado       timestamptz NOT NULL DEFAULT now()
);

CREATE VIEW v_saldos AS
SELECT p.id AS paciente_id, p.nombre || ' ' || p.apellido AS paciente,
       COALESCE(c.total, 0) AS cargos, COALESCE(g.total, 0) AS pagos,
       COALESCE(c.total, 0) - COALESCE(g.total, 0) AS saldo
FROM pacientes p
LEFT JOIN (SELECT paciente_id, sum(monto) total FROM cargos GROUP BY 1) c ON c.paciente_id = p.id
LEFT JOIN (SELECT paciente_id, sum(monto) total FROM pagos  GROUP BY 1) g ON g.paciente_id = p.id;

-- ---------------------------------------------------------------------
-- Inventario de medicamentos e insumos
-- ---------------------------------------------------------------------
CREATE TABLE inventario (
  id           serial PRIMARY KEY,
  nombre       text NOT NULL,
  tipo         text NOT NULL CHECK (tipo IN ('medicamento','insumo')),
  unidad       text NOT NULL DEFAULT 'unidad',
  lote         text,
  caducidad    date,
  stock        int NOT NULL DEFAULT 0 CHECK (stock >= 0),
  stock_minimo int NOT NULL DEFAULT 5 CHECK (stock_minimo >= 0)
);

CREATE VIEW v_alertas_inventario AS
SELECT i.*,
       CASE WHEN caducidad < current_date THEN 'caducado'
            WHEN caducidad <= current_date + 30 THEN 'por_caducar'
            WHEN stock <= stock_minimo THEN 'stock_bajo' END AS alerta
FROM inventario i
WHERE caducidad <= current_date + 30 OR stock <= stock_minimo;
