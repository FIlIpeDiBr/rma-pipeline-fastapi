"""API de empresas: listar e definir grupo (RF-24)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import current_org_id
from ..db import get_db
from ..models import Company, Document

router = APIRouter()


class GrupoIn(BaseModel):
    grupo: str = ""


@router.get("/companies")
def listar(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    comps = db.scalars(
        select(Company).where(Company.org_id == org_id).order_by(Company.nome)
    ).all()
    return {
        "empresas": [
            {"id": str(c.id), "nome": c.nome, "cnpj": c.cnpj, "grupo": c.grupo} for c in comps
        ]
    }


@router.get("/companies/periodos")
def periodos_disponiveis(
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Períodos (mes/ano) com documento associado, por empresa e por grupo.

    Usado para limitar a seleção de período em Indicadores e Relatórios apenas
    aos períodos que de fato possuem dados.
    """
    linhas = db.execute(
        select(Document.company_id, Document.mes, Document.ano)
        .where(
            Document.org_id == org_id,
            Document.company_id.is_not(None),
            Document.mes.is_not(None),
            Document.ano.is_not(None),
        )
        .distinct()
    ).all()
    por_empresa: dict[str, set] = {}
    for cid, mes, ano in linhas:
        por_empresa.setdefault(str(cid), set()).add((mes, ano))

    grupo_por_company = {
        str(c.id): c.grupo
        for c in db.scalars(select(Company).where(Company.org_id == org_id)).all()
    }
    por_grupo: dict[str, set] = {}
    for cid, periodos in por_empresa.items():
        g = grupo_por_company.get(cid, "")
        if g:
            por_grupo.setdefault(g, set()).update(periodos)

    def _fmt(s: set) -> list[dict]:
        return [
            {"mes": m, "ano": a}
            for (a, m) in sorted((a, m) for (m, a) in s)
        ]

    return {
        "empresas": {cid: _fmt(s) for cid, s in por_empresa.items()},
        "grupos": {g: _fmt(s) for g, s in por_grupo.items()},
    }


@router.patch("/companies/{company_id}")
def definir_grupo(
    company_id: uuid.UUID,
    body: GrupoIn,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    comp = db.get(Company, company_id)
    if comp is None or comp.org_id != org_id:
        raise HTTPException(404, "Empresa não encontrada.")
    comp.grupo = (body.grupo or "").strip()
    db.commit()
    return {"id": str(comp.id), "nome": comp.nome, "grupo": comp.grupo}
