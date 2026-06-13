FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Librerias runtime (sin build-essential — evita OOM en Render free)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    freetds-common \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

COPY scripts/render-start.sh /usr/local/bin/render-start.sh
RUN chmod +x /usr/local/bin/render-start.sh

EXPOSE 10000

CMD ["render-start.sh"]
