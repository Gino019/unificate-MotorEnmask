import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import Body, FastAPI, HTTPException

from config import settings

app = FastAPI(title="SecOps Monitor Service")
DB_NAME = os.path.join(settings.DATA_DIR, "monitor_metrics.db")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            motor_utilizado TEXT,
            tiempo_bd_ms REAL,
            tiempo_mask_ms REAL,
            overhead_total_ms REAL,
            filas_procesadas INTEGER,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.get("/health")
async def health():
    return {"status": "ok", "service": "monitor"}

def _get_conn():
    return sqlite3.connect(DB_NAME)

@app.post("/metrics")
async def save_metrics(payload: Dict[str, Any] = Body(...)):
    motor_utilizado = payload.get("motor_utilizado")
    tiempo_bd_ms = payload.get("tiempo_bd_ms")
    tiempo_mask_ms = payload.get("tiempo_mask_ms")
    overhead_total_ms = payload.get("overhead_total_ms")
    filas_procesadas = payload.get("filas_procesadas")
    timestamp = datetime.now(timezone.utc).isoformat()
    
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO metrics (motor_utilizado, tiempo_bd_ms, tiempo_mask_ms, overhead_total_ms, filas_procesadas, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (motor_utilizado, tiempo_bd_ms, tiempo_mask_ms, overhead_total_ms, filas_procesadas, timestamp))
        conn.commit()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, motor_utilizado, tiempo_bd_ms, tiempo_mask_ms, overhead_total_ms, filas_procesadas, timestamp FROM metrics ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        
        metrics = []
        for r in rows:
            metrics.append({
                "id": r[0],
                "motor_utilizado": r[1],
                "tiempo_bd_ms": r[2],
                "tiempo_mask_ms": r[3],
                "overhead_total_ms": r[4],
                "filas_procesadas": r[5],
                "timestamp": r[6]
            })
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("monitor_service:app", host="0.0.0.0", port=8002)
