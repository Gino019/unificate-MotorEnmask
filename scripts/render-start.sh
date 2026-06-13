#!/bin/sh
set -e

APP="${UVICORN_APP:-main:app}"
PORT="${PORT:-10000}"

echo "[RENDER] Iniciando uvicorn ${APP} en 0.0.0.0:${PORT}"
exec uvicorn "${APP}" --host 0.0.0.0 --port "${PORT}"
