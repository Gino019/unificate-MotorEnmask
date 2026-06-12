import hashlib
from cryptography.fernet import Fernet
from typing import List, Dict, Any

FERNET_KEY = Fernet.generate_key()
cipher_suite = Fernet(FERNET_KEY)

def aplicar_enmascaramiento(datos: List[Dict[str, Any]], reglas: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Motor central unificado de SecOps. Aplica dinámicamente las reglas especificadas
    por el usuario según el esquema `{"columna": "algoritmo"}`.
    Soporta aplicar diferentes algoritmos a múltiples columnas en la misma pasada.
    """
    if not reglas:
        return datos

    datos_enmascarados = []
    for fila in datos:
        nueva_fila = fila.copy()
        
        # Iteramos las reglas configuradas por el usuario
        for columna, algoritmo in reglas.items():
            if columna in nueva_fila and isinstance(nueva_fila[columna], str):
                valor = nueva_fila[columna]
                
                # 1. REDACCIÓN DESTRUCTIVA
                if algoritmo == "redaccion":
                    nueva_fila[columna] = "X" * len(valor)
                
                # 2. HASHING RÁPIDO
                elif algoritmo == "hashing":
                    nueva_fila[columna] = hashlib.sha256(valor.encode('utf-8')).hexdigest()[:16] + "..."
                
                # 3. ENCRIPTACIÓN REVERSIBLE (FERNET)
                elif algoritmo == "encriptacion":
                    token = cipher_suite.encrypt(valor.encode('utf-8'))
                    nueva_fila[columna] = f"enc::{token.decode('utf-8')[:30]}..."
                
                # 4. FPE SIMULADO (CARGA EXTREMA DE CPU)
                elif algoritmo == "fpe":
                    hash_val = valor.encode('utf-8')
                    for _ in range(5000): # Simulación deliberada de ciclos pesados para monitoreo
                        hash_val = hashlib.sha256(hash_val).digest()
                    nueva_fila[columna] = hash_val.hex()[:len(valor)]
                    
        datos_enmascarados.append(nueva_fila)
    return datos_enmascarados
