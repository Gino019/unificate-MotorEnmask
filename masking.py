"""
masking.py — Motor de Enmascaramiento Dinámico
La clave Fernet se genera UNA vez y se persiste en .keyfile.
Si el servidor se reinicia, la clave se recupera del archivo y los backups SDM
siguen siendo descifrables.
"""
import hashlib
import os
from cryptography.fernet import Fernet
from typing import List, Dict, Any

KEYFILE_PATH = ".keyfile"

def _cargar_o_generar_clave() -> bytes:
    """
    Garantiza que la clave Fernet siempre sea la misma entre reinicios.
    Si no existe el archivo, lo crea con permisos restrictivos.
    """
    if os.path.exists(KEYFILE_PATH):
        with open(KEYFILE_PATH, "rb") as f:
            clave = f.read().strip()
        print(f"[KEYFILE] Clave Fernet cargada desde '{KEYFILE_PATH}'.")
        return clave
    else:
        clave = Fernet.generate_key()
        with open(KEYFILE_PATH, "wb") as f:
            f.write(clave)
        # Permisos de solo lectura para el propietario en sistemas Unix/Linux
        try:
            os.chmod(KEYFILE_PATH, 0o600)
        except AttributeError:
            pass  # Windows no soporta chmod de la misma forma, ignorar.
        print(f"[KEYFILE] Nueva clave Fernet generada y guardada en '{KEYFILE_PATH}'.")
        return clave


# Clave global persistente — se carga una sola vez al importar el módulo
FERNET_KEY = _cargar_o_generar_clave()
cipher_suite = Fernet(FERNET_KEY)


def aplicar_enmascaramiento(datos: List[Dict[str, Any]], reglas: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Motor de reglas dinámicas. Recibe:
      - datos: Lista de diccionarios (filas de la BD)
      - reglas: {"nombre_columna": "algoritmo"} configurado por el usuario en la UI
    Retorna la misma lista con los valores sensibles transformados.
    """
    if not reglas:
        return datos

    datos_enmascarados = []
    for fila in datos:
        nueva_fila = fila.copy()
        for columna, algoritmo in reglas.items():
            if columna in nueva_fila and isinstance(nueva_fila[columna], str):
                valor = nueva_fila[columna]

                # ── 1. REDACCIÓN DESTRUCTIVA ──────────────────────────────
                if algoritmo == "redaccion":
                    nueva_fila[columna] = "X" * len(valor)

                # ── 2. HASHING RÁPIDO (SHA-256) ───────────────────────────
                elif algoritmo == "hashing":
                    nueva_fila[columna] = (
                        hashlib.sha256(valor.encode("utf-8")).hexdigest()[:16] + "..."
                    )

                # ── 3. ENCRIPTACIÓN REVERSIBLE (FERNET / AES-128-CBC) ─────
                elif algoritmo == "encriptacion":
                    token = cipher_suite.encrypt(valor.encode("utf-8"))
                    nueva_fila[columna] = f"enc::{token.decode('utf-8')[:30]}..."

                # ── 4. FPE SIMULADO (ALTA CARGA DE CPU) ───────────────────
                elif algoritmo == "fpe":
                    hash_val = valor.encode("utf-8")
                    for _ in range(5000):
                        hash_val = hashlib.sha256(hash_val).digest()
                    nueva_fila[columna] = hash_val.hex()[: len(valor)]

        datos_enmascarados.append(nueva_fila)
    return datos_enmascarados


def cifrar_valor(texto: str) -> str:
    """Cifra un string con la clave Fernet persistente. Usado por SDM para backups."""
    return cipher_suite.encrypt(texto.encode("utf-8")).decode("utf-8")


def descifrar_valor(token: str) -> str:
    """Descifra un token Fernet. Usado por SDM durante la restauración."""
    return cipher_suite.decrypt(token.encode("utf-8")).decode("utf-8")
