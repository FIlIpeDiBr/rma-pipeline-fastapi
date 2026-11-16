"""Fila de jobs (Procrastinate sobre o Postgres) — RNF-01/02."""

import procrastinate

from ..config import get_settings


def _conninfo() -> str:
    url = get_settings().database_url
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


# O CLI do Procrastinate (worker/schema) exige conector ASYNC (PsycopgConnector).
# Para enfileirar a partir da API, usamos defer_async() em endpoints async.
job_app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=_conninfo()),
    import_paths=["app.jobs.tasks"],
)
