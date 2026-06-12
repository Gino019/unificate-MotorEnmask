from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union
import psycopg2
from psycopg2.extras import RealDictCursor
import pymysql
import pymssql
from pymongo import MongoClient
import sqlite3
import redis
import json
from neo4j import GraphDatabase

class BaseDeDatos(ABC):
    """
    El contrato de la base de datos ahora exige recibir credenciales dinámicas
    y la capacidad de introspeccionar su propio esquema para alimentar la UI.
    """
    def __init__(self, credenciales: Dict[str, Any]):
        self.credenciales = credenciales

    @abstractmethod
    def conectar(self):
        pass

    @abstractmethod
    def obtener_esquema(self) -> Dict[str, List[str]]:
        """ Devuelve un diccionario { "nombre_tabla": ["col1", "col2"] } """
        pass

    @abstractmethod
    def ejecutar_consulta(self, query_o_filtro: Union[str, Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
        pass

class PostgresDB(BaseDeDatos):
    def conectar(self):
        return psycopg2.connect(
            host=self.credenciales.get('host'),
            port=int(self.credenciales.get('port', 5432)),
            user=self.credenciales.get('user'),
            password=self.credenciales.get('password'),
            dbname=self.credenciales.get('database'),
            cursor_factory=RealDictCursor
        )

    def obtener_esquema(self) -> Dict[str, List[str]]:
        esquema = {}
        query = """
            SELECT table_name, column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public'
        """
        resultados = self.ejecutar_consulta(query)
        for fila in resultados:
            t_name = fila['table_name']
            c_name = fila['column_name']
            if t_name not in esquema: esquema[t_name] = []
            esquema[t_name].append(c_name)
        return {"tablas": esquema}

    def ejecutar_consulta(self, query_o_filtro: str, **kwargs) -> List[Dict[str, Any]]:
        with self.conectar() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query_o_filtro)
                if cursor.description: return [dict(row) for row in cursor.fetchall()]
                return []

class MySQLDB(BaseDeDatos):
    def conectar(self):
        return pymysql.connect(
            host=self.credenciales.get('host'),
            port=int(self.credenciales.get('port', 3306)),
            user=self.credenciales.get('user'),
            password=self.credenciales.get('password'),
            database=self.credenciales.get('database'),
            cursorclass=pymysql.cursors.DictCursor
        )

    def obtener_esquema(self) -> Dict[str, List[str]]:
        esquema = {}
        db = self.credenciales.get('database')
        query = f"SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = '{db}'"
        resultados = self.ejecutar_consulta(query)
        for fila in resultados:
            t_name = fila.get('table_name') or fila.get('TABLE_NAME')
            c_name = fila.get('column_name') or fila.get('COLUMN_NAME')
            if t_name not in esquema: esquema[t_name] = []
            esquema[t_name].append(c_name)
        return {"tablas": esquema}

    def ejecutar_consulta(self, query_o_filtro: str, **kwargs) -> List[Dict[str, Any]]:
        conexion = self.conectar()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(query_o_filtro)
                if cursor.description: return cursor.fetchall()
                conexion.commit()
                return []
        finally:
            conexion.close()

class SQLiteDB(BaseDeDatos):
    def conectar(self):
        db_path = self.credenciales.get('database', 'local_monitor.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def obtener_esquema(self) -> Dict[str, List[str]]:
        esquema = {}
        tablas = self.ejecutar_consulta("SELECT name FROM sqlite_master WHERE type='table'")
        for t in tablas:
            t_name = t['name']
            cols = self.ejecutar_consulta(f"PRAGMA table_info({t_name})")
            esquema[t_name] = [c['name'] for c in cols]
        return {"tablas": esquema}

    def ejecutar_consulta(self, query_o_filtro: str, **kwargs) -> List[Dict[str, Any]]:
        with self.conectar() as conn:
            cursor = conn.cursor()
            cursor.execute(query_o_filtro)
            if cursor.description: return [dict(row) for row in cursor.fetchall()]
            conn.commit()
            return []

class SQLServerDB(BaseDeDatos):
    def conectar(self):
        return pymssql.connect(
            server=self.credenciales.get('host'),
            port=str(self.credenciales.get('port', 1433)),
            user=self.credenciales.get('user'),
            password=self.credenciales.get('password'),
            database=self.credenciales.get('database'),
            as_dict=True
        )

    def obtener_esquema(self) -> Dict[str, List[str]]:
        esquema = {}
        query = "SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"
        resultados = self.ejecutar_consulta(query)
        for fila in resultados:
            t_name = fila['TABLE_NAME']
            c_name = fila['COLUMN_NAME']
            if t_name not in esquema: esquema[t_name] = []
            esquema[t_name].append(c_name)
        return {"tablas": esquema}

    def ejecutar_consulta(self, query_o_filtro: str, **kwargs) -> List[Dict[str, Any]]:
        conexion = self.conectar()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(query_o_filtro)
                if cursor.description: return cursor.fetchall()
                conexion.commit()
                return []
        finally:
            conexion.close()

class MongoDB(BaseDeDatos):
    def conectar(self):
        # Para MongoDB, el usuario puede proveer URI directa o Host
        uri = self.credenciales.get('host', 'mongodb://localhost:27017/') 
        return MongoClient(uri)

    def obtener_esquema(self) -> Dict[str, List[str]]:
        esquema = {}
        cliente = self.conectar()
        try:
            db_name = self.credenciales.get('database')
            db = cliente[db_name]
            colecciones = db.list_collection_names()
            # Muestreo rápido de esquema
            for col_name in colecciones:
                doc = db[col_name].find_one()
                esquema[col_name] = list(doc.keys()) if doc else []
            return {"tablas": esquema}
        finally:
            cliente.close()

    def ejecutar_consulta(self, query_o_filtro: Dict[str, Any], coleccion: str = None, limit: int = 100, **kwargs) -> List[Dict[str, Any]]:
        if not coleccion: raise ValueError("MongoDB requiere 'coleccion'")
        cliente = self.conectar()
        try:
            db_name = self.credenciales.get('database')
            col = cliente[db_name][coleccion]
            resultados = list(col.find(query_o_filtro).limit(limit))
            for doc in resultados:
                if '_id' in doc: doc['_id'] = str(doc['_id'])
            return resultados
        finally:
            cliente.close()

class RedisDB(BaseDeDatos):
    def conectar(self):
        return redis.Redis(
            host=self.credenciales.get('host'),
            port=int(self.credenciales.get('port', 6379)),
            db=int(self.credenciales.get('database', 0)),
            password=self.credenciales.get('password') or None,
            decode_responses=True
        )

    def obtener_esquema(self) -> Dict[str, List[str]]:
        cliente = self.conectar()
        try:
            muestra = cliente.keys("*")[:5]
            esquema = {"redis_store": ["valor"]}
            if muestra:
                val = cliente.get(muestra[0])
                try:
                    obj = json.loads(val)
                    if isinstance(obj, dict): esquema["redis_store"] = list(obj.keys())
                except: pass
            return {"tablas": esquema}
        finally:
            cliente.close()

    def ejecutar_consulta(self, query_o_filtro: str, tipo_comando: str = "get", **kwargs) -> List[Dict[str, Any]]:
        cliente = self.conectar()
        try:
            if tipo_comando.lower() == "get":
                valor = cliente.get(query_o_filtro)
                try:
                    parsed = json.loads(valor) if valor else None
                    if isinstance(parsed, dict): return [parsed]
                except:
                    parsed = valor
                return [{"llave": query_o_filtro, "valor": parsed}]
            elif tipo_comando.lower() == "hgetall":
                return [cliente.hgetall(query_o_filtro)]
            return []
        finally:
            cliente.close()

class Neo4jDB(BaseDeDatos):
    def conectar(self):
        return GraphDatabase.driver(
            self.credenciales.get('host'), 
            auth=(self.credenciales.get('user'), self.credenciales.get('password'))
        )

    def obtener_esquema(self) -> Dict[str, List[str]]:
        driver = self.conectar()
        try:
            with driver.session() as session:
                result = session.run("MATCH (n) RETURN labels(n) AS labels, keys(n) AS properties LIMIT 5")
                esquema = {}
                for record in result:
                    labels, props = record["labels"], record["properties"]
                    if labels:
                        lbl = labels[0]
                        if lbl not in esquema: esquema[lbl] = []
                        esquema[lbl] = list(set(esquema[lbl] + props))
            return {"tablas": esquema}
        finally:
            driver.close()

    def ejecutar_consulta(self, query_o_filtro: str, parametros: Dict[str, Any] = None, **kwargs) -> List[Dict[str, Any]]:
        driver = self.conectar()
        try:
            with driver.session() as session:
                result = session.run(query_o_filtro, parameters=parametros or {})
                lista = []
                for record in result:
                    d = dict(record)
                    plana = {}
                    for k, v in d.items():
                        if hasattr(v, "items"): plana.update(dict(v.items()))
                        else: plana[k] = v
                    lista.append(plana)
                return lista
        finally:
            driver.close()

class DatabaseFactory:
    @staticmethod
    def obtener_motor(motor: str, credenciales: Dict[str, Any]) -> BaseDeDatos:
        motores = {
            "postgres": PostgresDB, "mysql": MySQLDB, "sqlserver": SQLServerDB,
            "sqlite": SQLiteDB, "mongodb": MongoDB, "redis": RedisDB, "neo4j": Neo4jDB
        }
        clase = motores.get(motor.lower())
        if not clase: raise ValueError(f"Motor '{motor}' no soportado.")
        return clase(credenciales)
