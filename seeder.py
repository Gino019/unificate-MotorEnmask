import sys
import uuid
import json
import copy
from typing import List, Dict, Any
from faker import Faker
from database_manager import DatabaseFactory
from config import settings

# Forzar el locale a español para generar datos más realistas en nuestro contexto
fake = Faker('es_ES')

def generar_datos_falsos(cantidad: int) -> List[Dict[str, Any]]:
    print(f"Generando {cantidad} registros falsos en memoria...")
    datos = []
    for _ in range(cantidad):
        datos.append({
            "id": str(uuid.uuid4()),
            "nombre_completo": fake.name(),
            "correo_electronico": fake.email(),
            "numero_tarjeta_credito": fake.credit_card_number(),
            "fecha_registro": fake.date_time_this_decade().isoformat()
        })
    return datos

def sembrar_motor(motor_nombre: str, datos: List[Dict[str, Any]]):
    print(f"\nIntentando sembrar en el motor: {motor_nombre.upper()}...")
    try:
        motor = DatabaseFactory.obtener_motor(motor_nombre)
        
        if motor_nombre in ("postgres", "mysql", "sqlserver", "sqlite"):
            conn = motor.conectar()
            cursor = conn.cursor()
            
            if motor_nombre == "sqlserver":
                ddl = """
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='clientes' and xtype='U')
                CREATE TABLE clientes (
                    id VARCHAR(50) PRIMARY KEY,
                    nombre_completo VARCHAR(255),
                    correo_electronico VARCHAR(255),
                    numero_tarjeta_credito VARCHAR(255),
                    fecha_registro VARCHAR(50)
                )
                """
            else:
                ddl = """
                CREATE TABLE IF NOT EXISTS clientes (
                    id VARCHAR(50) PRIMARY KEY,
                    nombre_completo VARCHAR(255),
                    correo_electronico VARCHAR(255),
                    numero_tarjeta_credito VARCHAR(255),
                    fecha_registro VARCHAR(50)
                )
                """
            cursor.execute(ddl)
            
            if motor_nombre == "sqlite":
                query = "INSERT INTO clientes (id, nombre_completo, correo_electronico, numero_tarjeta_credito, fecha_registro) VALUES (:id, :nombre_completo, :correo_electronico, :numero_tarjeta_credito, :fecha_registro)"
                cursor.executemany(query, datos)
            else:
                query = "INSERT INTO clientes (id, nombre_completo, correo_electronico, numero_tarjeta_credito, fecha_registro) VALUES (%(id)s, %(nombre_completo)s, %(correo_electronico)s, %(numero_tarjeta_credito)s, %(fecha_registro)s)"
                cursor.executemany(query, datos)
                
            conn.commit()
            conn.close()
            print(f"[OK] {len(datos)} registros insertados en la tabla 'clientes' de {motor_nombre.upper()}.")

        elif motor_nombre == "mongodb":
            cliente = motor.conectar()
            db = cliente[settings.MONGO_DB]
            col = db["clientes"]
            col.insert_many(copy.deepcopy(datos))
            cliente.close()
            print(f"[OK] {len(datos)} documentos insertados en la colección 'clientes' de {motor_nombre.upper()}.")

        elif motor_nombre == "redis":
            cliente = motor.conectar()
            pipe = cliente.pipeline()
            for d in datos:
                pipe.set(f"cliente:{d['id']}", json.dumps(d))
            pipe.execute()
            cliente.close()
            print(f"[OK] {len(datos)} llaves insertadas con prefijo 'cliente:*' en {motor_nombre.upper()}.")

        elif motor_nombre == "neo4j":
            driver = motor.conectar()
            with driver.session() as session:
                query = """
                UNWIND $batch AS fila
                MERGE (c:Cliente {id: fila.id})
                SET c.nombre_completo = fila.nombre_completo,
                    c.correo_electronico = fila.correo_electronico,
                    c.numero_tarjeta_credito = fila.numero_tarjeta_credito,
                    c.fecha_registro = fila.fecha_registro
                """
                session.run(query, batch=datos)
            driver.close()
            print(f"[OK] {len(datos)} nodos 'Cliente' creados exitosamente en {motor_nombre.upper()}.")

    except Exception as e:
        print(f"[ERROR] BD no disponible o error insertando en {motor_nombre.upper()}:\n   -> {e}")

def mostrar_menu() -> List[str]:
    import sys
    motores_disponibles = ["postgres", "mysql", "sqlserver", "sqlite", "mongodb", "redis", "neo4j"]
    
    if len(sys.argv) > 1:
        opcion = sys.argv[1]
    else:
        print("\n" + "="*60)
        print(" SecOps Data Seeder - Generador de Datos Falsos")
        print("="*60)
        for i, m in enumerate(motores_disponibles, 1):
            print(f" [{i}] {m.capitalize()}")
        print(f" [8] INYECTAR A TODOS LOS MOTORES SIMULTÁNEAMENTE")
        print(" [0] Salir")
        print("="*60)
        opcion = input("Selecciona un motor para la prueba de carga (0-8): ")
    
    if opcion == '0':
        sys.exit()
    
    try:
        op_idx = int(opcion)
        if 1 <= op_idx <= 7:
            return [motores_disponibles[op_idx - 1]]
        elif op_idx == 8:
            return motores_disponibles
        else:
            print("Opción inválida.")
            return []
    except ValueError:
        print("Entrada inválida.")
        return []

if __name__ == "__main__":
    motores_a_sembrar = mostrar_menu()
    if motores_a_sembrar:
        cantidad_registros = 5000
        datos_falsos = generar_datos_falsos(cantidad_registros)
        
        for motor_destino in motores_a_sembrar:
            sembrar_motor(motor_destino, datos_falsos)
            
        print("\n[INFO] Proceso de siembra finalizado. Puedes probar el enmascaramiento desde el Dashboard.")
