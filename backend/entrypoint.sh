#!/bin/sh
set -e

if [ "$SERVICE_ROLE" = "worker" ]; then
  echo "[entrypoint] iniciando worker Procrastinate"
  exec procrastinate --app=app.jobs.job_app worker --concurrency="${WORKER_CONCURRENCY:-4}"
else
  echo "[entrypoint] aplicando migrations"
  alembic upgrade head
  echo "[entrypoint] aplicando schema do Procrastinate (idempotente)"
  procrastinate --app=app.jobs.job_app schema --apply || true
  echo "[entrypoint] iniciando API web"
  exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
fi
