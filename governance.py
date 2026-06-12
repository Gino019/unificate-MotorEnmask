"""
governance.py — Módulo de Gobernanza de Datos (Static Data Masking)

ESTRATEGIA DE SEGURIDAD:
    INACTIVO: tabla original contiene datos reales → vulnerabilidad ante acceso directo.
    ACTIVO:   tabla original contiene datos enmascarados permanentemente.
              tabla __backup_enc contiene los datos originales CIFRADOS con Fernet AES.

Flujo de ataque bloqueado post-activación:
    ATACANTE → SELECT * FROM clientes → Ve datos ya enmascarados → Auditoría OK.
    ATACANTE → SELECT * FROM clientes__backup_enc → Ve tokens AES ilegibles → Auditoría OK.
"""

from typing import Any, Dict, List
from masking import cifrar_valor, descifrar_valor, aplicar_enmascaramiento

# Estado de gobernanza en memoria: {connection_id: {tabla: "ACTIVA"|"INACTIVA"}}
ESTADO_GOBERNANZA: Dict[str, Dict[str, str]] = {}

BACKUP_SUFFIX = "__backup_enc"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────────────────────

def _registrar_estado(connection_id: str, tabla: str, estado: str):
    if connection_id not in ESTADO_GOBERNANZA:
        ESTADO_GOBERNANZA[connection_id] = {}
    ESTADO_GOBERNANZA[connection_id][tabla] = estado


def obtener_estado(connection_id: str, tabla: str) -> str:
    return ESTADO_GOBERNANZA.get(connection_id, {}).get(tabla, "INACTIVA")


# ─────────────────────────────────────────────────────────────────────────────
# SQLITE — SDM
# ─────────────────────────────────────────────────────────────────────────────

def _sqlite_preflight(motor, tabla: str):
    """Pre-flight check: aborta si el backup ya existe."""
    backup_tabla = tabla + BACKUP_SUFFIX
    resultados = motor.ejecutar_consulta(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{backup_tabla}'"
    )
    if resultados:
        raise ValueError(
            f"Pre-flight FAIL: La tabla de backup '{backup_tabla}' ya existe. "
            "La protección ya podría estar activa. Usa 'Restaurar' primero."
        )


def sqlite_proteger(motor, tabla: str, reglas: Dict[str, str], connection_id: str):
    _sqlite_preflight(motor, tabla)

    # 1. Leer todos los datos originales
    datos_originales = motor.ejecutar_consulta(f"SELECT * FROM {tabla}")
    if not datos_originales:
        raise ValueError(f"La tabla '{tabla}' está vacía. Nada que proteger.")

    columnas = list(datos_originales[0].keys())
    backup_tabla = tabla + BACKUP_SUFFIX

    import sqlite3
    conn = motor.conectar()
    cursor = conn.cursor()

    # 2. Crear tabla de backup con columnas como TEXT (valores cifrados)
    col_defs = ", ".join([f"{c} TEXT" for c in columnas])
    cursor.execute(f"CREATE TABLE IF NOT EXISTS {backup_tabla} ({col_defs})")

    # 3. Insertar BACKUP CIFRADO (todos los campos como texto Fernet)
    placeholders = ", ".join(["?" for _ in columnas])
    for fila in datos_originales:
        valores_cifrados = []
        for col in columnas:
            val = fila.get(col)
            valores_cifrados.append(cifrar_valor(str(val)) if val is not None else None)
        cursor.execute(
            f"INSERT INTO {backup_tabla} ({', '.join(columnas)}) VALUES ({placeholders})",
            valores_cifrados,
        )

    # 4. Enmascarar los datos de la tabla original con las reglas del usuario
    datos_enmascarados = aplicar_enmascaramiento(datos_originales, reglas)

    # 5. Sobrescribir la tabla original
    cursor.execute(f"DELETE FROM {tabla}")
    for fila in datos_enmascarados:
        valores = [str(fila.get(c, "")) for c in columnas]
        cursor.execute(
            f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({placeholders})",
            valores,
        )

    conn.commit()
    conn.close()
    _registrar_estado(connection_id, tabla, "ACTIVA")
    return {"filas_protegidas": len(datos_enmascarados), "backup_tabla": backup_tabla}


def sqlite_restaurar(motor, tabla: str, connection_id: str):
    backup_tabla = tabla + BACKUP_SUFFIX

    resultados = motor.ejecutar_consulta(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{backup_tabla}'"
    )
    if not resultados:
        raise ValueError(f"No se encontró backup '{backup_tabla}'. Nada que restaurar.")

    datos_cifrados = motor.ejecutar_consulta(f"SELECT * FROM {backup_tabla}")
    if not datos_cifrados:
        raise ValueError("El backup está vacío.")

    columnas = list(datos_cifrados[0].keys())

    import sqlite3
    conn = motor.conectar()
    cursor = conn.cursor()

    # Descifrar y restaurar
    placeholders = ", ".join(["?" for _ in columnas])
    cursor.execute(f"DELETE FROM {tabla}")
    for fila in datos_cifrados:
        valores_descifrados = []
        for col in columnas:
            val = fila.get(col)
            try:
                valores_descifrados.append(descifrar_valor(val) if val else None)
            except Exception:
                valores_descifrados.append(val)  # Si ya no era cifrado, dejarlo
        cursor.execute(
            f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({placeholders})",
            valores_descifrados,
        )

    cursor.execute(f"DROP TABLE IF EXISTS {backup_tabla}")
    conn.commit()
    conn.close()
    _registrar_estado(connection_id, tabla, "INACTIVA")
    return {"filas_restauradas": len(datos_cifrados)}


# ─────────────────────────────────────────────────────────────────────────────
# POSTGRESQL — SDM
# ─────────────────────────────────────────────────────────────────────────────

def _postgres_preflight(motor, tabla: str):
    backup_tabla = tabla + BACKUP_SUFFIX
    resultado = motor.ejecutar_consulta(
        f"SELECT to_regclass('public.{backup_tabla}') AS existe"
    )
    if resultado and resultado[0].get("existe"):
        raise ValueError(
            f"Pre-flight FAIL: La tabla de backup '{backup_tabla}' ya existe en Postgres. "
            "Restaura primero antes de volver a proteger."
        )


def postgres_proteger(motor, tabla: str, reglas: Dict[str, str], connection_id: str):
    _postgres_preflight(motor, tabla)

    datos_originales = motor.ejecutar_consulta(f"SELECT * FROM {tabla} LIMIT 10000")
    if not datos_originales:
        raise ValueError(f"La tabla '{tabla}' está vacía.")

    columnas = list(datos_originales[0].keys())
    backup_tabla = tabla + BACKUP_SUFFIX

    conn = motor.conectar()
    cursor = conn.cursor()

    # Backup cifrado (todos los campos como TEXT)
    col_defs = ", ".join([f'"{c}" TEXT' for c in columnas])
    cursor.execute(f'CREATE TABLE IF NOT EXISTS "{backup_tabla}" ({col_defs})')

    for fila in datos_originales:
        placeholders = ", ".join([f"%s" for _ in columnas])
        cols_str = ", ".join([f'"{c}"' for c in columnas])
        valores = [cifrar_valor(str(fila.get(c))) if fila.get(c) is not None else None for c in columnas]
        cursor.execute(f'INSERT INTO "{backup_tabla}" ({cols_str}) VALUES ({placeholders})', valores)

    # Enmascarar y sobrescribir la tabla original
    datos_enmascarados = aplicar_enmascaramiento(datos_originales, reglas)
    cursor.execute(f'DELETE FROM "{tabla}"')

    for fila in datos_enmascarados:
        placeholders = ", ".join(["%s" for _ in columnas])
        cols_str = ", ".join([f'"{c}"' for c in columnas])
        valores = [str(fila.get(c, "")) for c in columnas]
        cursor.execute(f'INSERT INTO "{tabla}" ({cols_str}) VALUES ({placeholders})', valores)

    conn.commit()
    conn.close()
    _registrar_estado(connection_id, tabla, "ACTIVA")
    return {"filas_protegidas": len(datos_enmascarados), "backup_tabla": backup_tabla}


def postgres_restaurar(motor, tabla: str, connection_id: str):
    backup_tabla = tabla + BACKUP_SUFFIX

    resultado = motor.ejecutar_consulta(
        f"SELECT to_regclass('public.{backup_tabla}') AS existe"
    )
    if not resultado or not resultado[0].get("existe"):
        raise ValueError(f"No se encontró backup '{backup_tabla}'.")

    datos_cifrados = motor.ejecutar_consulta(f'SELECT * FROM "{backup_tabla}"')
    columnas = list(datos_cifrados[0].keys())

    conn = motor.conectar()
    cursor = conn.cursor()

    cursor.execute(f'DELETE FROM "{tabla}"')
    for fila in datos_cifrados:
        placeholders = ", ".join(["%s" for _ in columnas])
        cols_str = ", ".join([f'"{c}"' for c in columnas])
        valores = []
        for c in columnas:
            val = fila.get(c)
            try:
                valores.append(descifrar_valor(val) if val else None)
            except Exception:
                valores.append(val)
        cursor.execute(f'INSERT INTO "{tabla}" ({cols_str}) VALUES ({placeholders})', valores)

    cursor.execute(f'DROP TABLE IF EXISTS "{backup_tabla}"')
    conn.commit()
    conn.close()
    _registrar_estado(connection_id, tabla, "INACTIVA")
    return {"filas_restauradas": len(datos_cifrados)}


# ─────────────────────────────────────────────────────────────────────────────
# MONGODB — SDM (Shadow Collections)
# ─────────────────────────────────────────────────────────────────────────────

def _mongo_preflight(motor, coleccion: str):
    backup_col = coleccion + BACKUP_SUFFIX
    conn = motor.conectar()
    try:
        db_name = motor.credenciales.get("database")
        db = conn[db_name]
        nombres = db.list_collection_names()
        if backup_col in nombres:
            raise ValueError(
                f"Pre-flight FAIL: La shadow collection '{backup_col}' ya existe. "
                "Restaura antes de volver a proteger."
            )
    finally:
        conn.close()


def mongo_proteger(motor, coleccion: str, reglas: Dict[str, str], connection_id: str):
    _mongo_preflight(motor, coleccion)

    import copy
    conn = motor.conectar()
    try:
        db_name = motor.credenciales.get("database")
        db = conn[db_name]
        col_orig = db[coleccion]
        backup_col = coleccion + BACKUP_SUFFIX

        datos_originales = list(col_orig.find({}))
        if not datos_originales:
            raise ValueError(f"La colección '{coleccion}' está vacía.")

        # Serializar ObjectId para backup
        datos_serializados = []
        for doc in datos_originales:
            doc_copia = {k: (str(v) if k == "_id" else v) for k, v in doc.items()}
            datos_serializados.append(doc_copia)

        # Backup cifrado: cada campo de string se cifra con Fernet
        backup_docs = []
        for doc in datos_serializados:
            doc_cifrado = {}
            for k, v in doc.items():
                if isinstance(v, str) and k != "_id":
                    doc_cifrado[k] = cifrar_valor(v)
                else:
                    doc_cifrado[k] = v
            backup_docs.append(doc_cifrado)

        col_backup = db[backup_col]
        col_backup.insert_many(copy.deepcopy(backup_docs))

        # Enmascarar y reemplazar la colección original
        datos_enmascarados = aplicar_enmascaramiento(datos_serializados, reglas)
        col_orig.drop()
        col_nueva = db[coleccion]
        col_nueva.insert_many(copy.deepcopy(datos_enmascarados))

    finally:
        conn.close()

    _registrar_estado(connection_id, coleccion, "ACTIVA")
    return {"filas_protegidas": len(datos_originales), "shadow_collection": backup_col}


def mongo_restaurar(motor, coleccion: str, connection_id: str):
    backup_col = coleccion + BACKUP_SUFFIX

    import copy
    conn = motor.conectar()
    try:
        db_name = motor.credenciales.get("database")
        db = conn[db_name]

        nombres = db.list_collection_names()
        if backup_col not in nombres:
            raise ValueError(f"No se encontró shadow collection '{backup_col}'.")

        datos_cifrados = list(db[backup_col].find({}))

        docs_restaurados = []
        for doc in datos_cifrados:
            doc_restaurado = {}
            for k, v in doc.items():
                if k == "_id":
                    continue  # MongoDB generará nuevos _id
                if isinstance(v, str):
                    try:
                        doc_restaurado[k] = descifrar_valor(v)
                    except Exception:
                        doc_restaurado[k] = v
                else:
                    doc_restaurado[k] = v
            docs_restaurados.append(doc_restaurado)

        db[coleccion].drop()
        db[coleccion].insert_many(copy.deepcopy(docs_restaurados))
        db[backup_col].drop()

    finally:
        conn.close()

    _registrar_estado(connection_id, coleccion, "INACTIVA")
    return {"filas_restauradas": len(docs_restaurados)}


# ─────────────────────────────────────────────────────────────────────────────
# DISPATCHER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def proteger_tabla(motor_nombre: str, motor, tabla: str, reglas: Dict[str, str], connection_id: str) -> Dict[str, Any]:
    """Punto de entrada unificado para activar el SDM."""
    if motor_nombre == "sqlite":
        return sqlite_proteger(motor, tabla, reglas, connection_id)
    elif motor_nombre == "postgres":
        return postgres_proteger(motor, tabla, reglas, connection_id)
    elif motor_nombre == "mongodb":
        return mongo_proteger(motor, tabla, reglas, connection_id)
    else:
        raise ValueError(f"SDM no disponible para el motor '{motor_nombre}'. Soportados: sqlite, postgres, mongodb.")


def restaurar_tabla(motor_nombre: str, motor, tabla: str, connection_id: str) -> Dict[str, Any]:
    """Punto de entrada unificado para revertir el SDM."""
    if motor_nombre == "sqlite":
        return sqlite_restaurar(motor, tabla, connection_id)
    elif motor_nombre == "postgres":
        return postgres_restaurar(motor, tabla, connection_id)
    elif motor_nombre == "mongodb":
        return mongo_restaurar(motor, tabla, connection_id)
    else:
        raise ValueError(f"Restore no disponible para el motor '{motor_nombre}'.")
