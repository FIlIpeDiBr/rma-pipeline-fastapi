"""Tarefas da fila (Procrastinate).

`processar_documento` é o pipeline de ingestão: idempotente, retomável e com
retry (RNF-01/02). `gerar_relatorio` monta o docx. `poll_email` varre a caixa.
"""

import structlog

from . import job_app

log = structlog.get_logger()


@job_app.task(name="processar_documento", retry=2)
def processar_documento(document_id: str) -> dict:
    # Import tardio evita carregar o pipeline (e suas deps) no import da fila.
    from ..extraction.pipeline import processar_documento as _processar

    return _processar(document_id)


@job_app.task(name="gerar_relatorio", retry=2)
def gerar_relatorio(report_id: str) -> dict:
    from ..reports.service import gerar_relatorio as _gerar

    return _gerar(report_id)


def _poll_email() -> dict:
    from ..email.ingest import sincronizar_caixa

    return sincronizar_caixa()


def _auto_poll_ativo() -> bool:
    """Lê o toggle do banco (Org.email_poll_ativo), com o env como porta global."""
    from ..config import get_settings

    if not get_settings().email_poll_enabled:
        return False
    from ..auth.users import get_or_create_org
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        org = get_or_create_org(db)
        db.commit()
        return bool(org.email_poll_ativo)
    finally:
        db.close()


@job_app.task(name="poll_email_manual")
def poll_email_manual() -> dict:
    return _poll_email()


@job_app.periodic(cron="*/5 * * * *")
@job_app.task(name="poll_email")
def poll_email(timestamp: int) -> dict:
    if not _auto_poll_ativo():
        return {"skip": True}
    return _poll_email()
