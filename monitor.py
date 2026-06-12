import time
from typing import Callable, Dict, Any

def monitor_overhead(motor_nombre: str, ejecutar_db_func: Callable, reglas: Dict[str, str]) -> Dict[str, Any]:
    """
    Middleware que calcula el overhead quirúrgico en milisegundos
    utilizando reglas dinámicas por columna.
    """
    # ====================================================
    # DELTA 1: TIEMPO DE CONSULTA CRUDA EN BASE DE DATOS
    # ====================================================
    inicio_db = time.perf_counter_ns()
    resultados_db = ejecutar_db_func()
    fin_db = time.perf_counter_ns()
    
    tiempo_db_ms = (fin_db - inicio_db) / 1_000_000.0
    
    if not resultados_db or not reglas:
        return {
            "motor_utilizado": motor_nombre,
            "tiempo_bd_ms": round(tiempo_db_ms, 3),
            "tiempo_enmascarado_ms": 0.0,
            "overhead_total_ms": round(tiempo_db_ms, 3),
            "filas_procesadas": len(resultados_db) if resultados_db else 0,
            "data": resultados_db or []
        }

    # ====================================================
    # DELTA 2: TIEMPO DE PROCESAMIENTO (ENMASCARAMIENTO DINÁMICO)
    # ====================================================
    import masking # Inline import to avoid circular dependencies if any
    
    inicio_mask = time.perf_counter_ns()
    resultados_enmascarados = masking.aplicar_enmascaramiento(resultados_db, reglas)
    fin_mask = time.perf_counter_ns()

    tiempo_mask_ms = (fin_mask - inicio_mask) / 1_000_000.0
    
    # CÁLCULO FINAL
    overhead_total_ms = tiempo_db_ms + tiempo_mask_ms

    return {
        "motor_utilizado": motor_nombre,
        "tiempo_bd_ms": round(tiempo_db_ms, 3),
        "tiempo_enmascarado_ms": round(tiempo_mask_ms, 3),
        "overhead_total_ms": round(overhead_total_ms, 3),
        "filas_procesadas": len(resultados_enmascarados),
        "data": resultados_enmascarados
    }
