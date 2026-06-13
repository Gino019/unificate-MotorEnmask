# ─── Imagen base ──────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Evitar escritura de .pyc y mantener stdout/stderr sin buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencias del sistema necesarias para drivers de BD (pymssql, psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    freetds-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copiar código fuente y archivos estáticos
COPY . .

# Directorio de datos persistentes (montado como volumen en producción)
RUN mkdir -p /app/data

# Puerto de FastAPI
EXPOSE 8000

# Iniciar API Gateway por defecto (sobreescribible en docker-compose.yml)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
