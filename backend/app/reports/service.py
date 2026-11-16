"""Serviço de relatórios: template padrão, enfileiramento e geração com progresso (RF-38/39)."""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..models import (
    REPORT_CONCLUIDO,
    REPORT_ERRO,
    REPORT_GERANDO,
    Company,
    Report,
    Template,
)
from . import builder
from .default_template import gerar_template_bytes

log = structlog.get_logger()
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def get_or_create_template_padrao(db: Session, org_id) -> Template:
    """Garante um template padrão (gerado em código) cadastrado e armazenado."""
    t = db.scalar(
        select(Template).where(Template.org_id == org_id, Template.nome == "RMA Padrão")
    )
    if t is not None:
        return t
    t = Template(
        org_id=org_id, nome="RMA Padrão", descricao="Modelo padrão (individual e grupo).",
        suporta_grupo=True, storage_key="",
    )
    db.add(t)
    db.flush()
    key = f"templates/{org_id}/{t.id}.docx"
    storage.save_bytes(key, gerar_template_bytes(), DOCX_MIME)
    t.storage_key = key
    db.commit()
    return t


def gerar_relatorio(report_id: str) -> dict:
    """Gera o docx do relatório (job do worker). Atualiza progresso e status no Report."""
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        report = db.get(Report, uuid.UUID(str(report_id)))
        if report is None:
            return {"status": "NAO_ENCONTRADO"}
        report.status = REPORT_GERANDO
        report.progresso = 5
        report.etapa = "Iniciando"
        report.erro = ""
        db.commit()

        template = db.get(Template, report.template_id)
        template_bytes = storage.get_bytes(template.storage_key)

        def on_progress(etapa, pct):
            report.etapa = etapa
            report.progresso = pct
            db.commit()

        docx = builder.gerar(
            db, report.org_id, template_bytes=template_bytes, mes=report.mes, ano=report.ano,
            company_id=report.company_id, grupo=(report.grupo or None),
            anual=report.anual, com_ia=True, on_progress=on_progress,
        )

        if report.grupo:
            entidade = report.grupo
        else:
            comp = db.get(Company, report.company_id) if report.company_id else None
            entidade = comp.nome if comp else "Relatorio"
        nome = builder.nome_arquivo(entidade, report.mes, report.ano, anual=report.anual)
        key = f"reports/{report.org_id}/{report.id}.docx"
        storage.save_bytes(key, docx, DOCX_MIME)

        report.storage_key = key
        report.nome_arquivo = nome
        report.status = REPORT_CONCLUIDO
        report.progresso = 100
        report.etapa = "Concluído"
        db.commit()
        log.info("relatorio_gerado", report_id=str(report.id), nome=nome)
        return {"status": REPORT_CONCLUIDO, "nome_arquivo": nome}
    except Exception as exc:  # noqa: BLE001 - marca ERRO e propaga p/ retry
        db.rollback()
        rep = db.get(Report, uuid.UUID(str(report_id)))
        if rep is not None:
            rep.status = REPORT_ERRO
            rep.erro = f"{exc.__class__.__name__}: {exc}"[:2000]
            db.commit()
        log.warning("relatorio_falhou", report_id=str(report_id), exc_info=True)
        raise
    finally:
        db.close()
