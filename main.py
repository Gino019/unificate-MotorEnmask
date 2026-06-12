import os
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Body, Depends, Form, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from config import settings
from database_manager import DatabaseFactory
from monitor import monitor_overhead
from governance import proteger_tabla, restaurar_tabla, obtener_estado
from auth import (
    crear_token_sesion, revocar_token, validar_credenciales, SESIONES_ACTIVAS,
    obtener_sesion_actual, agregar_conexion, obtener_conexion, eliminar_conexion
)

app = FastAPI(
    title=settings.APP_NAME,
    description="Monitorización de Rendimiento y Enmascaramiento Multi-Motor (SecOps Universal)",
    version="4.0.0"
)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/login", tags=["Auth"])
async def serve_login():
    return FileResponse("static/login.html")

@app.post("/api/login", tags=["Auth"])
async def login(username: str = Form(...), password: str = Form(...)):
    if validar_credenciales(username, password):
        token = crear_token_sesion(username)
        response = JSONResponse({"message": "Login exitoso"})
        response.set_cookie(key="session_token", value=token, httponly=True)
        return response
    raise HTTPException(status_code=401, detail="Credenciales inválidas")

@app.post("/api/logout", tags=["Auth"])
async def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        revocar_token(token)
    response = JSONResponse({"message": "Logout exitoso"})
    response.delete_cookie("session_token")
    return response

@app.get("/", tags=["Dashboard"])
async def serve_dashboard(request: Request):
    token = request.cookies.get("session_token")
    if not token or token not in SESIONES_ACTIVAS:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return FileResponse("static/index.html")


# ─────────────────────────────────────────────────────────────────────────────
# CONEXIONES MÚLTIPLES
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/connect", tags=["SecOps Universal"])
async def conectar_db(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    sesion: Dict[str, Any] = Depends(obtener_sesion_actual)
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
    lista = [{"id": cid, "alias": data.get("alias"), "motor": data.get("motor")} for cid, data in conexiones.items()]
    return {"conexiones": lista}

@app.delete("/api/v1/connections/{connection_id}", tags=["SecOps Universal"])
async def delete_connection(connection_id: str, request: Request, sesion: Dict[str, Any] = Depends(obtener_sesion_actual)):
    eliminar_conexion(request, connection_id)
    return {"message": "Conexión eliminada"}

@app.get("/api/v1/schema", tags=["SecOps Universal"])
async def get_schema(connection_id: str, request: Request):
    config = obtener_conexion(request, connection_id)
    return config.get("esquema_cache", {"tablas": {}})

@app.post("/api/v1/execute_test", tags=["SecOps Universal"])
async def ejecutar_test_dinamico(request: Request, payload: Dict[str, Any] = Body(...)):
    connection_id = payload.get("connection_id")
    if not connection_id:
        raise HTTPException(status_code=400, detail="Falta connection_id en el payload")

    config = obtener_conexion(request, connection_id)
    motor_nombre = config.get("motor")
    credenciales = config.get("credenciales")
    tabla = payload.get("tabla")
    reglas = payload.get("reglas", {})

    if not tabla:
        raise HTTPException(status_code=400, detail="Especifica la tabla a consultar.")

    motor = DatabaseFactory.obtener_motor(motor_nombre, credenciales)

    query = ""
    kwargs_extra = {}
    if motor_nombre in ("postgres", "mysql", "sqlserver", "sqlite"):
        query = f"SELECT TOP 100 * FROM {tabla}" if motor_nombre == "sqlserver" else f"SELECT * FROM {tabla} LIMIT 100"
    elif motor_nombre == "mongodb":
        query = {}
        kwargs_extra["coleccion"] = tabla
    elif motor_nombre == "neo4j":
        query = f"MATCH (n:{tabla}) RETURN n LIMIT 100"
    elif motor_nombre == "redis":
        kwargs_extra["tipo_comando"] = "get"
        query = tabla

    def ejecutar_db_wrapper():
        return motor.ejecutar_consulta(query, **kwargs_extra)

    try:
        return monitor_overhead(motor_nombre, ejecutar_db_wrapper, reglas)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# GOBERNANZA DE DATOS (SDM)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/governance/protect", tags=["Gobernanza SDM"])
async def activar_proteccion(
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    """
    Ejecuta el Static Data Masking sobre la tabla real.
    Requiere: connection_id, tabla, reglas.
    ADVERTENCIA: Operación con efecto permanente en la BD. Incluye Pre-flight check.
    """
    connection_id = payload.get("connection_id")
    tabla = payload.get("tabla")
    reglas = payload.get("reglas", {})

    if not connection_id or not tabla:
        raise HTTPException(status_code=400, detail="Faltan connection_id y/o tabla.")
    if not reglas:
        raise HTTPException(status_code=400, detail="Define al menos una regla de enmascaramiento antes de proteger.")

    config = obtener_conexion(request, connection_id)
    motor_nombre = config.get("motor")
    credenciales = config.get("credenciales")

    if motor_nombre not in ("sqlite", "postgres", "mongodb"):
        raise HTTPException(status_code=400, detail=f"SDM no disponible para '{motor_nombre}'. Soportados: sqlite, postgres, mongodb.")

    motor = DatabaseFactory.obtener_motor(motor_nombre, credenciales)

    try:
        resultado = proteger_tabla(motor_nombre, motor, tabla, reglas, connection_id)
        return {
            "estado": "ACTIVA",
            "mensaje": f"Proteccion SDM activada en '{tabla}'.",
            **resultado
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante SDM: {str(e)}")


@app.post("/api/v1/governance/restore", tags=["Gobernanza SDM"])
async def revertir_proteccion(
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    """
    Descifra el backup y restaura los datos originales en la tabla.
    Requiere: connection_id, tabla.
    """
    connection_id = payload.get("connection_id")
    tabla = payload.get("tabla")

    if not connection_id or not tabla:
        raise HTTPException(status_code=400, detail="Faltan connection_id y/o tabla.")

    config = obtener_conexion(request, connection_id)
    motor_nombre = config.get("motor")
    credenciales = config.get("credenciales")

    motor = DatabaseFactory.obtener_motor(motor_nombre, credenciales)

    try:
        resultado = restaurar_tabla(motor_nombre, motor, tabla, connection_id)
        return {
            "estado": "INACTIVA",
            "mensaje": f"Datos originales restaurados en '{tabla}'.",
            **resultado
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante restauracion: {str(e)}")


@app.get("/api/v1/governance/status", tags=["Gobernanza SDM"])
async def estado_gobernanza(connection_id: str, tabla: str, request: Request):
    """Consulta si la protección SDM está activa para una tabla específica."""
    obtener_conexion(request, connection_id)  # Valida que la conexión exista
    estado = obtener_estado(connection_id, tabla)
    return {"connection_id": connection_id, "tabla": tabla, "estado": estado}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
