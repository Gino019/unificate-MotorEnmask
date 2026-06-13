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

@app.post("/status")
async def status(payload: Dict[str, Any] = Body(...)):
    connection_id = payload.get("connection_id")
    tabla = payload.get("tabla")
    motor_nombre = payload.get("motor_nombre")
    credenciales = payload.get("credenciales")
    
    try:
        estado = obtener_estado(connection_id, tabla)
        
        # Auto-sanación: si figura INACTIVA pero la tabla de backup física existe,
        # retornamos ACTIVA para habilitar el botón de restauración en el frontend.
        if estado == "INACTIVA" and motor_nombre and credenciales:
            try:
                motor = DatabaseFactory.obtener_motor(motor_nombre, credenciales)
                backup = tabla + "__backup_enc"
                existe = False
                
                if motor_nombre == "sqlite":
                    res = motor.ejecutar_consulta(
                        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{backup}'"
                    )
                    existe = len(res) > 0
                elif motor_nombre == "postgres":
                    res = motor.ejecutar_consulta(f"SELECT to_regclass('public.\"{backup}\"') AS existe")
                    existe = len(res) > 0 and res[0].get("existe") is not None
                elif motor_nombre == "sqlserver":
                    res = motor.ejecutar_consulta(f"SELECT OBJECT_ID('{backup}', 'U') AS existe")
                    existe = len(res) > 0 and res[0].get("existe") is not None
                elif motor_nombre == "mongodb":
                    cliente = motor.conectar()
                    db_name = motor.credenciales.get("database")
                    db = cliente[db_name]
                    existe = backup in db.list_collection_names()
                    cliente.close()
                    
                if existe:
                    estado = "ACTIVA"
            except Exception:
                pass
                
        return {"connection_id": connection_id, "tabla": tabla, "estado": estado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("masking_service:app", host="0.0.0.0", port=8001)
