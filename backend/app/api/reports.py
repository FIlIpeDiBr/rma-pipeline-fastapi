"""API de relatórios: templates (listar/subir/padrão) e relatórios (gerar/listar/baixar)."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..auth.deps import current_org_id
from ..config import get_settings
from ..db import get_db
from ..http_utils import content_disposition
from ..models import REPORT_FILA, Company, Report, Template
from ..reports.builder import eh_docx
from ..reports.service import DOCX_MIME, get_or_create_template_padrao

router = APIRouter()
log = structlog.get_logger()


def _report_dict(r: Report, entidade: str | None = None) -> dict:
    return {
        "id": str(r.id), "template_id": str(r.template_id),
        "company_id": str(r.company_id) if r.company_id else None, "grupo": r.grupo or None,
        "entidade": entidade if entidade is not None else (r.grupo or "—"),
        "mes": r.mes, "ano": r.ano, "anual": r.anual, "status": r.status, "progresso": r.progresso,
        "etapa": r.etapa, "erro": r.erro, "nome_arquivo": r.nome_arquivo,
        "pronto": bool(r.storage_key),
        "criado_em": r.criado_em.isoformat() if r.criado_em else None,
    }


def _entidade(db: Session, r: Report) -> str:
    if r.grupo:
        return r.grupo
    if r.company_id:
        comp = db.get(Company, r.company_id)
        if comp:
            return comp.nome
    return "—"


# ── Templates ────────────────────────────────────────────────────────────────
@router.get("/templates")
def listar_templates(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    ts = db.scalars(
        select(Template).where(Template.org_id == org_id, Template.ativo.is_(True))
        .order_by(Template.nome)
    ).all()
    if not ts:  # bootstrap: cria o template padrão na primeira consulta
        get_or_create_template_padrao(db, org_id)
        ts = db.scalars(
            select(Template).where(Template.org_id == org_id, Template.ativo.is_(True))
            .order_by(Template.nome)
        ).all()
    return {
        "templates": [
            {"id": str(t.id), "nome": t.nome, "descricao": t.descricao,
             "suporta_grupo": t.suporta_grupo}
            for t in ts
        ]
    }


@router.post("/templates/seed-default")
def semear_padrao(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    t = get_or_create_template_padrao(db, org_id)
    return {"id": str(t.id), "nome": t.nome, "suporta_grupo": t.suporta_grupo}


@router.post("/templates/upload")
async def subir_template(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
    arquivo: Annotated[UploadFile, File(...)],
    nome: Annotated[str, Form()],
    suporta_grupo: Annotated[bool, Form()] = False,
) -> dict:
    data = await arquivo.read()
    if not data:
        raise HTTPException(422, "Arquivo vazio.")
    limite_mb = get_settings().max_upload_mb
    if len(data) > limite_mb * 1024 * 1024:
        raise HTTPException(413, f"Template excede {limite_mb} MB.")
    if not eh_docx(data):
        raise HTTPException(422, "O template precisa ser um arquivo .docx.")
    t = Template(org_id=org_id, nome=nome, suporta_grupo=suporta_grupo, storage_key="")
    db.add(t)
    db.flush()
    key = f"templates/{org_id}/{t.id}.docx"
    storage.save_bytes(key, data, DOCX_MIME)
    t.storage_key = key
    db.commit()
    return {"id": str(t.id), "nome": t.nome, "suporta_grupo": t.suporta_grupo}


@router.delete("/templates/{template_id}")
def excluir_template(
    template_id: uuid.UUID,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Soft delete: marca o template como inativo (some de `listar_templates`).
    Não remove a linha nem o arquivo, pois `reports.template_id` referencia o
    template por FK — relatórios já gerados continuam válidos."""
    t = db.get(Template, template_id)
    if t is None or t.org_id != org_id:
        raise HTTPException(404, "Template não encontrado.")
    t.ativo = False
    db.commit()
    log.info("template_excluido", template_id=str(template_id), nome=t.nome)
    return {"id": str(template_id), "nome": t.nome, "excluido": True}


# ── Relatórios ───────────────────────────────────────────────────────────────
@router.post("/reports")
async def gerar(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
    template_id: uuid.UUID,
    ano: int,
    mes: int | None = None,
    company_id: uuid.UUID | None = None,
    grupo: str | None = None,
    anual: bool = False,
    source_document_id: uuid.UUID | None = None,
) -> dict:
    if not company_id and not grupo:
        raise HTTPException(422, "Informe company_id (individual) ou grupo.")
    if not anual and not mes:
        raise HTTPException(422, "Informe o mês (ou marque o relatório como anual).")
    template = db.get(Template, template_id)
    if template is None or template.org_id != org_id:
        raise HTTPException(404, "Template não encontrado.")
    if grupo and not template.suporta_grupo:
        raise HTTPException(422, "Este template não suporta grupo.")
    if company_id:
        comp = db.get(Company, company_id)
        if comp is None or comp.org_id != org_id:
            raise HTTPException(404, "Empresa não encontrada.")

    report = Report(
        org_id=org_id, template_id=template_id, company_id=company_id, grupo=(grupo or ""),
        mes=(12 if anual else mes), ano=ano, anual=anual, status=REPORT_FILA,  # anual usa dez/ano
        source_document_id=source_document_id,
    )
    db.add(report)
    db.commit()

    from ..jobs.tasks import gerar_relatorio

    try:
        await gerar_relatorio.defer_async(report_id=str(report.id))
    except Exception as exc:  # noqa: BLE001
        log.warning("defer_relatorio_falhou", report_id=str(report.id), erro=str(exc))
        report.erro = f"Fila indisponível ({exc.__class__.__name__})."
        db.commit()
    return _report_dict(report, _entidade(db, report))


@router.get("/reports")
def listar(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
) -> dict:
    q = select(Report).where(Report.org_id == org_id)
    if status:
        q = q.where(Report.status == status)
    q = q.order_by(Report.criado_em.desc()).limit(200)
    regs = db.scalars(q).all()
    nomes = {
        c.id: c.nome
        for c in db.scalars(
            select(Company).where(Company.id.in_({r.company_id for r in regs if r.company_id}))
        ).all()
    } if regs else {}

    def ent(r: Report) -> str:
        return r.grupo or nomes.get(r.company_id, "—")

    return {"relatorios": [_report_dict(r, ent(r)) for r in regs]}


@router.get("/reports/{report_id}")
def detalhe(
    report_id: uuid.UUID,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    r = db.get(Report, report_id)
    if r is None or r.org_id != org_id:
        raise HTTPException(404, "Relatório não encontrado.")
    return _report_dict(r, _entidade(db, r))


@router.get("/reports/{report_id}/download")
def baixar(
    report_id: uuid.UUID,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    r = db.get(Report, report_id)
    if r is None or r.org_id != org_id:
        raise HTTPException(404, "Relatório não encontrado.")
    if not r.storage_key:
        raise HTTPException(409, f"Relatório ainda não está pronto (status {r.status}).")
    data = storage.get_bytes(r.storage_key)
    return Response(
        content=data, media_type=DOCX_MIME,
        headers={"Content-Disposition": content_disposition(r.nome_arquivo)},
    )
