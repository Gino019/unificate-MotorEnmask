# Usamos una imagen oficial y ligera de Python
FROM python:3.11-slim

# Evitar escritura de .pyc y mantener stdout unbuffered
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Instalamos dependencias a nivel de sistema que requieren algunos drivers (ej: psycopg2, pymssql)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    freetds-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiamos requerimientos e instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos todo el código fuente y archivos estáticos
COPY . .

# Exponemos el puerto de FastAPI
EXPOSE 8000

# Iniciamos el servidor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
