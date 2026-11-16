"""API de email: fila de revisão, importação seletiva e toggle de varredura (RF-47/49)."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import current_org_id
from ..db import get_db
from ..email import graph, ingest
from ..models import EMAIL_PENDENTE, EmailMessage, Org

router = APIRouter()
log = structlog.get_logger()


class ToggleIn(BaseModel):
    auto: bool


class ImportarIn(BaseModel):
    attachment_ids: list[str]


@router.get("/email/status")
def status(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    from ..config import get_settings

    org = db.get(Org, org_id)
    pendentes = db.scalar(
        select(func.count(EmailMessage.id)).where(
            EmailMessage.org_id == org_id, EmailMessage.status == EMAIL_PENDENTE
        )
    ) or 0
    return {
        "configurado": graph.configurado(),
        "caixa": get_settings().rma_mailbox or None,
        "auto": bool(org.email_poll_ativo) if org else False,
        "pendentes": pendentes,
    }


@router.patch("/email/settings")
def settings(
    body: ToggleIn,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    org = db.get(Org, org_id)
    if org is None:
        raise HTTPException(404, "Organização não encontrada.")
    org.email_poll_ativo = body.auto
    db.commit()
    return {"auto": org.email_poll_ativo}


@router.post("/email/sync")
async def sincronizar(org_id: Annotated[uuid.UUID, Depends(current_org_id)]) -> dict:
    """Enfileira uma busca imediata da caixa para a fila de revisão."""
    if not graph.configurado():
        raise HTTPException(503, "Integração de email não configurada (AZURE_* / RMA_MAILBOX).")
    from ..jobs.tasks import poll_email_manual

    try:
        await poll_email_manual.defer_async()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Fila indisponível ({exc.__class__.__name__}).") from exc
    return {"status": "disparado"}


@router.get("/email/messages")
def mensagens(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return {"mensagens": ingest.listar_pendentes(db, org_id)}


@router.post("/email/messages/{message_id}/import")
async def importar(
    message_id: uuid.UUID,
    body: ImportarIn,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    res = ingest.importar(db, org_id, message_id, body.attachment_ids)
    if res.get("erro"):
        raise HTTPException(404, res["erro"])
    docs = res.get("documentos", [])

    from ..jobs.tasks import processar_documento

    avisos = []
    for d in docs:
        try:
            await processar_documento.defer_async(document_id=d["id"])
        except Exception as exc:  # noqa: BLE001
            avisos.append(f"{d['nome']}: fila indisponível ({exc.__class__.__name__})")

    if docs:
        nomes = ", ".join(d["nome"] for d in docs)
        graph.responder(
            res["message_id"],
            f"Recebemos e estamos processando os documentos: {nomes}.",
        )
    return {"importados": len(docs), "documentos": docs, "avisos": avisos}


@router.post("/email/messages/{message_id}/ignore")
def ignorar(
    message_id: uuid.UUID,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    res = ingest.ignorar(db, org_id, message_id)
    if res.get("erro"):
        raise HTTPException(404, res["erro"])
    return res
