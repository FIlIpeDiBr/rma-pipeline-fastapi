"""Health check usado pelo Render (healthCheckPath) e pelo portal."""

from fastapi import APIRouter
from sqlalchemy import text

from .. import storage
from ..db import engine

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "ok"
    except Exception as exc:  # noqa: BLE001 - health check reporta qualquer falha
        db = f"erro: {exc.__class__.__name__}"

    return {"status": "ok", "db": db, "storage": storage.healthcheck()}
