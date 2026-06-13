"""
auth.py — Gestión de sesiones en memoria
Sesiones ahora incluyen: username, email, proveedor y el mapa de conexiones concurrentes.
"""

import secrets
import uuid
from fastapi import Request, HTTPException, status
from typing import Dict, Any

# Estructura:
# {
#   "token_hex": {
#       "username": "John Doe",
#       "email": "john@example.com",
#       "proveedor": "local",
#       "conexiones": { "uuid_conn": {...} }
#   }
# }
SESIONES_ACTIVAS: Dict[str, Dict[str, Any]] = {}


def crear_token_sesion(username: str, email: str, proveedor: str = "local") -> str:
    """Genera un token seguro y registra la sesión en memoria."""
    token = secrets.token_hex(32)
    SESIONES_ACTIVAS[token] = {
        "username": username,
        "email": email,
        "proveedor": proveedor,
        "conexiones": {}
    }
    return token


def revocar_token(token: str):
    if token in SESIONES_ACTIVAS:
        del SESIONES_ACTIVAS[token]


def obtener_sesion_actual(request: Request) -> Dict[str, Any]:
    """Extrae y valida la sesión desde la cookie HTTP-only."""
    token = request.cookies.get("session_token")
    if not token or token not in SESIONES_ACTIVAS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado. Inicia sesión.",
        )
    return SESIONES_ACTIVAS[token]


# ── Conexiones concurrentes ───────────────────────────────────────────────────

def agregar_conexion(request: Request, config: Dict[str, Any]) -> str:
    token = request.cookies.get("session_token")
    if token and token in SESIONES_ACTIVAS:
        conn_id = uuid.uuid4().hex
        SESIONES_ACTIVAS[token]["conexiones"][conn_id] = config
        return conn_id
    raise HTTPException(status_code=401, detail="Sesión inválida")


def obtener_conexion(request: Request, connection_id: str) -> Dict[str, Any]:
    sesion = obtener_sesion_actual(request)
    conexiones = sesion.get("conexiones", {})
    if connection_id not in conexiones:
        raise HTTPException(status_code=404, detail="Conexión no encontrada o expirada.")
    return conexiones[connection_id]


def eliminar_conexion(request: Request, connection_id: str):
    token = request.cookies.get("session_token")
    if token and token in SESIONES_ACTIVAS:
        SESIONES_ACTIVAS[token]["conexiones"].pop(connection_id, None)
