"""
main.py — SecOps Universal Monitor API v5.0
Autenticación: email + bcrypt (local).
"""

import os
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
from db_usuarios import (autenticar_usuario, init_db, registrar_usuario)
import time

load_dotenv()
MASKING_SERVICE_URL = os.getenv("MASKING_SERVICE_URL", "http://localhost:8001")
MONITOR_SERVICE_URL = os.getenv("MONITOR_SERVICE_URL", "http://localhost:8002")
MOTORES_SDM_DISPONIBLES = ["sqlite", "postgres", "sqlserver", "mongodb"]
# Render sirve HTTPS; las cookies deben marcarse secure en produccion
_COOKIE_SECURE = os.getenv("RENDER") == "true"

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


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "api"}


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
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax", secure=_COOKIE_SECURE)
    return response


@app.post("/api/login", tags=["Auth"])
async def login(correo: str = Form(...), password: str = Form(...)):
    usuario = autenticar_usuario(correo.strip().lower(), password)
    if not usuario:
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")

    token = crear_token_sesion(usuario["nombre_completo"], usuario["correo"], usuario.get("proveedor","local"))
    response = JSONResponse({"message": "Login exitoso.", "nombre": usuario["nombre_completo"]})
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax", secure=_COOKIE_SECURE)
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
        # 1. Medir tiempo de consulta cruda en base de datos
        inicio_db = time.perf_counter_ns()
        resultados_db = motor.ejecutar_consulta(query, **kwargs_extra)
        fin_db = time.perf_counter_ns()
        tiempo_db_ms = (fin_db - inicio_db) / 1_000_000.0

        tiempo_mask_ms = 0.0
        data_final = resultados_db or []

        # 2. Si hay reglas, delegar el enmascaramiento al Servicio de Masking
        if resultados_db and reglas:
            async with httpx.AsyncClient() as client:
                try:
                    from fastapi.encoders import jsonable_encoder
                    payload_json = jsonable_encoder({"datos": resultados_db, "reglas": reglas})
                    res = await client.post(
                        f"{MASKING_SERVICE_URL}/mask",
                        json=payload_json,
                        timeout=10.0
                    )
                    if res.status_code == 200:
                        res_json = res.json()
                        data_final = res_json.get("datos_enmascarados", [])
                        tiempo_mask_ms = res_json.get("tiempo_mask_ms", 0.0)
                    else:
                        raise Exception(f"Error del servicio de masking: {res.text}")
                except Exception as e:
                    raise HTTPException(status_code=502, detail=f"Fallo comunicación con Masking Service: {str(e)}")

        # 3. Enviar métricas al Monitor Service
        overhead_total_ms = tiempo_db_ms + tiempo_mask_ms
        metrics_payload = {
            "motor_utilizado": motor_nombre,
            "tiempo_bd_ms": round(tiempo_db_ms, 3),
            "tiempo_mask_ms": round(tiempo_mask_ms, 3),
            "overhead_total_ms": round(overhead_total_ms, 3),
            "filas_procesadas": len(data_final)
        }

        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"{MONITOR_SERVICE_URL}/metrics",
                    json=metrics_payload,
                    timeout=2.0
                )
            except Exception as e:
                print(f"[GATEWAY] Advertencia: No se pudieron enviar métricas al Monitor Service: {e}")

        # Formato de retorno exacto esperado por el frontend
        return {
            "motor_utilizado": motor_nombre,
            "tiempo_bd_ms": round(tiempo_db_ms, 3),
            "tiempo_enmascarado_ms": round(tiempo_mask_ms, 3),
            "overhead_total_ms": round(overhead_total_ms, 3),
            "filas_procesadas": len(data_final),
            "data": data_final
        }
    except HTTPException:
        raise
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

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{MASKING_SERVICE_URL}/protect",
                json={
                    "motor_nombre": motor_nombre,
                    "credenciales": config.get("credenciales"),
                    "tabla": tabla,
                    "reglas": reglas,
                    "connection_id": connection_id
                },
                timeout=30.0
            )
            if res.status_code == 200:
                resultado = res.json()
                return {"estado": "ACTIVA", "mensaje": f"SDM activado en '{tabla}'.", **resultado}
            elif res.status_code == 409:
                raise HTTPException(status_code=409, detail=res.json().get("detail", "Conflicto en pre-flight"))
            else:
                detail_msg = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
                raise HTTPException(status_code=res.status_code, detail=detail_msg)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Fallo comunicación con Masking Service: {str(e)}")


@app.post("/api/v1/governance/restore", tags=["Gobernanza SDM"])
async def revertir_proteccion(request: Request, payload: Dict[str, Any] = Body(...)):
    connection_id = payload.get("connection_id")
    tabla = payload.get("tabla")
    if not connection_id or not tabla:
        raise HTTPException(status_code=400, detail="Faltan connection_id y/o tabla.")

    config = obtener_conexion(request, connection_id)
    motor_nombre = config.get("motor")

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{MASKING_SERVICE_URL}/restore",
                json={
                    "motor_nombre": motor_nombre,
                    "credenciales": config.get("credenciales"),
                    "tabla": tabla,
                    "connection_id": connection_id
                },
                timeout=30.0
            )
            if res.status_code == 200:
                resultado = res.json()
                return {"estado": "INACTIVA", "mensaje": f"Datos restaurados en '{tabla}'.", **resultado}
            elif res.status_code == 409:
                raise HTTPException(status_code=409, detail=res.json().get("detail", "Conflicto en restauración"))
            else:
                detail_msg = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
                raise HTTPException(status_code=res.status_code, detail=detail_msg)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Fallo comunicación con Masking Service: {str(e)}")


@app.get("/api/v1/governance/status", tags=["Gobernanza SDM"])
async def estado_gobernanza(connection_id: str, tabla: str, request: Request):
    config = obtener_conexion(request, connection_id)

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{MASKING_SERVICE_URL}/status",
                json={
                    "connection_id": connection_id,
                    "tabla": tabla,
                    "motor_nombre": config.get("motor"),
                    "credenciales": config.get("credenciales")
                },
                timeout=5.0
            )
            if res.status_code == 200:
                return res.json()
            else:
                detail_msg = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
                raise HTTPException(status_code=res.status_code, detail=detail_msg)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Fallo comunicación con Masking Service: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

