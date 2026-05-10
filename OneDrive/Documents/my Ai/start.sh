#!/usr/bin/env bash
set -euo pipefail

export PORT="${PORT:-10000}"

# Render sets PORT; bind to 0.0.0.0 for external traffic.
exec gunicorn \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --worker-class "uvicorn.workers.UvicornWorker" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  "app:app"

