"""API de indicadores: listar, gerar (empresa/grupo, unitário/lote) e CRUD de definições."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import current_org_id
from ..db import get_db
from ..indicadores_service import (
    calcular_e_salvar_indicadores,
    calcular_e_salvar_indicadores_grupo,
    carregar_definicoes,
    gerar_grupos_pendentes,
    gerar_pendentes,
)
from ..models import Document, IndicatorDefinition, IndicatorValue

router = APIRouter()


def _formatar(valor, formato: str) -> str:
    """Formatação pt-BR (RF-33): 2 casas R$/%, 3 casas índices."""
    if valor is None:
        return "—"
    casas = 3 if formato == "indice" else 2
    s = f"{float(valor):,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")
    if formato == "rs":
        return f"R$ {s}"
    if formato == "pct":
        return f"{s}%"
    return s


# ── Definições (RF-27b) ──────────────────────────────────────────────────────
class DefinicaoIn(BaseModel):
    key: str
    label: str
    formula: str = ""
    formato: str = "rs"
    ordem: int = 0
    ativo: bool = True


@router.get("/indicators/definitions")
def listar_definicoes(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    defs = carregar_definicoes(db, org_id)
    return {
        "definicoes": [
            {"key": d.key, "label": d.label, "formula": d.formula, "formato": d.formato}
            for d in defs
        ]
    }


@router.post("/indicators/definitions")
def salvar_definicao(
    body: DefinicaoIn,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if body.formato not in ("rs", "pct", "indice"):
        raise HTTPException(422, "formato deve ser rs, pct ou indice.")
    chave = body.key.strip()
    if not chave:
        raise HTTPException(422, "key obrigatória.")
    existente = db.scalar(
        select(IndicatorDefinition).where(
            IndicatorDefinition.org_id == org_id, IndicatorDefinition.key == chave
        )
    )
    if existente is None:
        db.add(
            IndicatorDefinition(
                org_id=org_id, key=chave, label=body.label, formula=body.formula,
                formato=body.formato, ordem=body.ordem, ativo=body.ativo,
            )
        )
    else:
        existente.label = body.label
        existente.formula = body.formula
        existente.formato = body.formato
        existente.ordem = body.ordem
        existente.ativo = body.ativo
    db.commit()
    return {"key": chave, "salvo": True}


@router.delete("/indicators/definitions/{key}")
def excluir_definicao(
    key: str,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    d = db.scalar(
        select(IndicatorDefinition).where(
            IndicatorDefinition.org_id == org_id, IndicatorDefinition.key == key
        )
    )
    if d is None:
        raise HTTPException(
            404,
            "Definição da org não encontrada (padrões do sistema não são removíveis).",
        )
    db.delete(d)
    db.commit()
    return {"key": key, "excluido": True}


# ── Valores ──────────────────────────────────────────────────────────────────
@router.get("/indicators")
def listar(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
    mes: int,
    ano: int,
    company_id: uuid.UUID | None = None,
    grupo: str | None = None,
) -> dict:
    q = select(IndicatorValue).where(
        IndicatorValue.org_id == org_id, IndicatorValue.mes == mes, IndicatorValue.ano == ano
    )
    if grupo:
        q = q.where(IndicatorValue.grupo == grupo, IndicatorValue.company_id.is_(None))
    elif company_id:
        q = q.where(IndicatorValue.company_id == company_id, IndicatorValue.grupo == "")
    else:
        raise HTTPException(422, "Informe company_id ou grupo.")
    vals = db.scalars(q).all()
    return {
        "entidade": {"company_id": str(company_id) if company_id else None, "grupo": grupo or None},
        "mes": mes,
        "ano": ano,
        "indicadores": [
            {
                "key": v.key, "label": v.label, "formato": v.formato,
                "valor": float(v.valor) if v.valor is not None else None,
                "valor_formatado": _formatar(v.valor, v.formato),
            }
            for v in vals
        ],
    }


@router.post("/indicators/generate")
def gerar(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
    company_id: uuid.UUID,
    mes: int,
    ano: int,
) -> dict:
    doc = db.scalar(
        select(Document.id).where(
            Document.org_id == org_id, Document.company_id == company_id
        ).limit(1)
    )
    if doc is None:
        raise HTTPException(404, "Empresa sem documentos nesta organização.")
    res = calcular_e_salvar_indicadores(db, org_id, company_id, mes, ano)
    db.commit()
    return res


@router.post("/indicators/generate-group")
def gerar_grupo(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
    grupo: str,
    mes: int,
    ano: int,
) -> dict:
    res = calcular_e_salvar_indicadores_grupo(db, org_id, grupo, mes, ano)
    db.commit()
    return res


@router.post("/indicators/generate-pending")
def gerar_lote(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
    limite: int = 100,
) -> dict:
    return gerar_pendentes(db, org_id, limite)


@router.post("/indicators/generate-groups-pending")
def gerar_grupos_lote(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
    limite: int = 100,
) -> dict:
    return gerar_grupos_pendentes(db, org_id, limite)
