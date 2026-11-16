"""Serviço de indicadores: definições, cálculo e persistência (RF-26/30/31) + grupos (RF-24/25).

Cálculo 100% determinístico (sem IA). Funciona para empresa (company_id) e para
grupo (consolidação por soma das contas das integrantes).
"""

import datetime as dt
import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain.indicadores import INDICADORES, Definicao, calcular_indicadores, normalizar_chave
from .models import (
    STATUS_PROCESSADO,
    BalanceLine,
    Company,
    Document,
    DreLine,
    IndicatorDefinition,
    IndicatorValue,
)

_RECEITA_LIQ = {normalizar_chave("Receita Liquida"), normalizar_chave("Receita Líquida")}
_LUCRO = {
    normalizar_chave("Lucro ou Prejuizo do Exercicio"),
    normalizar_chave("Lucro ou Prejuízo do Exercício"),
    normalizar_chave("Lucro Liquido"),
    normalizar_chave("Lucro Líquido"),
}


def carregar_definicoes(db: Session, org_id: uuid.UUID) -> list[Definicao]:
    """As 23 definições padrão SEMPRE presentes; linhas do banco sobrepõem por chave.

    Prioridade: padrão do sistema (constante) < linhas org_id NULL < linhas da org.
    Indicadores extras (chaves novas) entram após as 23. Assim, adicionar/editar um
    indicador nunca remove os demais (nem do cálculo).
    """
    base: dict[str, Definicao] = {d.key: d for d in INDICADORES}
    ordem: dict[str, int] = {d.key: i for i, d in enumerate(INDICADORES)}
    prox = len(INDICADORES)

    linhas = db.scalars(
        select(IndicatorDefinition).where(
            IndicatorDefinition.ativo.is_(True),
            IndicatorDefinition.org_id.in_([org_id, None]),
        )
    ).all()
    for ln in sorted(linhas, key=lambda x: (x.org_id is not None, x.ordem)):
        base[ln.key] = Definicao(ln.key, ln.label, ln.formula, ln.formato)
        if ln.key not in ordem:
            ordem[ln.key] = prox
            prox += 1
    return [base[k] for k in sorted(base, key=lambda k: ordem[k])]


def _dre_rows(db, org_id, company_ids, mes, ano) -> list[dict]:
    """DRE consolidada por conta (soma das integrantes; passthrough p/ 1 empresa)."""
    acc: dict[str, dict] = defaultdict(lambda: {"valor_atual": 0.0, "valor_anterior": 0.0})
    for ln in db.scalars(
        select(DreLine).where(
            DreLine.org_id == org_id, DreLine.company_id.in_(company_ids),
            DreLine.mes == mes, DreLine.ano == ano,
        )
    ).all():
        a = acc[ln.conta]
        a["valor_atual"] += float(ln.valor_atual or 0)
        a["valor_anterior"] += float(ln.valor_anterior or 0)
    return [{"conta": c, **v} for c, v in acc.items()]


def _bal_rows(db, org_id, company_ids, mes, ano) -> list[dict]:
    """Balancete consolidado por conta (analíticas + sintéticas), somando integrantes."""
    acc: dict[str, dict] = defaultdict(lambda: {"saldo_anterior": 0.0, "saldo_atual": 0.0})
    for ln in db.scalars(
        select(BalanceLine).where(
            BalanceLine.org_id == org_id, BalanceLine.company_id.in_(company_ids),
            BalanceLine.mes == mes, BalanceLine.ano == ano,
        )
    ).all():
        a = acc[ln.conta]
        a["saldo_anterior"] += float(ln.saldo_anterior or 0)
        a["saldo_atual"] += float(ln.saldo_atual or 0)
    return [{"conta": c, **v} for c, v in acc.items()]


def _somas_acumuladas(db, org_id, company_ids, mes, ano) -> tuple[float, float]:
    linhas = db.scalars(
        select(DreLine).where(
            DreLine.org_id == org_id, DreLine.company_id.in_(company_ids),
            DreLine.ano == ano, DreLine.mes <= mes,
        )
    ).all()
    sl = sr = 0.0
    for ln in linhas:
        cn = normalizar_chave(ln.conta)
        if cn in _RECEITA_LIQ:
            sr += float(ln.valor_atual or 0)
        if cn in _LUCRO:
            sl += float(ln.valor_atual or 0)
    return sl, sr


def _upsert_valores(db, org_id, company_id, grupo, mes, ano, valores, defs) -> int:
    formato = {d.key: d.formato for d in defs}
    label = {d.key: d.label for d in defs}
    existentes = {
        v.key: v
        for v in db.scalars(
            select(IndicatorValue).where(
                IndicatorValue.org_id == org_id,
                IndicatorValue.company_id == company_id,  # IS NULL quando grupo
                IndicatorValue.grupo == grupo,
                IndicatorValue.mes == mes,
                IndicatorValue.ano == ano,
            )
        ).all()
    }
    for key, val in valores.items():
        dec = None if val is None else Decimal(str(val))
        iv = existentes.get(key)
        if iv is None:
            db.add(
                IndicatorValue(
                    org_id=org_id, company_id=company_id, grupo=grupo, mes=mes, ano=ano,
                    key=key, label=label.get(key, ""), formato=formato.get(key, ""), valor=dec,
                )
            )
        else:
            iv.valor = dec
            iv.label = label.get(key, iv.label)
            iv.formato = formato.get(key, iv.formato)
            iv.atualizado_em = dt.datetime.now(dt.UTC)
    db.flush()
    return len(valores)


def calcular_e_salvar_indicadores(db: Session, org_id, company_id, mes: int, ano: int) -> dict:
    """Indicadores de uma empresa/período (upsert)."""
    dre_rows = _dre_rows(db, org_id, [company_id], mes, ano)
    bal_rows = _bal_rows(db, org_id, [company_id], mes, ano)
    if not dre_rows and not bal_rows:
        return {"calculados": 0}
    defs = carregar_definicoes(db, org_id)
    sl, sr = _somas_acumuladas(db, org_id, [company_id], mes, ano)
    valores = calcular_indicadores(dre_rows, bal_rows, soma_lucro=sl, soma_receita=sr, defs=defs)
    n = _upsert_valores(db, org_id, company_id, "", mes, ano, valores, defs)
    return {"calculados": n, "company_id": str(company_id), "mes": mes, "ano": ano}


def companies_do_grupo(db, org_id, grupo: str) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(Company.id).where(Company.org_id == org_id, Company.grupo == grupo)
        ).all()
    )


def calcular_e_salvar_indicadores_grupo(
    db: Session, org_id, grupo: str, mes: int, ano: int
) -> dict:
    """Consolida as integrantes do grupo e calcula os indicadores do consolidado (RF-25)."""
    ids = companies_do_grupo(db, org_id, grupo)
    if not ids:
        return {"calculados": 0, "motivo": "grupo sem empresas"}
    dre_rows = _dre_rows(db, org_id, ids, mes, ano)
    bal_rows = _bal_rows(db, org_id, ids, mes, ano)
    if not dre_rows and not bal_rows:
        return {"calculados": 0, "motivo": "sem dados no período"}
    defs = carregar_definicoes(db, org_id)
    sl, sr = _somas_acumuladas(db, org_id, ids, mes, ano)
    valores = calcular_indicadores(dre_rows, bal_rows, soma_lucro=sl, soma_receita=sr, defs=defs)
    n = _upsert_valores(db, org_id, None, grupo, mes, ano, valores, defs)
    return {"calculados": n, "grupo": grupo, "mes": mes, "ano": ano, "integrantes": len(ids)}


def gerar_pendentes(db: Session, org_id, limite: int = 100) -> dict:
    """Empresas/períodos com documentos PROCESSADO ainda sem indicadores."""
    periodos = db.execute(
        select(Document.company_id, Document.mes, Document.ano).where(
            Document.org_id == org_id, Document.status == STATUS_PROCESSADO,
            Document.company_id.is_not(None), Document.mes.is_not(None), Document.ano.is_not(None),
        ).distinct()
    ).all()
    feitos = 0
    for company_id, mes, ano in periodos:
        if feitos >= limite:
            break
        ja = db.scalar(
            select(IndicatorValue.id).where(
                IndicatorValue.org_id == org_id, IndicatorValue.company_id == company_id,
                IndicatorValue.grupo == "", IndicatorValue.mes == mes, IndicatorValue.ano == ano,
            ).limit(1)
        )
        if ja is not None:
            continue
        calcular_e_salvar_indicadores(db, org_id, company_id, mes, ano)
        feitos += 1
    db.commit()
    return {"periodos_calculados": feitos}


def gerar_grupos_pendentes(db: Session, org_id, limite: int = 100) -> dict:
    """Grupos/períodos com documentos PROCESSADO ainda sem indicadores de grupo."""
    combos = db.execute(
        select(Company.grupo, Document.mes, Document.ano)
        .join(Company, Company.id == Document.company_id)
        .where(
            Document.org_id == org_id, Document.status == STATUS_PROCESSADO,
            Company.grupo != "", Document.mes.is_not(None), Document.ano.is_not(None),
        ).distinct()
    ).all()
    feitos = 0
    for grupo, mes, ano in combos:
        if feitos >= limite:
            break
        ja = db.scalar(
            select(IndicatorValue.id).where(
                IndicatorValue.org_id == org_id, IndicatorValue.company_id.is_(None),
                IndicatorValue.grupo == grupo, IndicatorValue.mes == mes, IndicatorValue.ano == ano,
            ).limit(1)
        )
        if ja is not None:
            continue
        calcular_e_salvar_indicadores_grupo(db, org_id, grupo, mes, ano)
        feitos += 1
    db.commit()
    return {"grupos_calculados": feitos}
