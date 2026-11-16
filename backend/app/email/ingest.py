"""Recepção por email com fila de revisão (RF-47).

Segurança: o polling apenas BUSCA emails da caixa rma@ para uma fila de revisão
(`email_messages`/`email_attachments`); nada entra no pipeline automaticamente.
Pela tela, o usuário escolhe quais anexos importar.
"""

import hashlib

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..models import (
    EMAIL_IGNORADO,
    EMAIL_PENDENTE,
    EMAIL_PROCESSADO,
    STATUS_RECEBIDO,
    Company,
    Document,
    EmailAttachment,
    EmailMessage,
)
from . import graph

log = structlog.get_logger()

EXTS_DOC = {
    "pdf", "xlsx", "xlsm", "xls", "csv", "ods",
    "png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff",
}


def _ext(nome: str) -> str:
    return nome.lower().rsplit(".", 1)[-1] if "." in nome else ""


def sincronizar_caixa(limite: int = 25) -> dict:
    """Busca emails não lidos com anexos e guarda na fila de revisão (sem importar)."""
    if not graph.configurado():
        return {"erro": "Graph não configurado (AZURE_* / RMA_MAILBOX ausentes)."}

    from ..auth.users import get_or_create_org
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        org = get_or_create_org(db)
        db.commit()
        try:
            mensagens = graph.listar_nao_lidas(limite)
        except graph.GraphError as exc:
            log.warning("graph_listar_falhou", erro=str(exc))
            return {"erro": str(exc)}

        novos = 0
        for msg in mensagens:
            mid = msg["id"]
            ja = db.scalar(
                select(EmailMessage.id).where(
                    EmailMessage.org_id == org.id, EmailMessage.message_id == mid
                )
            )
            if ja is not None:
                graph.marcar_lida(mid)
                continue
            try:
                anexos = graph.baixar_anexos(mid)
            except graph.GraphError as exc:
                log.warning("graph_anexos_falhou", erro=str(exc))
                continue
            if not anexos:  # só imagens de assinatura / sem arquivos -> ignora
                graph.marcar_lida(mid)
                continue

            em = EmailMessage(
                org_id=org.id, message_id=mid, remetente=graph.remetente(msg),
                assunto=graph.assunto(msg)[:500], corpo=graph.texto_corpo(msg),
                recebido_em=graph.recebido_em(msg), status=EMAIL_PENDENTE,
            )
            db.add(em)
            db.flush()
            for ax in anexos:
                att = EmailAttachment(
                    email_message_id=em.id, org_id=org.id, nome=ax["nome"],
                    content_type=ax["content_type"], tamanho=len(ax["data"]),
                    suportado=_ext(ax["nome"]) in EXTS_DOC, storage_key="",
                )
                db.add(att)
                db.flush()
                key = f"email/{org.id}/{att.id}/{ax['nome']}"
                storage.save_bytes(
                    key, ax["data"], ax["content_type"] or "application/octet-stream"
                )
                att.storage_key = key
            db.commit()
            graph.marcar_lida(mid)  # sai dos não-lidos; permanece na fila de revisão
            novos += 1
        return {"novos": novos}
    finally:
        db.close()


def listar_pendentes(db: Session, org_id) -> list[dict]:
    msgs = db.scalars(
        select(EmailMessage)
        .where(EmailMessage.org_id == org_id, EmailMessage.status == EMAIL_PENDENTE)
        .order_by(EmailMessage.criado_em.desc())
    ).all()
    return [
        {
            "id": str(m.id),
            "remetente": m.remetente,
            "assunto": m.assunto,
            "corpo": m.corpo,
            "recebido_em": m.recebido_em,
            "anexos": [
                {
                    "id": str(a.id), "nome": a.nome, "tamanho": a.tamanho,
                    "content_type": a.content_type, "suportado": a.suportado,
                    "incluido": a.incluido,
                }
                for a in m.anexos
            ],
        }
        for m in msgs
    ]


def importar(db: Session, org_id, message_id, attachment_ids: list[str]) -> dict:
    """Cria Documents a partir dos anexos selecionados. Não enfileira (o endpoint defere)."""
    em = db.get(EmailMessage, message_id)
    if em is None or em.org_id != org_id:
        return {"erro": "Email não encontrado."}
    selecionados = set(attachment_ids or [])
    docs: list[dict] = []
    for att in em.anexos:
        if str(att.id) not in selecionados or not att.suportado or att.incluido:
            continue
        data = storage.get_bytes(att.storage_key)
        doc = Document(
            org_id=org_id, nome_arquivo=att.nome, content_type=att.content_type,
            tamanho=att.tamanho, sha256=hashlib.sha256(data).hexdigest(), storage_key="",
            origem="EMAIL", remetente=em.remetente, status=STATUS_RECEBIDO,
        )
        db.add(doc)
        db.flush()
        key = f"docs/{org_id}/{doc.id}/{att.nome}"
        storage.save_bytes(key, data, att.content_type or "application/octet-stream")
        doc.storage_key = key
        att.incluido = True
        att.document_id = doc.id
        docs.append({"id": str(doc.id), "nome": att.nome})
    em.status = EMAIL_PROCESSADO
    db.commit()
    return {"message_id": em.message_id, "remetente": em.remetente, "documentos": docs}


def ignorar(db: Session, org_id, message_id) -> dict:
    em = db.get(EmailMessage, message_id)
    if em is None or em.org_id != org_id:
        return {"erro": "Email não encontrado."}
    em.status = EMAIL_IGNORADO
    db.commit()
    return {"ignorado": True}


def vincular_empresa(db: Session, org_id, sender: str, company_id) -> None:
    """Aprende o mapeamento remetente->empresa (best-effort), usado após processar."""
    if not (sender and company_id):
        return
    comp = db.get(Company, company_id)
    if comp is not None and not comp.email:
        comp.email = sender
        db.commit()
