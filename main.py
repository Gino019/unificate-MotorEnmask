"""
main.py — SecOps Universal Monitor API v5.0
Autenticación real: email + bcrypt, Google OAuth2.
"""

import os
import secrets
import urllib.parse
from typing import Any, Dict

import httpx
from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from auth import (SESIONES_ACTIVAS, agregar_conexion, crear_token_sesion,
                  eliminar_conexion, obtener_conexion, obtener_sesion_actual,
                  revocar_token)
from config import settings
from database_manager import DatabaseFactory
from db_usuarios import (autenticar_usuario, buscar_o_crear_usuario_google,
                         init_db, registrar_usuario)
from governance import (obtener_estado, proteger_tabla, restaurar_tabla,
                        MOTORES_SDM_DISPONIBLES)
from monitor import monitor_overhead

# ── Configuración ─────────────────────────────────────────────────────────────
load_dotenv()
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")
GOOGLE_AUTH_URL      = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL     = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL  = "https://www.googleapis.com/oauth2/v3/userinfo"

# Estado temporal para anti-CSRF en OAuth2 (state param)
_OAUTH_STATES: Dict[str, str] = {}  # {state_token: "pending"}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="SecOps Universal Monitor — Autenticación Real + Multi-DB",
    version="5.0.0",
)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup_event():
    """Inicializa la BD de usuarios y crea el admin por defecto."""
    init_db()


# ─────────────────────────────────────────────────────────────────────────────
# AUTH — VISTAS HTML
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/login")
async def serve_login():
    return FileResponse("static/login.html")


@app.get("/")
async def serve_dashboard(request: Request):
    token = request.cookies.get("session_token")
    if not token or token not in SESIONES_ACTIVAS:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return FileResponse("static/index.html")


# ─────────────────────────────────────────────────────────────────────────────
# AUTH — REGISTRO Y LOGIN TRADICIONAL
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/auth/register", tags=["Auth"])
async def register(payload: Dict[str, Any] = Body(...)):
    """
    Registra un nuevo usuario con email + contraseña.
    Body: { nombre, correo, password }
    """
    nombre   = (payload.get("nombre") or "").strip()
    correo   = (payload.get("correo") or "").strip().lower()
    password = payload.get("password") or ""

    if not nombre or not correo or not password:
        raise HTTPException(status_code=400, detail="Nombre, correo y contraseña son obligatorios.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres.")

    try:
        usuario = registrar_usuario(nombre, correo, password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Auto-login tras registro exitoso
    token = crear_token_sesion(usuario["nombre"], usuario["correo"], "local")
    response = JSONResponse({"message": "Cuenta creada exitosamente.", "nombre": usuario["nombre"]})
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return response


@app.post("/api/login", tags=["Auth"])
async def login(correo: str = Form(...), password: str = Form(...)):
    usuario = autenticar_usuario(correo.strip().lower(), password)
    if not usuario:
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")

    token = crear_token_sesion(usuario["nombre_completo"], usuario["correo"], usuario.get("proveedor","local"))
    response = JSONResponse({"message": "Login exitoso.", "nombre": usuario["nombre_completo"]})
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return response


@app.post("/api/logout", tags=["Auth"])
async def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        revocar_token(token)
    response = JSONResponse({"message": "Sesión cerrada."})
    response.delete_cookie("session_token")
    return response


@app.get("/api/auth/me", tags=["Auth"])
async def me(sesion: Dict[str, Any] = Depends(obtener_sesion_actual)):
    """Retorna los datos del usuario de la sesión activa."""
    return {
        "username": sesion.get("username"),
        "email":    sesion.get("email"),
        "proveedor": sesion.get("proveedor"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# AUTH — GOOGLE OAUTH2
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/auth/google/login", tags=["Auth / Google OAuth2"])
async def google_login():
    """
    Redirige al usuario a la pantalla de consentimiento de Google.
    Requiere GOOGLE_CLIENT_ID configurado en .env.
    """
    if not GOOGLE_CLIENT_ID or GOOGLE_CLIENT_ID == "PENDIENTE_CONFIGURAR":
        raise HTTPException(
            status_code=503,
            detail="Google OAuth2 no está configurado. Añade GOOGLE_CLIENT_ID en el archivo .env."
        )

    state = secrets.token_urlsafe(16)
    _OAUTH_STATES[state] = "pending"

    params = urllib.parse.urlencode({
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "access_type":   "online",
        "prompt":        "select_account",
    })
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{params}")


@app.get("/api/v1/auth/google/callback", tags=["Auth / Google OAuth2"])
async def google_callback(code: str, state: str, request: Request):
    """
    Google redirige aquí con ?code=...&state=...
    Intercambiamos el code por un access_token y obtenemos el perfil del usuario.
    """
    # Anti-CSRF: verificar state
    if state not in _OAUTH_STATES:
        raise HTTPException(status_code=400, detail="OAuth state inválido o expirado.")
    del _OAUTH_STATES[state]

    # Intercambiar code por access_token
    async with httpx.AsyncClient() as client:
        token_res = await client.post(GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri":  GOOGLE_REDIRECT_URI,
            "grant_type":    "authorization_code",
        })
        if token_res.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Error al obtener token de Google: {token_res.text}")

        token_data = token_res.json()
        access_token = token_data.get("access_token")

        # Obtener perfil del usuario desde Google
        user_res = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_res.status_code != 200:
            raise HTTPException(status_code=502, detail="No se pudo obtener el perfil de Google.")

        user_info = user_res.json()

    nombre = user_info.get("name", "Usuario Google")
    correo = user_info.get("email", "")

    if not correo:
        raise HTTPException(status_code=400, detail="Google no proporcionó un correo electrónico.")

    # Buscar o crear el usuario en nuestra BD
    usuario = buscar_o_crear_usuario_google(nombre, correo)

    token = crear_token_sesion(
        usuario.get("nombre_completo") or usuario.get("nombre") or nombre,
        correo,
        "google"
    )
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return response


# ─────────────────────────────────────────────────────────────────────────────
# CONEXIONES MÚLTIPLES
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/connect", tags=["SecOps Universal"])
async def conectar_db(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    sesion: Dict[str, Any] = Depends(obtener_sesion_actual),
):
    motor_nombre = payload.get("motor")
    credenciales = payload.get("credenciales", {})
    alias = payload.get("alias", f"{str(motor_nombre).capitalize()} DB")
    try:
        motor = DatabaseFactory.obtener_motor(motor_nombre, credenciales)
        esquema = motor.obtener_esquema()
        payload["esquema_cache"] = esquema
        payload["alias"] = alias
        conn_id = agregar_conexion(request, payload)
        return {"message": "Conexión exitosa", "connection_id": conn_id, "alias": alias, "esquema": esquema}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error conectando a BD: {str(e)}")


@app.get("/api/v1/connections", tags=["SecOps Universal"])
async def get_connections(sesion: Dict[str, Any] = Depends(obtener_sesion_actual)):
    conexiones = sesion.get("conexiones", {})
    return {"conexiones": [{"id": cid, "alias": d.get("alias"), "motor": d.get("motor")} for cid, d in conexiones.items()]}


@app.delete("/api/v1/connections/{connection_id}", tags=["SecOps Universal"])
async def delete_connection(connection_id: str, request: Request, sesion: Dict[str, Any] = Depends(obtener_sesion_actual)):
    eliminar_conexion(request, connection_id)
    return {"message": "Conexión eliminada"}


@app.get("/api/v1/schema", tags=["SecOps Universal"])
async def get_schema(connection_id: str, request: Request):
    config = obtener_conexion(request, connection_id)
    return config.get("esquema_cache", {"tablas": {}})


@app.post("/api/v1/execute_test", tags=["SecOps Universal"])
async def ejecutar_test(request: Request, payload: Dict[str, Any] = Body(...)):
    connection_id = payload.get("connection_id")
    if not connection_id:
        raise HTTPException(status_code=400, detail="Falta connection_id.")

    config = obtener_conexion(request, connection_id)
    motor_nombre = config.get("motor")
    credenciales = config.get("credenciales")
    tabla = payload.get("tabla")
    reglas = payload.get("reglas", {})

    if not tabla:
        raise HTTPException(status_code=400, detail="Especifica la tabla a consultar.")

    motor = DatabaseFactory.obtener_motor(motor_nombre, credenciales)
    query, kwargs_extra = "", {}

    if motor_nombre in ("postgres", "mysql", "sqlserver", "sqlite"):
        query = f"SELECT TOP 100 * FROM {tabla}" if motor_nombre == "sqlserver" else f"SELECT * FROM {tabla} LIMIT 100"
    elif motor_nombre == "mongodb":
        query = {}; kwargs_extra["coleccion"] = tabla
    elif motor_nombre == "neo4j":
        query = f"MATCH (n:{tabla}) RETURN n LIMIT 100"
    elif motor_nombre == "redis":
        kwargs_extra["tipo_comando"] = "get"; query = tabla

    try:
        return monitor_overhead(motor_nombre, lambda: motor.ejecutar_consulta(query, **kwargs_extra), reglas)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GOBERNANZA SDM
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/governance/protect", tags=["Gobernanza SDM"])
async def activar_proteccion(request: Request, payload: Dict[str, Any] = Body(...)):
    connection_id = payload.get("connection_id")
    tabla = payload.get("tabla")
    reglas = payload.get("reglas", {})
    if not connection_id or not tabla:
        raise HTTPException(status_code=400, detail="Faltan connection_id y/o tabla.")
    if not reglas:
        raise HTTPException(status_code=400, detail="Define al menos una regla.")

    config = obtener_conexion(request, connection_id)
    motor_nombre = config.get("motor")
    if motor_nombre not in MOTORES_SDM_DISPONIBLES:
        raise HTTPException(
            status_code=400,
            detail=f"SDM no disponible para '{motor_nombre}'. Soportados: {', '.join(MOTORES_SDM_DISPONIBLES)}."
        )

    motor = DatabaseFactory.obtener_motor(motor_nombre, config.get("credenciales"))
    try:
        resultado = proteger_tabla(motor_nombre, motor, tabla, reglas, connection_id)
        return {"estado": "ACTIVA", "mensaje": f"SDM activado en '{tabla}'.", **resultado}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/governance/restore", tags=["Gobernanza SDM"])
async def revertir_proteccion(request: Request, payload: Dict[str, Any] = Body(...)):
    connection_id = payload.get("connection_id")
    tabla = payload.get("tabla")
    if not connection_id or not tabla:
        raise HTTPException(status_code=400, detail="Faltan connection_id y/o tabla.")

    config = obtener_conexion(request, connection_id)
    motor = DatabaseFactory.obtener_motor(config.get("motor"), config.get("credenciales"))
    try:
        resultado = restaurar_tabla(config.get("motor"), motor, tabla, connection_id)
        return {"estado": "INACTIVA", "mensaje": f"Datos restaurados en '{tabla}'.", **resultado}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/governance/status", tags=["Gobernanza SDM"])
async def estado_gobernanza(connection_id: str, tabla: str, request: Request):
    obtener_conexion(request, connection_id)
    return {"connection_id": connection_id, "tabla": tabla, "estado": obtener_estado(connection_id, tabla)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
