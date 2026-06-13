from fastapi import FastAPI, HTTPException, Body
import time
from typing import Dict, Any, List

from governance import proteger_tabla, restaurar_tabla, obtener_estado
from masking import aplicar_enmascaramiento
from database_manager import DatabaseFactory

app = FastAPI(title="SecOps Masking Service")

@app.post("/protect")
async def protect(payload: Dict[str, Any] = Body(...)):
    motor_nombre = payload.get("motor_nombre")
    credenciales = payload.get("credenciales")
    tabla = payload.get("tabla")
    reglas = payload.get("reglas")
    connection_id = payload.get("connection_id")
    
    try:
        motor = DatabaseFactory.obtener_motor(motor_nombre, credenciales)
        resultado = proteger_tabla(motor_nombre, motor, tabla, reglas, connection_id)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/restore")
async def restore(payload: Dict[str, Any] = Body(...)):
    motor_nombre = payload.get("motor_nombre")
    credenciales = payload.get("credenciales")
    tabla = payload.get("tabla")
    connection_id = payload.get("connection_id")
    
    try:
        motor = DatabaseFactory.obtener_motor(motor_nombre, credenciales)
        resultado = restaurar_tabla(motor_nombre, motor, tabla, connection_id)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mask")
async def mask(payload: Dict[str, Any] = Body(...)):
    datos = payload.get("datos", [])
    reglas = payload.get("reglas", {})
    
    inicio = time.perf_counter_ns()
    datos_enmascarados = aplicar_enmascaramiento(datos, reglas)
    fin = time.perf_counter_ns()
    
    tiempo_mask_ms = (fin - inicio) / 1_000_000.0
    return {
        "datos_enmascarados": datos_enmascarados,
        "tiempo_mask_ms": round(tiempo_mask_ms, 3)
    }

@app.get("/status")
async def status(connection_id: str, tabla: str):
    try:
        estado = obtener_estado(connection_id, tabla)
        return {"connection_id": connection_id, "tabla": tabla, "estado": estado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("masking_service:app", host="0.0.0.0", port=8001)
