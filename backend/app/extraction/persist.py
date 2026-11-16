"""Persistência transacional das extrações (RF-15/16/17/18 e dedup RF-03).

Regras:
- metadados da IA prevalecem sobre os preliminares (RF-15);
- reprocessar substitui as linhas do mesmo documento (RF-16);
- contas normalizadas para categorias canônicas (RF-17);
- todas as categorias sintéticas presentes, mesmo zeradas (RF-18);
- dedup por chave de negócio empresa|mês|ano|tipo — vence o mais recente (RF-03).
"""

import uuid
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..ai import AiResultado
from ..domain.categories import (
    SINTETICOS_BALANCO,
    SINTETICOS_DRE,
    normalizar_categoria_balanco,
    normalizar_categoria_dre,
    ordem_balanco,
    ordem_dre,
)
from ..domain.textutil import canonical, parse_valor_brl
from ..models import (
    AiCall,
    BalanceLine,
    Company,
    Document,
    DreLine,
    JobEvent,
)


def registrar_ai_call(resultado: AiResultado, org_id, document_id) -> None:
    """Grava a auditoria da chamada de IA numa transação curta e independente."""
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        db.add(
            AiCall(
                org_id=org_id,
                document_id=document_id,
                tipo=resultado.tipo,
                modelo=resultado.modelo,
                input_tokens=resultado.input_tokens,
                output_tokens=resultado.output_tokens,
                custo_usd=resultado.custo_usd,
                duracao_ms=resultado.duracao_ms,
                sucesso=resultado.sucesso,
                erro=resultado.erro[:8000],
                prompt=resultado.prompt[:50000],
                resposta=resultado.texto[:50000],
            )
        )
        db.commit()
    finally:
        db.close()


def emitir_evento(org_id, document_id, etapa, progresso, status="info", mensagem="") -> None:
    """Append-only de progresso para o SSE (transação curta independente)."""
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        db.add(
            JobEvent(
                org_id=org_id,
                document_id=document_id,
                etapa=etapa,
                progresso=progresso,
                status=status,
                mensagem=mensagem[:2000],
            )
        )
        db.commit()
    finally:
        db.close()


def get_or_create_company(db: Session, org_id, nome: str, cnpj: str = "") -> Company:
    canon = canonical(nome)
    company = db.scalar(
        select(Company).where(Company.org_id == org_id, Company.nome_canonico == canon)
    )
    if company is None:
        company = Company(org_id=org_id, nome=nome.strip(), nome_canonico=canon, cnpj=cnpj or "")
        db.add(company)
        db.flush()
    elif cnpj and not company.cnpj:
        company.cnpj = cnpj
    return company


def dedup_por_chave(db: Session, document: Document) -> int:
    """Remove documentos antigos com a mesma chave de negócio (RF-03).

    O documento atual é o mais recente e prevalece; os demais e seus dados
    derivados (linhas via FK CASCADE) são removidos.
    """
    if not (document.company_id and document.mes and document.ano and document.tipo):
        return 0
    antigos = db.scalars(
        select(Document).where(
            Document.org_id == document.org_id,
            Document.company_id == document.company_id,
            Document.mes == document.mes,
            Document.ano == document.ano,
            Document.tipo == document.tipo,
            Document.id != document.id,
        )
    ).all()
    for d in antigos:
        db.delete(d)
    return len(antigos)


def _num(v) -> Decimal:
    return parse_valor_brl(v)


def salvar_balanco(db: Session, document: Document, dados: dict) -> dict:
    """Grava linhas e sintéticos de balancete (substitui os existentes do documento)."""
    db.execute(delete(BalanceLine).where(BalanceLine.document_id == document.id))

    base = dict(
        document_id=document.id,
        org_id=document.org_id,
        company_id=document.company_id,
        mes=document.mes,
        ano=document.ano,
    )

    for i, ln in enumerate(dados.get("linhas", []) or []):
        db.add(
            BalanceLine(
                **base,
                ordem=i,
                conta=str(ln.get("conta", ""))[:400],
                is_sintetico=False,
                saldo_anterior=_num(ln.get("saldo_anterior")),
                debito=_num(ln.get("debito")),
                credito=_num(ln.get("credito")),
                saldo_atual=_num(ln.get("saldo_atual")),
            )
        )

    # Sintéticos normalizados + garantia de todas as categorias (RF-18).
    presentes: dict[str, dict] = {}
    for s in dados.get("sinteticos", []) or []:
        cat = normalizar_categoria_balanco(str(s.get("categoria", "")))
        if cat:
            presentes[cat] = s
    for cat in SINTETICOS_BALANCO:
        s = presentes.get(cat, {})
        db.add(
            BalanceLine(
                **base,
                ordem=1000 + ordem_balanco(cat),
                conta=cat,
                categoria=cat,
                is_sintetico=True,
                saldo_anterior=_num(s.get("saldo_anterior")),
                debito=_num(s.get("debito")),
                credito=_num(s.get("credito")),
                saldo_atual=_num(s.get("saldo_atual")),
            )
        )
    return {"linhas": len(dados.get("linhas", []) or []), "sinteticos": len(SINTETICOS_BALANCO)}


def salvar_dre(db: Session, document: Document, dados: dict, derivada: bool = False) -> dict:
    """Grava linhas sintéticas de DRE (substitui as existentes do documento).

    derivada=True marca uma DRE sintética derivada do balancete (RF-19).
    """
    db.execute(delete(DreLine).where(DreLine.document_id == document.id))

    presentes: dict[str, dict] = {}
    for ln in dados.get("linhas", []) or []:
        cat = normalizar_categoria_dre(str(ln.get("categoria", ln.get("conta", ""))))
        if cat:
            presentes[cat] = ln

    for cat in SINTETICOS_DRE:
        ln = presentes.get(cat, {})
        db.add(
            DreLine(
                document_id=document.id,
                org_id=document.org_id,
                company_id=document.company_id,
                mes=document.mes,
                ano=document.ano,
                ordem=ordem_dre(cat),
                conta=cat,
                is_sintetico=True,
                derivada=derivada,
                valor_atual=_num(ln.get("valor_atual")),
                valor_anterior=_num(ln.get("valor_anterior")),
            )
        )
    return {"categorias": len(SINTETICOS_DRE), "preenchidas": len(presentes)}


def coerce_periodo(dados: dict, fallback: dict) -> tuple[int | None, int | None]:
    """mes/ano da extração prevalecem (RF-15); cai no fallback da triagem."""

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    mes = _int(dados.get("mes")) or _int(fallback.get("mes"))
    ano = _int(dados.get("ano")) or _int(fallback.get("ano"))
    return mes, ano


def as_uuid(v) -> uuid.UUID:
    return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))
