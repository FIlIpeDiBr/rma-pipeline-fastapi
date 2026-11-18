"""API de documentos: upload, listagem, detalhe, reprocesso e download (RF-48/50)."""

import hashlib
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..auth.deps import current_org_id, current_user
from ..config import get_settings
from ..db import get_db
from ..http_utils import ArquivoGrandeDemais, content_disposition, ler_com_limite
from ..models import (
    STATUS_RECEBIDO,
    BalanceLine,
    Document,
    DreLine,
    JobEvent,
)

router = APIRouter()
log = structlog.get_logger()


async def _enfileirar(document_id: uuid.UUID) -> str | None:
    """Defere o job de processamento. Retorna mensagem de erro se a fila estiver indisponível."""
    from ..jobs.tasks import processar_documento

    try:
        await processar_documento.defer_async(document_id=str(document_id))
        return None
    except Exception as exc:  # noqa: BLE001 - upload não falha por causa da fila
        log.warning("defer_falhou", document_id=str(document_id), erro=str(exc))
        return f"Fila indisponível ({exc.__class__.__name__}); reprocessar depois."


def _doc_resumo(d: Document) -> dict:
    metodo = "E-mail" if d.origem == "EMAIL" else "Upload manual"
    enviado_por = d.remetente if d.origem == "EMAIL" else d.enviado_por
    return {
        "id": str(d.id),
        "nome_arquivo": d.nome_arquivo,
        "empresa": d.empresa_nome,
        "tipo": d.tipo,
        "mes": d.mes,
        "ano": d.ano,
        "status": d.status,
        "mensagem": d.mensagem,
        "aviso": d.aviso,
        "tamanho": d.tamanho,
        "content_type": d.content_type,
        "origem": d.origem,
        "metodo_envio": metodo,
        "enviado_por": enviado_por or "—",
        "remetente": d.remetente,
        "criado_em": d.criado_em.isoformat() if d.criado_em else None,
        "atualizado_em": d.atualizado_em.isoformat() if d.atualizado_em else None,
    }


@router.post("/documents/upload")
async def upload(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    user: Annotated[dict, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    arquivos: Annotated[list[UploadFile], File(...)],
) -> dict:
    enviado_por = (user.get("nome") or user.get("email") or "").strip()
    limite = get_settings().max_upload_mb * 1024 * 1024
    criados = []
    for up in arquivos:
        try:
            data = await ler_com_limite(up, limite)
        except ArquivoGrandeDemais:
            criados.append(
                {"nome_arquivo": up.filename, "erro": f"excede {get_settings().max_upload_mb} MB"}
            )
            continue
        if not data:
            criados.append({"nome_arquivo": up.filename, "erro": "arquivo vazio"})
            continue

        doc = Document(
            org_id=org_id,
            nome_arquivo=up.filename or "documento",
            content_type=up.content_type or "",
            tamanho=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            storage_key="",
            status=STATUS_RECEBIDO,
            origem="UPLOAD",
            enviado_por=enviado_por,
        )
        db.add(doc)
        db.flush()  # garante doc.id

        key = f"docs/{org_id}/{doc.id}/{doc.nome_arquivo}"
        try:
            storage.save_bytes(key, data, doc.content_type or "application/octet-stream")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Falha ao gravar no storage: {exc}") from exc
        doc.storage_key = key
        db.commit()

        aviso = await _enfileirar(doc.id)
        if aviso:
            doc.mensagem = aviso
            db.commit()
        item = _doc_resumo(doc)
        if aviso:
            item["aviso"] = aviso
        criados.append(item)

    return {"criados": criados, "total": len(criados)}


@router.get("/documents")
def listar(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    company_id: uuid.UUID | None = None,
    mes: int | None = None,
    ano: int | None = None,
    limite: int = Query(200, le=1000),
) -> dict:
    q = select(Document).where(Document.org_id == org_id)
    if status:
        q = q.where(Document.status == status)
    if company_id:
        q = q.where(Document.company_id == company_id)
    if mes:
        q = q.where(Document.mes == mes)
    if ano:
        q = q.where(Document.ano == ano)
    q = q.order_by(Document.criado_em.desc()).limit(limite)
    docs = db.scalars(q).all()
    return {"documentos": [_doc_resumo(d) for d in docs], "total": len(docs)}


@router.get("/documents/{document_id}")
def detalhe(
    document_id: uuid.UUID,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    doc = db.get(Document, document_id)
    if doc is None or doc.org_id != org_id:
        raise HTTPException(404, "Documento não encontrado.")

    resumo = _doc_resumo(doc)
    if doc.tipo == "BALANCO":
        sint = db.scalars(
            select(BalanceLine)
            .where(BalanceLine.document_id == doc.id, BalanceLine.is_sintetico.is_(True))
            .order_by(BalanceLine.ordem)
        ).all()
        resumo["sinteticos"] = [
            {
                "categoria": s.categoria,
                "saldo_anterior": float(s.saldo_anterior),
                "saldo_atual": float(s.saldo_atual),
            }
            for s in sint
        ]
        resumo["qtd_linhas"] = db.query(BalanceLine).filter(
            BalanceLine.document_id == doc.id, BalanceLine.is_sintetico.is_(False)
        ).count()
    elif doc.tipo == "DRE":
        linhas = db.scalars(
            select(DreLine).where(DreLine.document_id == doc.id).order_by(DreLine.ordem)
        ).all()
        resumo["sinteticos"] = [
            {
                "categoria": ln.conta,
                "valor_atual": float(ln.valor_atual),
                "valor_anterior": float(ln.valor_anterior),
            }
            for ln in linhas
        ]

    eventos = db.scalars(
        select(JobEvent)
        .where(JobEvent.document_id == doc.id)
        .order_by(JobEvent.criado_em.desc())
        .limit(10)
    ).all()
    resumo["eventos"] = [
        {"etapa": e.etapa, "progresso": e.progresso, "status": e.status, "mensagem": e.mensagem}
        for e in reversed(eventos)
    ]
    return resumo


@router.post("/documents/{document_id}/reprocess")
async def reprocessar(
    document_id: uuid.UUID,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    doc = db.get(Document, document_id)
    if doc is None or doc.org_id != org_id:
        raise HTTPException(404, "Documento não encontrado.")
    doc.status = STATUS_RECEBIDO
    doc.mensagem = ""
    db.commit()
    aviso = await _enfileirar(doc.id)
    if aviso:
        doc.mensagem = aviso
        db.commit()
    return {"id": str(doc.id), "status": doc.status, "aviso": aviso}


@router.get("/documents/{document_id}/download")
def download(
    document_id: uuid.UUID,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    doc = db.get(Document, document_id)
    if doc is None or doc.org_id != org_id:
        raise HTTPException(404, "Documento não encontrado.")
    try:
        data = storage.get_bytes(doc.storage_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Falha ao ler do storage: {exc}") from exc
    return Response(
        content=data,
        media_type=doc.content_type or "application/octet-stream",
        headers={"Content-Disposition": content_disposition(doc.nome_arquivo)},
    )


def _recalcular_periodo(db, org_id, company_id, mes, ano) -> None:
    """Após excluir um documento, remove e recalcula os indicadores derivados do
    período afetado (empresa e, se houver, grupo). Best-effort."""
    if not (company_id and mes and ano):
        return
    from sqlalchemy import delete as sa_delete

    from ..indicadores_service import (
        calcular_e_salvar_indicadores,
        calcular_e_salvar_indicadores_grupo,
    )
    from ..models import Company, IndicatorValue

    try:
        comp = db.get(Company, company_id)
        grupo = comp.grupo if comp else ""
        # zera os valores existentes do período (empresa)
        db.execute(
            sa_delete(IndicatorValue).where(
                IndicatorValue.org_id == org_id,
                IndicatorValue.company_id == company_id,
                IndicatorValue.grupo == "",
                IndicatorValue.mes == mes,
                IndicatorValue.ano == ano,
            )
        )
        # recalcula a partir do que sobrou (se não sobrou nada, fica vazio)
        calcular_e_salvar_indicadores(db, org_id, company_id, mes, ano)
        if grupo:
            db.execute(
                sa_delete(IndicatorValue).where(
                    IndicatorValue.org_id == org_id,
                    IndicatorValue.company_id.is_(None),
                    IndicatorValue.grupo == grupo,
                    IndicatorValue.mes == mes,
                    IndicatorValue.ano == ano,
                )
            )
            calcular_e_salvar_indicadores_grupo(db, org_id, grupo, mes, ano)
        db.commit()
    except Exception:  # noqa: BLE001 - recálculo é best-effort; documento já foi excluído
        db.rollback()
        log.warning("recalculo_pos_exclusao_falhou", company_id=str(company_id), exc_info=True)


@router.delete("/documents/{document_id}")
def excluir(
    document_id: uuid.UUID,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    doc = db.get(Document, document_id)
    if doc is None or doc.org_id != org_id:
        raise HTTPException(404, "Documento não encontrado.")
    company_id, mes, ano = doc.company_id, doc.mes, doc.ano
    try:
        storage.delete(doc.storage_key)
    except Exception:  # noqa: BLE001 - storage órfão não impede a exclusão do registro
        pass
    db.delete(doc)  # linhas/eventos caem por FK CASCADE
    db.commit()
    _recalcular_periodo(db, org_id, company_id, mes, ano)
    return {"id": str(document_id), "excluido": True}
