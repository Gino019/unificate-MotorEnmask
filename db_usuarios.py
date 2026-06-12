"""
db_usuarios.py — Gestión de la tabla usuarios_plataforma
Base de datos SQLite interna del sistema SecOps (NO la de los usuarios finales).

Contiene:
- Inicialización del esquema
- Registro con hash bcrypt
- Autenticación por email + password
- Upsert para usuarios de Google OAuth2
- Auto-creación del usuario administrador por defecto al primer arranque
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from passlib.context import CryptContext

# Motor de hash bcrypt — estándar de la industria para contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Archivo SQLite exclusivo para la plataforma (separado de las BDs de los usuarios)
PLATFORM_DB = "platform_users.db"

# Credenciales del administrador por defecto (primer arranque)
ADMIN_EMAIL    = "admin@secops.local"
ADMIN_PASSWORD = "Admin1234!"
ADMIN_NAME     = "Administrador SecOps"


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
    password: Optional[str] = None,
    proveedor: str = "local"
) -> Dict[str, Any]:
    """
    Inserta un nuevo usuario. Lanza ValueError si el correo ya existe.
    Para usuarios de Google, password puede ser None.
    """
    if buscar_usuario_por_correo(correo):
        raise ValueError(f"El correo '{correo}' ya está registrado.")

    usuario_id = str(uuid.uuid4())
    hash_pwd = pwd_context.hash(password) if password else None
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
        # Usuario de Google — no tiene contraseña local
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


def buscar_o_crear_usuario_google(nombre: str, correo: str) -> Dict[str, Any]:
    """
    Upsert para usuarios que entran vía Google OAuth2.
    Si ya existe (de login previo con Google o local), retorna su registro.
    Si es nuevo, lo crea con proveedor='google'.
    """
    usuario = buscar_usuario_por_correo(correo)
    if usuario:
        return dict(usuario)
    return registrar_usuario(nombre, correo, password=None, proveedor="google")
