"""
db_usuarios.py — Gestión de la tabla usuarios_plataforma
Base de datos SQLite interna del sistema SecOps (NO la de los usuarios finales).

Contiene:
- Inicialización del esquema
- Registro con hash bcrypt
- Autenticación por email + password
- Auto-creación del usuario administrador por defecto al primer arranque
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from passlib.context import CryptContext

from config import settings

# Motor de hash bcrypt — estándar de la industria para contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Archivo SQLite exclusivo para la plataforma (separado de las BDs de los usuarios)
PLATFORM_DB = os.path.join(settings.DATA_DIR, "platform_users.db")

# Credenciales del administrador por defecto (primer arranque; sobreescribibles vía .env)
ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL", "admin@secops.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin1234!")
ADMIN_NAME     = os.getenv("ADMIN_NAME", "Administrador SecOps")


# ─────────────────────────────────────────────────────────────────────────────
# INICIALIZACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(PLATFORM_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea la tabla de usuarios si no existe y siembra el admin por defecto."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usuarios_plataforma (
                id              TEXT PRIMARY KEY,
                nombre_completo TEXT NOT NULL,
                correo          TEXT UNIQUE NOT NULL,
                password_hash   TEXT,
                proveedor       TEXT NOT NULL DEFAULT 'local',
                fecha_registro  TEXT NOT NULL
            )
        """)
        conn.commit()

    # Crear el usuario administrador si no existe todavía
    if not buscar_usuario_por_correo(ADMIN_EMAIL):
        registrar_usuario(ADMIN_NAME, ADMIN_EMAIL, ADMIN_PASSWORD, proveedor="local")
        print(f"[DB_USUARIOS] Usuario administrador creado: {ADMIN_EMAIL}")
    else:
        print(f"[DB_USUARIOS] Tabla usuarios_plataforma OK. Admin: {ADMIN_EMAIL}")


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

def registrar_usuario(
    nombre: str,
    correo: str,
    password: str,
    proveedor: str = "local",
) -> Dict[str, Any]:
    """Inserta un nuevo usuario. Lanza ValueError si el correo ya existe."""
    if not password:
        raise ValueError("La contraseña es obligatoria.")
    if buscar_usuario_por_correo(correo):
        raise ValueError(f"El correo '{correo}' ya está registrado.")

    usuario_id = str(uuid.uuid4())
    hash_pwd = pwd_context.hash(password)
    fecha = datetime.now(timezone.utc).isoformat()

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO usuarios_plataforma (id, nombre_completo, correo, password_hash, proveedor, fecha_registro)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (usuario_id, nombre, correo, hash_pwd, proveedor, fecha)
        )
        conn.commit()

    return {"id": usuario_id, "nombre": nombre, "correo": correo, "proveedor": proveedor}


def autenticar_usuario(correo: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Valida email + contraseña. Retorna el usuario si OK, None si falla.
    """
    usuario = buscar_usuario_por_correo(correo)
    if not usuario:
        return None
    if not usuario["password_hash"]:
        return None
    if not pwd_context.verify(password, usuario["password_hash"]):
        return None
    return dict(usuario)


def buscar_usuario_por_correo(correo: str) -> Optional[sqlite3.Row]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM usuarios_plataforma WHERE correo = ?", (correo,)
        ).fetchone()
    return row
