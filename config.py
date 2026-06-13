import os
from pydantic_settings import BaseSettings, SettingsConfigDict


def ensure_data_dir(path: str) -> str:
    """Crea el directorio de datos persistentes si no existe."""
    os.makedirs(path, exist_ok=True)
    return path


class Settings(BaseSettings):
    # Configuración de la aplicación
    APP_NAME: str = "Multi-DB Masking & Performance Overhead Monitor"
    DEBUG: bool = True
    DATA_DIR: str = os.getenv("DATA_DIR", ".")
    
    # PostgreSQL Config
    PG_HOST: str = os.getenv("PG_HOST", "localhost")
    PG_PORT: int = int(os.getenv("PG_PORT", 5432))
    PG_USER: str = os.getenv("PG_USER", "postgres")
    PG_PASSWORD: str = os.getenv("PG_PASSWORD", "postgres")
    PG_DB: str = os.getenv("PG_DB", "postgres")

    # MySQL Config
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "root")
    MYSQL_DB: str = os.getenv("MYSQL_DB", "mysql")

    # SQL Server Config
    MSSQL_HOST: str = os.getenv("MSSQL_HOST", "localhost")
    MSSQL_PORT: int = int(os.getenv("MSSQL_PORT", 1433))
    MSSQL_USER: str = os.getenv("MSSQL_USER", "sa")
    MSSQL_PASSWORD: str = os.getenv("MSSQL_PASSWORD", "StrongPassword123!")
    MSSQL_DB: str = os.getenv("MSSQL_DB", "master")

    # MongoDB Config
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB: str = os.getenv("MONGO_DB", "admin")

    # SQLite Config
    SQLITE_DB_PATH: str = os.getenv("SQLITE_DB_PATH", "local_monitor.db")

    # Redis Config
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    # Neo4j Config
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "password")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Instancia global de las configuraciones
settings = Settings()
ensure_data_dir(settings.DATA_DIR)
