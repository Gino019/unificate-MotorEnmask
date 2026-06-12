import os
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Body, Depends, Form, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from config import settings
from database_manager import DatabaseFactory
from monitor import monitor_overhead
from auth import (
    crear_token_sesion, revocar_token, validar_credenciales, SESIONES_ACTIVAS, 
    obtener_sesion_actual, agregar_conexion, obtener_conexion, eliminar_conexion
)

app = FastAPI(
    title=settings.APP_NAME,
    description="Monitorización de Rendimiento y Enmascaramiento Multi-Motor (SecOps Universal)",
    version="3.0.0"
)

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

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
    if token: revocar_token(token)
    response = JSONResponse({"message": "Logout exitoso"})
    response.delete_cookie("session_token")
    return response

@app.get("/", tags=["Dashboard"])
async def serve_dashboard(request: Request):
    token = request.cookies.get("session_token")
    if not token or token not in SESIONES_ACTIVAS:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return FileResponse("static/index.html")

# --- ENDPOINTS PARA MÚLTIPLES CONEXIONES ---

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
    """ Retorna la lista de conexiones activas del usuario """
    conexiones = sesion.get("conexiones", {})
    lista = [{"id": cid, "alias": data.get("alias"), "motor": data.get("motor")} for cid, data in conexiones.items()]
    return {"conexiones": lista}

@app.delete("/api/v1/connections/{connection_id}", tags=["SecOps Universal"])
async def delete_connection(connection_id: str, request: Request, sesion: Dict[str, Any] = Depends(obtener_sesion_actual)):
    """ Cierra una base de datos específica """
    eliminar_conexion(request, connection_id)
    return {"message": "Conexión eliminada"}

@app.get("/api/v1/schema", tags=["SecOps Universal"])
async def get_schema(
    connection_id: str, 
    request: Request
):
    config = obtener_conexion(request, connection_id)
    return config.get("esquema_cache", {"tablas": {}})

@app.post("/api/v1/execute_test", tags=["SecOps Universal"])
async def ejecutar_test_dinamico(
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
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
        if motor_nombre == "sqlserver":
            query = f"SELECT TOP 100 * FROM {tabla}"
        else:
            query = f"SELECT * FROM {tabla} LIMIT 100"
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
