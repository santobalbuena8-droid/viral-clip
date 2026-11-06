#!/usr/bin/env bash
# Arranca Viral Clip en 0.0.0.0:8741 (accesible desde el celular en la misma Wi‑Fi).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export MAX_DURATION_SEC="${MAX_DURATION_SEC:-7200}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8741}"

if [[ -x "$ROOT/.venv/bin/uvicorn" ]]; then
  UV="$ROOT/.venv/bin/uvicorn"
elif command -v uvicorn >/dev/null 2>&1; then
  UV="uvicorn"
else
  echo "No encuentro uvicorn. Crea el venv e instala deps:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "AVISO: ffmpeg no está en el PATH. Instálalo antes de crear clips."
fi

echo "Viral Clip en http://0.0.0.0:${PORT}"
echo "En el celular / Chrome usa http://TU_IP_LAN:${PORT}"
echo "MAX_DURATION_SEC=${MAX_DURATION_SEC}"
exec "$UV" app.main:app --host "$HOST" --port "$PORT"
