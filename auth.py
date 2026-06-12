from fastapi import Request, HTTPException, status
import secrets
import uuid
from typing import Dict, Any

# Estructura: {"token": {"username": "admin", "conexiones": {"uuid_1": {...}, "uuid_2": {...}}}}
SESIONES_ACTIVAS: Dict[str, Dict[str, Any]] = {}

def crear_token_sesion(username: str) -> str:
    token = secrets.token_hex(32)
    SESIONES_ACTIVAS[token] = {"username": username, "conexiones": {}}
    return token

def revocar_token(token: str):
    if token in SESIONES_ACTIVAS:
        del SESIONES_ACTIVAS[token]

def obtener_sesion_actual(request: Request) -> Dict[str, Any]:
    token = request.cookies.get("session_token")
    if not token or token not in SESIONES_ACTIVAS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return SESIONES_ACTIVAS[token]

def agregar_conexion(request: Request, config: Dict[str, Any]) -> str:
    """ Genera un UUID para la conexión y la agrega al estado del usuario """
    token = request.cookies.get("session_token")
    if token and token in SESIONES_ACTIVAS:
        conn_id = uuid.uuid4().hex
        SESIONES_ACTIVAS[token]["conexiones"][conn_id] = config
        return conn_id
    raise HTTPException(status_code=401, detail="Sesión inválida")

def obtener_conexion(request: Request, connection_id: str) -> Dict[str, Any]:
    """ Recupera el contexto de una conexión específica """
    sesion = obtener_sesion_actual(request)
    conexiones = sesion.get("conexiones", {})
    if connection_id not in conexiones:
        raise HTTPException(status_code=404, detail="Conexión no encontrada o expirada")
    return conexiones[connection_id]

def eliminar_conexion(request: Request, connection_id: str):
    """ Desconecta una base de datos específica sin cerrar la sesión global """
    token = request.cookies.get("session_token")
    if token and token in SESIONES_ACTIVAS:
        if connection_id in SESIONES_ACTIVAS[token]["conexiones"]:
            del SESIONES_ACTIVAS[token]["conexiones"][connection_id]

def validar_credenciales(username: str, password: str) -> bool:
    return username == "admin" and password == "admin123"
