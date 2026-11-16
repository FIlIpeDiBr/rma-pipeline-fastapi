"""DRE sintética derivada do balancete (RF-19).

Quando um período só tem balancete (sem DRE real), deriva uma DRE classificando
as contas de resultado do balancete via IA. Não gera se já existe DRE real;
a DRE real, ao chegar, substitui a sintética (removida no pipeline).
"""

import structlog
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import ai
from ..models import BalanceLine, Document, DreLine
from .persist import registrar_ai_call, salvar_dre

log = structlog.get_logger()


def existe_dre_real(db: Session, org_id, company_id, mes, ano) -> bool:
    return db.scalar(
        select(DreLine.id).where(
            DreLine.org_id == org_id,
            DreLine.company_id == company_id,
            DreLine.mes == mes,
            DreLine.ano == ano,
            DreLine.derivada.is_(False),
        ).limit(1)
    ) is not None


def remover_dre_sintetica(db: Session, org_id, company_id, mes, ano) -> int:
    r = db.execute(
        delete(DreLine).where(
            DreLine.org_id == org_id,
            DreLine.company_id == company_id,
            DreLine.mes == mes,
            DreLine.ano == ano,
            DreLine.derivada.is_(True),
        )
    )
    return r.rowcount or 0


def _texto_contas(db: Session, document: Document) -> str:
    linhas = db.scalars(
        select(BalanceLine).where(
            BalanceLine.document_id == document.id,
            BalanceLine.is_sintetico.is_(False),
        ).order_by(BalanceLine.ordem)
    ).all()
    return "\n".join(f"{ln.conta} | {ln.saldo_atual}" for ln in linhas if ln.conta)


def derivar_e_salvar(db: Session, document: Document) -> dict:
    """Deriva a DRE do balancete `document` e grava como derivada=True. Best-effort."""
    if not (document.company_id and document.mes and document.ano):
        return {"derivada": False, "motivo": "sem chave de período"}
    if existe_dre_real(db, document.org_id, document.company_id, document.mes, document.ano):
        return {"derivada": False, "motivo": "já existe DRE real"}

    texto = _texto_contas(db, document)
    if not texto.strip():
        return {"derivada": False, "motivo": "balancete sem contas analíticas"}

    r = ai.derivar_dre_de_balanco(texto)
    registrar_ai_call(r, document.org_id, document.id)
    if not r.sucesso or not isinstance(r.parsed, dict):
        log.warning("dre_sintetica_falhou", document_id=str(document.id), erro=r.erro[:200])
        return {"derivada": False, "motivo": f"IA: {r.erro[:120]}"}

    salvar_dre(db, document, r.parsed, derivada=True)
    return {"derivada": True, "custo_usd": str(r.custo_usd)}
