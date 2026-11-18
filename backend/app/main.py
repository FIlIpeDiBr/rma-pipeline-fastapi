"""Aplicação FastAPI — serve a API e a SPA buildada."""

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .api import companies, documents, email, events, health, indicadores, me, reports
from .auth import oidc
from .config import get_settings
from .logging_setup import setup_logging
from .sentry_setup import setup_sentry

settings = get_settings()
setup_logging()
setup_sentry()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from .eventos import barramento
    from .jobs import _conninfo, job_app

    try:
        await job_app.open_async()
        log.info("fila_conectada")
    except Exception as exc:  # noqa: BLE001 - app sobe mesmo sem fila (healthz reporta)
        log.warning("fila_indisponivel", erro=str(exc))
    # Um LISTEN por processo para o progresso em tempo real; sem ele o SSE consulta o banco.
    if _conninfo().startswith("postgresql"):
        await barramento.iniciar(_conninfo())
    yield
    await barramento.parar()
    try:
        await job_app.close_async()
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title="RMA v2", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=settings.is_production,
    same_site="lax",
)

app.include_router(health.router)
app.include_router(oidc.router, prefix="/auth", tags=["auth"])
app.include_router(me.router, prefix="/api", tags=["api"])
app.include_router(events.router, prefix="/api", tags=["api"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(indicadores.router, prefix="/api", tags=["indicadores"])
app.include_router(companies.router, prefix="/api", tags=["companies"])
app.include_router(reports.router, prefix="/api", tags=["reports"])
app.include_router(email.router, prefix="/api", tags=["email"])

_static = Path(__file__).parent / "static"
if _static.exists():
    app.mount("/", StaticFiles(directory=_static, html=True), name="spa")
else:

    @app.get("/", include_in_schema=False)
    def _raiz_dev() -> dict:
        return {
            "app": "RMA v2",
            "ambiente": settings.environment,
            "dica": "Em dev a interface roda no Vite (:5173); docs da API em /docs.",
        }
