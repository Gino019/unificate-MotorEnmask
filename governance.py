"""
governance.py — Módulo de Gobernanza de Datos Universal (Static Data Masking)

ARQUITECTURA: Patrón Strategy con Dispatcher.
Cada motor implementa dos funciones (_proteger / _restaurar) con la misma firma.
El dispatcher `proteger_tabla` / `restaurar_tabla` selecciona la estrategia correcta
en tiempo de ejecución según el nombre del motor.

ESTRATEGIA DE SEGURIDAD:
    INACTIVO: tabla original contiene datos reales.
              → SELECT * directo expone todo → VULNERABILIDAD DE AUDITORÍA.
    ACTIVO:   tabla original contiene DATOS ENMASCARADOS de forma permanente.
              tabla <nombre>__backup_enc contiene los originales CIFRADOS con AES-256 (Fernet).
              → SELECT * directo solo expone datos ya protegidos → AUDITORÍA CUMPLIDA.
              → SELECT * sobre el backup expone tokens Fernet ilegibles → AUDITORÍA CUMPLIDA.

MOTORES SOPORTADOS:
    sqlite    → SQL estándar con parámetros posicionales (?)
    postgres  → SQL estándar con parámetros posicionales (%s) y comillas dobles
    sqlserver → T-SQL nativo (SELECT INTO, UPDATE, DROP TABLE)
    mongodb   → PyMongo: clonación de colección + updateMany + shadow collection

PRE-FLIGHT CHECK (todos los motores):
    Antes de proteger, se verifica que el backup NO exista.
    Si existe, la operación aborta con un ValueError descriptivo.
    Esto evita sobrescrituras accidentales y corrupción de datos.
"""

import copy
import datetime
import os
import sqlite3
from typing import Any, Callable, Dict, List, Optional, Tuple

from config import settings
from masking import aplicar_enmascaramiento, cifrar_valor, descifrar_valor

# ─────────────────────────────────────────────────────────────────────────────
# ESTADO DE GOBERNANZA (en memoria)
# ─────────────────────────────────────────────────────────────────────────────

PLATFORM_DB = os.path.join(settings.DATA_DIR, "platform_users.db")
BACKUP_SUFFIX = "__backup_enc"

def _get_platform_conn():
    conn = sqlite3.connect(PLATFORM_DB)
    return conn

# Crear la tabla de gobernanza si no existe al arrancar
def init_governance_db():
    try:
        with _get_platform_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gobernanza_estado (
                    connection_id TEXT,
                    tabla         TEXT,
                    estado        TEXT NOT NULL,
                    PRIMARY KEY (connection_id, tabla)
                )
            """)
            conn.commit()
    except Exception:
        pass

init_governance_db()


def _registrar_estado(connection_id: str, tabla: str, estado: str) -> None:
    try:
        with _get_platform_conn() as conn:
            conn.execute("""
                INSERT INTO gobernanza_estado (connection_id, tabla, estado)
                VALUES (?, ?, ?)
                ON CONFLICT(connection_id, tabla) DO UPDATE SET estado=excluded.estado
            """, (connection_id, tabla, estado))
            conn.commit()
    except Exception:
        pass


def obtener_estado(connection_id: str, tabla: str) -> str:
    try:
        with _get_platform_conn() as conn:
            row = conn.execute("""
                SELECT estado FROM gobernanza_estado WHERE connection_id = ? AND tabla = ?
            """, (connection_id, tabla)).fetchone()
            if row:
                return row[0]
    except Exception:
        pass
    return "INACTIVA"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS COMPARTIDOS
# ─────────────────────────────────────────────────────────────────────────────

def _parsear_fecha_sqlserver(val_str: str, tipo_destino: str):
    """
    Intenta parsear una cadena de texto a un objeto datetime/date
    según el tipo de destino de SQL Server.
    """
    if not val_str:
        return None
    val_str = val_str.strip()
    
    # Formatos comunes de str(datetime) y str(date)
    formatos = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S"
    ]
    
    for fmt in formatos:
        try:
            dt = datetime.datetime.strptime(val_str, fmt)
            if tipo_destino == "date":
                return dt.date()
            return dt
        except ValueError:
            continue
            
    # Si ningún formato funciona, retornamos el string original
    return val_str

def _cifrar_fila(fila: Dict, columnas: List[str]) -> List[Optional[str]]:
    """Serializa y cifra todos los valores de una fila con Fernet AES."""
    return [cifrar_valor(str(fila.get(c))) if fila.get(c) is not None else None for c in columnas]


def _descifrar_fila(fila: Dict, columnas: List[str]) -> List[Optional[str]]:
    """Descifra todos los valores de una fila desde el backup Fernet."""
    resultado = []
    for c in columnas:
        val = fila.get(c)
        if val is None:
            resultado.append(None)
            continue
        try:
            resultado.append(descifrar_valor(val))
        except Exception:
            resultado.append(val)  # Valor no cifrado, lo devuelve sin cambios
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# ESTRATEGIA: SQLite
# ─────────────────────────────────────────────────────────────────────────────

def _sqlite_preflight(motor, tabla: str) -> str:
    backup = tabla + BACKUP_SUFFIX
    existe = motor.ejecutar_consulta(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{backup}'"
    )
    if existe:
        raise ValueError(
            f"Pre-flight FAIL: El backup '{backup}' ya existe en SQLite. "
            "La protección podría estar activa. Ejecuta 'Restaurar' primero."
        )
    return backup


def _sqlite_proteger(motor, tabla: str, reglas: Dict[str, str], connection_id: str) -> Dict[str, Any]:
    backup = _sqlite_preflight(motor, tabla)

    datos = motor.ejecutar_consulta(f"SELECT * FROM {tabla}")
    if not datos:
        raise ValueError(f"La tabla '{tabla}' está vacía. No hay nada que proteger.")

    cols = list(datos[0].keys())
    ph = ", ".join(["?" for _ in cols])
    cols_str = ", ".join(cols)

    conn = motor.conectar()
    cur = conn.cursor()

    # 1. Crear tabla de backup con todos los campos como TEXT
    col_defs = ", ".join([f"{c} TEXT" for c in cols])
    cur.execute(f"CREATE TABLE IF NOT EXISTS {backup} ({col_defs})")

    # 2. Insertar filas cifradas en el backup
    for fila in datos:
        cur.execute(f"INSERT INTO {backup} ({cols_str}) VALUES ({ph})", _cifrar_fila(fila, cols))

    # 3. Enmascarar y sobrescribir la tabla original
    enmascarados = aplicar_enmascaramiento(datos, reglas)
    cur.execute(f"DELETE FROM {tabla}")
    for fila in enmascarados:
        cur.execute(
            f"INSERT INTO {tabla} ({cols_str}) VALUES ({ph})",
            [str(fila.get(c, "")) for c in cols]
        )

    conn.commit()
    conn.close()
    _registrar_estado(connection_id, tabla, "ACTIVA")
    return {"filas_protegidas": len(enmascarados), "backup_tabla": backup}


def _sqlite_restaurar(motor, tabla: str, connection_id: str) -> Dict[str, Any]:
    backup = tabla + BACKUP_SUFFIX

    if not motor.ejecutar_consulta(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{backup}'"
    ):
        raise ValueError(f"Backup '{backup}' no encontrado en SQLite. Nada que restaurar.")

    cifrados = motor.ejecutar_consulta(f"SELECT * FROM {backup}")
    if not cifrados:
        raise ValueError("El backup está vacío.")

    cols = list(cifrados[0].keys())
    ph = ", ".join(["?" for _ in cols])

    conn = motor.conectar()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {tabla}")
    for fila in cifrados:
        cur.execute(f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({ph})", _descifrar_fila(fila, cols))
    cur.execute(f"DROP TABLE IF EXISTS {backup}")
    conn.commit()
    conn.close()

    _registrar_estado(connection_id, tabla, "INACTIVA")
    return {"filas_restauradas": len(cifrados)}


# ─────────────────────────────────────────────────────────────────────────────
# ESTRATEGIA: PostgreSQL
# ─────────────────────────────────────────────────────────────────────────────

def _postgres_preflight(motor, tabla: str) -> str:
    backup = tabla + BACKUP_SUFFIX
    res = motor.ejecutar_consulta(f"SELECT to_regclass('public.\"{backup}\"') AS existe")
    if res and res[0].get("existe"):
        raise ValueError(
            f"Pre-flight FAIL: La tabla '{backup}' ya existe en PostgreSQL. "
            "Ejecuta 'Restaurar' antes de volver a proteger."
        )
    return backup


def _postgres_proteger(motor, tabla: str, reglas: Dict[str, str], connection_id: str) -> Dict[str, Any]:
    backup = _postgres_preflight(motor, tabla)

    datos = motor.ejecutar_consulta(f'SELECT * FROM "{tabla}" LIMIT 50000')
    if not datos:
        raise ValueError(f"La tabla '{tabla}' está vacía.")

    cols = list(datos[0].keys())
    cols_q = ", ".join([f'"{c}"' for c in cols])      # columnas con comillas
    ph = ", ".join(["%s" for _ in cols])

    conn = motor.conectar()
    cur = conn.cursor()

    # 1. Crear tabla de backup (todos los campos TEXT para almacenar tokens Fernet)
    col_defs = ", ".join([f'"{c}" TEXT' for c in cols])
    cur.execute(f'CREATE TABLE IF NOT EXISTS "{backup}" ({col_defs})')

    # 2. Insertar filas cifradas en el backup
    for fila in datos:
        cur.execute(f'INSERT INTO "{backup}" ({cols_q}) VALUES ({ph})', _cifrar_fila(fila, cols))

    # 3. Enmascarar y sobrescribir tabla original
    enmascarados = aplicar_enmascaramiento(datos, reglas)
    cur.execute(f'DELETE FROM "{tabla}"')
    for fila in enmascarados:
        cur.execute(
            f'INSERT INTO "{tabla}" ({cols_q}) VALUES ({ph})',
            [str(fila.get(c, "")) for c in cols]
        )

    conn.commit()
    conn.close()
    _registrar_estado(connection_id, tabla, "ACTIVA")
    return {"filas_protegidas": len(enmascarados), "backup_tabla": backup}


def _postgres_restaurar(motor, tabla: str, connection_id: str) -> Dict[str, Any]:
    backup = tabla + BACKUP_SUFFIX

    res = motor.ejecutar_consulta(f"SELECT to_regclass('public.\"{backup}\"') AS existe")
    if not res or not res[0].get("existe"):
        raise ValueError(f"Backup '{backup}' no encontrado en PostgreSQL.")

    cifrados = motor.ejecutar_consulta(f'SELECT * FROM "{backup}"')
    if not cifrados:
        raise ValueError("El backup está vacío.")

    cols = list(cifrados[0].keys())
    cols_q = ", ".join([f'"{c}"' for c in cols])
    ph = ", ".join(["%s" for _ in cols])

    conn = motor.conectar()
    cur = conn.cursor()
    cur.execute(f'DELETE FROM "{tabla}"')
    for fila in cifrados:
        cur.execute(f'INSERT INTO "{tabla}" ({cols_q}) VALUES ({ph})', _descifrar_fila(fila, cols))
    cur.execute(f'DROP TABLE IF EXISTS "{backup}"')
    conn.commit()
    conn.close()

    _registrar_estado(connection_id, tabla, "INACTIVA")
    return {"filas_restauradas": len(cifrados)}


# ─────────────────────────────────────────────────────────────────────────────
# ESTRATEGIA: SQL Server (T-SQL)
# ─────────────────────────────────────────────────────────────────────────────

def _sqlserver_preflight(motor, tabla: str) -> str:
    backup = tabla + BACKUP_SUFFIX
    res = motor.ejecutar_consulta(
        f"SELECT OBJECT_ID('{backup}', 'U') AS existe"
    )
    if res and res[0].get("existe") is not None:
        raise ValueError(
            f"Pre-flight FAIL: La tabla '{backup}' ya existe en SQL Server. "
            "Ejecuta 'Restaurar' antes de volver a proteger."
        )
    return backup


def _sqlserver_get_fk_dependientes(cur, tabla: str) -> List[str]:
    """
    Consulta el catálogo del sistema para obtener todas las tablas hijo
    que tienen FK references apuntando a [tabla].
    Devuelve una lista de nombres de tabla para poder operar con NOCHECK / CHECK.
    """
    cur.execute("""
        SELECT DISTINCT
            OBJECT_NAME(fk.parent_object_id) AS tabla_hijo
        FROM sys.foreign_keys AS fk
        INNER JOIN sys.tables AS t
            ON t.object_id = fk.referenced_object_id
        WHERE t.name = %s
    """, (tabla,))
    filas = cur.fetchall()
    # pymssql devuelve tuplas; extraemos el primer elemento de cada fila
    return [f[0] if isinstance(f, (tuple, list)) else f.get("tabla_hijo") for f in filas]


def _sqlserver_proteger(motor, tabla: str, reglas: Dict[str, str], connection_id: str) -> Dict[str, Any]:
    backup = _sqlserver_preflight(motor, tabla)

    datos = motor.ejecutar_consulta(f"SELECT TOP 50000 * FROM [{tabla}]")
    if not datos:
        raise ValueError(f"La tabla '{tabla}' está vacía.")

    cols = list(datos[0].keys())
    cols_q = ", ".join([f"[{c}]" for c in cols])
    ph    = ", ".join(["%s" for _ in cols])  # pymssql usa %s

    conn = motor.conectar()
    cur  = conn.cursor()

    # Descubrir tablas hijo con FK hacia [tabla]
    tablas_hijo = _sqlserver_get_fk_dependientes(cur, tabla)

    success = False
    try:
        # ─ Deshabilitar FK constraints en tablas hijo ─────────────────────
        for hijo in tablas_hijo:
            cur.execute(f"ALTER TABLE [{hijo}] NOCHECK CONSTRAINT ALL")

        # Habilitar IDENTITY_INSERT por si la tabla tiene columna IDENTITY
        try:
            cur.execute(f"SET IDENTITY_INSERT [{tabla}] ON")
        except Exception:
            pass

        # 1. Crear tabla de backup (NVARCHAR(MAX) para tokens Fernet)
        col_defs = ", ".join([f"[{c}] NVARCHAR(MAX)" for c in cols])
        cur.execute(f"CREATE TABLE [{backup}] ({col_defs})")

        # 2. Insertar filas cifradas en el backup
        for fila in datos:
            cur.execute(
                f"INSERT INTO [{backup}] ({cols_q}) VALUES ({ph})",
                _cifrar_fila(fila, cols)
            )

        # 3. Enmascarar y sobrescribir tabla original
        enmascarados = aplicar_enmascaramiento(datos, reglas)
        cur.execute(f"DELETE FROM [{tabla}]")
        for fila in enmascarados:
            valores = [fila.get(c) for c in cols]
            cur.execute(
                f"INSERT INTO [{tabla}] ({cols_q}) VALUES ({ph})",
                valores
            )

        conn.commit()
        success = True

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        raise e
    finally:
        # Deshabilitar IDENTITY_INSERT para la tabla original
        try:
            cur.execute(f"SET IDENTITY_INSERT [{tabla}] OFF")
        except Exception:
            pass

        # ─ Rehabilitar FK constraints SIEMPRE (incluso si hubo excepción) ───
        for hijo in tablas_hijo:
            try:
                cur.execute(f"ALTER TABLE [{hijo}] CHECK CONSTRAINT ALL")
            except Exception:
                pass  # No queremos enmascarar el error original
        if success:
            try:
                conn.commit()
            except Exception:
                pass
        conn.close()

    _registrar_estado(connection_id, tabla, "ACTIVA")
    return {"filas_protegidas": len(enmascarados), "backup_tabla": backup}


def _sqlserver_restaurar(motor, tabla: str, connection_id: str) -> Dict[str, Any]:
    backup = tabla + BACKUP_SUFFIX

    res = motor.ejecutar_consulta(f"SELECT OBJECT_ID('{backup}', 'U') AS existe")
    if not res or res[0].get("existe") is None:
        raise ValueError(f"Backup '{backup}' no encontrado en SQL Server.")

    cifrados = motor.ejecutar_consulta(f"SELECT * FROM [{backup}]")
    if not cifrados:
        raise ValueError("El backup está vacío.")

    cols = list(cifrados[0].keys())
    cols_q = ", ".join([f"[{c}]" for c in cols])
    ph    = ", ".join(["%s" for _ in cols])  # pymssql usa %s

    conn = motor.conectar()
    cur  = conn.cursor()

    # Descubrir tablas hijo con FK hacia [tabla]
    tablas_hijo = _sqlserver_get_fk_dependientes(cur, tabla)

    # Obtener tipos de columna de la tabla original para parsear fechas
    tipos_cols = {}
    try:
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = %s
        """, (tabla,))
        filas_tipos = cur.fetchall()
        for f in filas_tipos:
            col_name = f[0] if isinstance(f, (tuple, list)) else f.get("COLUMN_NAME")
            col_type = f[1] if isinstance(f, (tuple, list)) else f.get("DATA_TYPE")
            if col_name and col_type:
                tipos_cols[col_name.lower()] = col_type.lower()
    except Exception:
        pass

    success = False
    try:
        # ─ Deshabilitar FK constraints en tablas hijo ─────────────────────
        for hijo in tablas_hijo:
            cur.execute(f"ALTER TABLE [{hijo}] NOCHECK CONSTRAINT ALL")

        # Habilitar IDENTITY_INSERT por si la tabla tiene columna IDENTITY
        try:
            cur.execute(f"SET IDENTITY_INSERT [{tabla}] ON")
        except Exception:
            pass

        cur.execute(f"DELETE FROM [{tabla}]")
        for fila in cifrados:
            descifrada = _descifrar_fila(fila, cols)
            valores_restaurados = []
            for c, val in zip(cols, descifrada):
                tipo = tipos_cols.get(c.lower(), "")
                if val is not None and tipo in ("date", "datetime", "datetime2", "smalldatetime", "datetimeoffset"):
                    valores_restaurados.append(_parsear_fecha_sqlserver(val, tipo))
                else:
                    valores_restaurados.append(val)

            cur.execute(
                f"INSERT INTO [{tabla}] ({cols_q}) VALUES ({ph})",
                valores_restaurados
            )
        cur.execute(f"DROP TABLE [{backup}]")
        conn.commit()
        success = True

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        raise e
    finally:
        # Deshabilitar IDENTITY_INSERT para la tabla original
        try:
            cur.execute(f"SET IDENTITY_INSERT [{tabla}] OFF")
        except Exception:
            pass

        # ─ Rehabilitar FK constraints SIEMPRE ────────────────────────
        for hijo in tablas_hijo:
            try:
                cur.execute(f"ALTER TABLE [{hijo}] CHECK CONSTRAINT ALL")
            except Exception:
                pass
        if success:
            try:
                conn.commit()
            except Exception:
                pass
        conn.close()

    _registrar_estado(connection_id, tabla, "INACTIVA")
    return {"filas_restauradas": len(cifrados)}


# ─────────────────────────────────────────────────────────────────────────────
# ESTRATEGIA: MongoDB (Shadow Collections)
# ─────────────────────────────────────────────────────────────────────────────

def _mongo_preflight(motor, coleccion: str) -> Tuple[Any, Any, str]:
    """
    Retorna (cliente_mongo, db, nombre_backup) si el preflight pasa.
    El cliente queda ABIERTO — el caller debe cerrarlo con cliente.close().
    """
    backup = coleccion + BACKUP_SUFFIX
    cliente = motor.conectar()
    db_name = motor.credenciales.get("database")
    db = cliente[db_name]
    if backup in db.list_collection_names():
        cliente.close()
        raise ValueError(
            f"Pre-flight FAIL: La shadow collection '{backup}' ya existe en MongoDB. "
            "Ejecuta 'Restaurar' antes de volver a proteger."
        )
    return cliente, db, backup


def _mongo_proteger(motor, coleccion: str, reglas: Dict[str, str], connection_id: str) -> Dict[str, Any]:
    cliente, db, backup = _mongo_preflight(motor, coleccion)

    try:
        col_orig = db[coleccion]
        docs_originales = list(col_orig.find({}))
        if not docs_originales:
            raise ValueError(f"La colección '{coleccion}' está vacía.")

        # Serializar ObjectId a string para poder manipular los documentos
        docs_serializados = [
            {k: (str(v) if k == "_id" else v) for k, v in doc.items()}
            for doc in docs_originales
        ]

        # 1. Crear shadow collection con documentos COMPLETAMENTE cifrados (campo a campo)
        docs_backup = []
        for doc in docs_serializados:
            doc_enc = {}
            for k, v in doc.items():
                if k == "_id":
                    doc_enc[k] = v  # Preservar el ID original como string
                elif isinstance(v, str):
                    doc_enc[k] = cifrar_valor(v)
                elif v is not None:
                    doc_enc[k] = cifrar_valor(str(v))  # Serializar y cifrar no-strings
                else:
                    doc_enc[k] = None
            docs_backup.append(doc_enc)

        db[backup].insert_many(copy.deepcopy(docs_backup))

        # 2. Aplicar enmascaramiento con las reglas del usuario sobre los originales
        docs_enmascarados = aplicar_enmascaramiento(docs_serializados, reglas)

        # 3. Reemplazar la colección original
        col_orig.drop()
        db[coleccion].insert_many(copy.deepcopy(docs_enmascarados))

    finally:
        cliente.close()

    _registrar_estado(connection_id, coleccion, "ACTIVA")
    return {"filas_protegidas": len(docs_originales), "shadow_collection": backup}


def _mongo_restaurar(motor, coleccion: str, connection_id: str) -> Dict[str, Any]:
    backup = coleccion + BACKUP_SUFFIX
    cliente = motor.conectar()

    try:
        db_name = motor.credenciales.get("database")
        db = cliente[db_name]

        if backup not in db.list_collection_names():
            raise ValueError(f"Shadow collection '{backup}' no encontrada en MongoDB.")

        docs_cifrados = list(db[backup].find({}))
        if not docs_cifrados:
            raise ValueError("El backup de MongoDB está vacío.")

        # Descifrar todos los campos (excepto _id que es string del ObjectId original)
        docs_restaurados = []
        for doc in docs_cifrados:
            doc_dec = {}
            for k, v in doc.items():
                if k == "_id":
                    continue  # MongoDB generará un nuevo _id al insertar
                if isinstance(v, str):
                    try:
                        doc_dec[k] = descifrar_valor(v)
                    except Exception:
                        doc_dec[k] = v  # Si no era Fernet, dejarlo tal cual
                else:
                    doc_dec[k] = v
            docs_restaurados.append(doc_dec)

        db[coleccion].drop()
        db[coleccion].insert_many(copy.deepcopy(docs_restaurados))
        db[backup].drop()

    finally:
        cliente.close()

    _registrar_estado(connection_id, coleccion, "INACTIVA")
    return {"filas_restauradas": len(docs_restaurados)}


# ─────────────────────────────────────────────────────────────────────────────
# DISPATCHER PRINCIPAL — Patrón Strategy
# ─────────────────────────────────────────────────────────────────────────────

# Registro de estrategias: motor → (fn_proteger, fn_restaurar)
_ESTRATEGIAS: Dict[str, Tuple[Callable, Callable]] = {
    "sqlite":    (_sqlite_proteger,    _sqlite_restaurar),
    "postgres":  (_postgres_proteger,  _postgres_restaurar),
    "sqlserver": (_sqlserver_proteger, _sqlserver_restaurar),
    "mongodb":   (_mongo_proteger,     _mongo_restaurar),
}

MOTORES_SDM_DISPONIBLES = list(_ESTRATEGIAS.keys())


def proteger_tabla(
    motor_nombre: str,
    motor: Any,
    tabla: str,
    reglas: Dict[str, str],
    connection_id: str,
) -> Dict[str, Any]:
    """
    Punto de entrada unificado para activar el Static Data Masking.
    Selecciona la estrategia correcta según el motor y delega la operación.

    Raises:
        ValueError: Pre-flight fallido, tabla vacía, o motor no soportado.
        Exception:  Error de conexión o error inesperado durante la operación.
    """
    if motor_nombre not in _ESTRATEGIAS:
        disponibles = ", ".join(MOTORES_SDM_DISPONIBLES)
        raise ValueError(
            f"SDM no disponible para el motor '{motor_nombre}'. "
            f"Motores soportados: {disponibles}."
        )

    fn_proteger, _ = _ESTRATEGIAS[motor_nombre]
    return fn_proteger(motor, tabla, reglas, connection_id)


def restaurar_tabla(
    motor_nombre: str,
    motor: Any,
    tabla: str,
    connection_id: str,
) -> Dict[str, Any]:
    """
    Punto de entrada unificado para revertir el Static Data Masking.
    Descifra el backup AES y restaura los datos originales.

    Raises:
        ValueError: Backup no encontrado o motor no soportado.
        Exception:  Error de conexión o error inesperado durante la operación.
    """
    if motor_nombre not in _ESTRATEGIAS:
        disponibles = ", ".join(MOTORES_SDM_DISPONIBLES)
        raise ValueError(
            f"Restore no disponible para el motor '{motor_nombre}'. "
            f"Motores soportados: {disponibles}."
        )

    _, fn_restaurar = _ESTRATEGIAS[motor_nombre]
    return fn_restaurar(motor, tabla, connection_id)
