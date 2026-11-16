"""Cálculos sobre as bases: preenchimento de período anterior (RF-20) e AV%/AH% (RF-21)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain.indicadores import limitar_casas, normalizar_chave, safe_divide
from .domain.textutil import proximo_periodo_anterior
from .models import BalanceLine, DreLine


def _q2(x):
    return None if x is None else Decimal(str(limitar_casas(x, 2)))


def _av(valor, base):
    d = safe_divide(valor, base)
    return None if d is None else d * 100


def _ah(atual, anterior):
    a = float(anterior or 0)
    if a == 0:
        return None
    return (float(atual or 0) - a) / abs(a) * 100


def preencher_periodo_anterior(db: Session, org_id, company_id, mes: int, ano: int) -> None:
    """Quando saldo/valor anterior está zerado, busca o valor atual do mês anterior (RF-20)."""
    pm, pa = proximo_periodo_anterior(mes, ano)

    ant_bal = {
        normalizar_chave(ln.conta): float(ln.saldo_atual or 0)
        for ln in db.scalars(
            select(BalanceLine).where(
                BalanceLine.org_id == org_id, BalanceLine.company_id == company_id,
                BalanceLine.mes == pm, BalanceLine.ano == pa,
            )
        ).all()
    }
    if ant_bal:
        for ln in db.scalars(
            select(BalanceLine).where(
                BalanceLine.org_id == org_id, BalanceLine.company_id == company_id,
                BalanceLine.mes == mes, BalanceLine.ano == ano,
            )
        ).all():
            if (ln.saldo_anterior or 0) == 0:
                v = ant_bal.get(normalizar_chave(ln.conta))
                if v is not None:
                    ln.saldo_anterior = Decimal(str(v))

    ant_dre = {
        normalizar_chave(ln.conta): float(ln.valor_atual or 0)
        for ln in db.scalars(
            select(DreLine).where(
                DreLine.org_id == org_id, DreLine.company_id == company_id,
                DreLine.mes == pm, DreLine.ano == pa,
            )
        ).all()
    }
    if ant_dre:
        for ln in db.scalars(
            select(DreLine).where(
                DreLine.org_id == org_id, DreLine.company_id == company_id,
                DreLine.mes == mes, DreLine.ano == ano,
            )
        ).all():
            if (ln.valor_anterior or 0) == 0:
                v = ant_dre.get(normalizar_chave(ln.conta))
                if v is not None:
                    ln.valor_anterior = Decimal(str(v))


def calcular_av_ah_balanco(db: Session, org_id, company_id, mes: int, ano: int) -> None:
    """AV% sobre Ativo Total (fallback Ativo) e AH% sobre o anterior (RF-21)."""
    linhas = db.scalars(
        select(BalanceLine).where(
            BalanceLine.org_id == org_id, BalanceLine.company_id == company_id,
            BalanceLine.mes == mes, BalanceLine.ano == ano,
        )
    ).all()
    base_at = base_ant = None
    for alvo in ("ATIVO TOTAL", "ATIVO"):
        for ln in linhas:
            if normalizar_chave(ln.conta) == normalizar_chave(alvo) and ln.is_sintetico:
                base_at = float(ln.saldo_atual or 0)
                base_ant = float(ln.saldo_anterior or 0)
                break
        if base_at:
            break
    for ln in linhas:
        ln.av_atual = _q2(_av(float(ln.saldo_atual or 0), base_at))
        ln.av_anterior = _q2(_av(float(ln.saldo_anterior or 0), base_ant))
        ln.ah = _q2(_ah(ln.saldo_atual, ln.saldo_anterior))


def calcular_av_ah_dre(db: Session, org_id, company_id, mes: int, ano: int) -> None:
    """AV% sobre Receita Bruta (fallback Receita Líquida) e AH% sobre o anterior (RF-21)."""
    linhas = db.scalars(
        select(DreLine).where(
            DreLine.org_id == org_id, DreLine.company_id == company_id,
            DreLine.mes == mes, DreLine.ano == ano,
        )
    ).all()
    base_at = base_ant = None
    for alvo in ("Receita Bruta", "Receita Líquida"):
        for ln in linhas:
            if normalizar_chave(ln.conta) == normalizar_chave(alvo):
                base_at = float(ln.valor_atual or 0)
                base_ant = float(ln.valor_anterior or 0)
                break
        if base_at:
            break
    for ln in linhas:
        ln.av_atual = _q2(_av(float(ln.valor_atual or 0), base_at))
        ln.av_anterior = _q2(_av(float(ln.valor_anterior or 0), base_ant))
        ln.ah = _q2(_ah(ln.valor_atual, ln.valor_anterior))
