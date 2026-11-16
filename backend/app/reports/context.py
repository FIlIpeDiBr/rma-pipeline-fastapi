"""Monta o contexto docxtpl a partir do banco (sem IA, sem gráficos — adicionados no builder)."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.categories import SINTETICOS_BALANCO, SINTETICOS_DRE, ordem_balanco, ordem_dre
from ..domain.indicadores import limitar_casas, normalizar_chave, safe_divide
from ..domain.textutil import proximo_periodo_anterior
from ..models import BalanceLine, Company, DreLine, IndicatorValue

MESES = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def fmt(v) -> str:
    if v is None or v == "":
        return ""
    return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def periodo_str(mes, ano) -> str:
    return f"{MESES[mes]}/{ano}"


def _av(valor, base):
    d = safe_divide(valor, base)
    return None if d is None else limitar_casas(d * 100, 2)


def _ah(atual, anterior):
    a = float(anterior or 0)
    if a == 0:
        return None
    return limitar_casas((float(atual or 0) - a) / abs(a) * 100, 2)


def _linha(conta, anterior, atual, av_ant, av_atu, ah) -> dict:
    return {
        "conta": conta,
        "anterior": fmt(anterior), "av_ant": fmt(av_ant),
        "atual": fmt(atual), "av_atu": fmt(av_atu), "ah": fmt(ah),
    }


def _rows_balanco_empresa(db, org_id, company_id, mes, ano) -> list[dict]:
    linhas = db.scalars(
        select(BalanceLine).where(
            BalanceLine.org_id == org_id, BalanceLine.company_id == company_id,
            BalanceLine.mes == mes, BalanceLine.ano == ano,
            BalanceLine.is_sintetico.is_(True),
        ).order_by(BalanceLine.ordem)
    ).all()
    return [
        _linha(ln.categoria or ln.conta, ln.saldo_anterior, ln.saldo_atual,
               ln.av_anterior, ln.av_atual, ln.ah)
        for ln in linhas
    ]


def _rows_dre_empresa(db, org_id, company_id, mes, ano) -> list[dict]:
    linhas = db.scalars(
        select(DreLine).where(
            DreLine.org_id == org_id, DreLine.company_id == company_id,
            DreLine.mes == mes, DreLine.ano == ano,
        ).order_by(DreLine.ordem)
    ).all()
    return [
        _linha(ln.conta, ln.valor_anterior, ln.valor_atual, ln.av_anterior, ln.av_atual, ln.ah)
        for ln in linhas
    ]


def _consolidar_rows(db, org_id, company_ids, mes, ano):
    """Soma sintéticos de balanço/DRE entre integrantes e recalcula AV/AH no consolidado."""
    bal = defaultdict(lambda: [0.0, 0.0])  # categoria -> [anterior, atual]
    for ln in db.scalars(
        select(BalanceLine).where(
            BalanceLine.org_id == org_id, BalanceLine.company_id.in_(company_ids),
            BalanceLine.mes == mes, BalanceLine.ano == ano, BalanceLine.is_sintetico.is_(True),
        )
    ).all():
        cat = ln.categoria or ln.conta
        bal[cat][0] += float(ln.saldo_anterior or 0)
        bal[cat][1] += float(ln.saldo_atual or 0)
    dre = defaultdict(lambda: [0.0, 0.0])
    for ln in db.scalars(
        select(DreLine).where(
            DreLine.org_id == org_id, DreLine.company_id.in_(company_ids),
            DreLine.mes == mes, DreLine.ano == ano,
        )
    ).all():
        dre[ln.conta][0] += float(ln.valor_anterior or 0)
        dre[ln.conta][1] += float(ln.valor_atual or 0)

    base_bal_at = bal.get("ATIVO TOTAL", bal.get("ATIVO", [0, 0]))[1]
    base_bal_ant = bal.get("ATIVO TOTAL", bal.get("ATIVO", [0, 0]))[0]
    rows_bal = []
    for cat in sorted(bal, key=ordem_balanco):
        ant, atu = bal[cat]
        rows_bal.append(_linha(cat, ant, atu, _av(ant, base_bal_ant), _av(atu, base_bal_at),
                               _ah(atu, ant)))
    base_dre_at = dre.get("Receita Bruta", dre.get("Receita Líquida", [0, 0]))[1]
    base_dre_ant = dre.get("Receita Bruta", dre.get("Receita Líquida", [0, 0]))[0]
    rows_dre = []
    for cat in sorted(dre, key=ordem_dre):
        ant, atu = dre[cat]
        rows_dre.append(_linha(cat, ant, atu, _av(ant, base_dre_ant), _av(atu, base_dre_at),
                               _ah(atu, ant)))
    return rows_bal, rows_dre


def _indicadores(db, org_id, company_id, grupo, atual, anterior) -> dict:
    """Indicadores dos dois períodos, com chaves estáveis 'atual'/'anterior'."""
    resultado = {}
    for chave, (m, a) in (("atual", atual), ("anterior", anterior)):
        q = select(IndicatorValue).where(
            IndicatorValue.org_id == org_id, IndicatorValue.mes == m, IndicatorValue.ano == a
        )
        if grupo:
            q = q.where(IndicatorValue.grupo == grupo, IndicatorValue.company_id.is_(None))
        else:
            q = q.where(IndicatorValue.company_id == company_id, IndicatorValue.grupo == "")
        resultado[chave] = {
            v.label: (float(v.valor) if v.valor is not None else None) for v in db.scalars(q).all()
        }
    return resultado


def _comparativo_rows(db, org_id, company_ids, ano):
    """Tabelas ANUAIS: coluna atual = exercício `ano`, anterior = `ano-1` (sintéticos,
    somando integrantes), com AV/AH recalculados sobre os dois exercícios."""

    def agg_bal(a):
        d = defaultdict(float)
        for ln in db.scalars(
            select(BalanceLine).where(
                BalanceLine.org_id == org_id, BalanceLine.company_id.in_(company_ids),
                BalanceLine.mes == 12, BalanceLine.ano == a, BalanceLine.is_sintetico.is_(True),
            )
        ).all():
            d[ln.categoria or ln.conta] += float(ln.saldo_atual or 0)
        return d

    def agg_dre(a):
        d = defaultdict(float)
        for ln in db.scalars(
            select(DreLine).where(
                DreLine.org_id == org_id, DreLine.company_id.in_(company_ids),
                DreLine.mes == 12, DreLine.ano == a,
            )
        ).all():
            d[ln.conta] += float(ln.valor_atual or 0)
        return d

    bal_cur, bal_prev = agg_bal(ano), agg_bal(ano - 1)
    dre_cur, dre_prev = agg_dre(ano), agg_dre(ano - 1)
    base_bal_atu = bal_cur.get("ATIVO TOTAL", bal_cur.get("ATIVO", 0.0))
    base_bal_ant = bal_prev.get("ATIVO TOTAL", bal_prev.get("ATIVO", 0.0))
    base_dre_atu = dre_cur.get("Receita Bruta", dre_cur.get("Receita Líquida", 0.0))
    base_dre_ant = dre_prev.get("Receita Bruta", dre_prev.get("Receita Líquida", 0.0))

    rows_bal = []
    for cat in sorted(set(bal_cur) | set(bal_prev), key=ordem_balanco):
        atu, ant = bal_cur.get(cat, 0.0), bal_prev.get(cat, 0.0)
        rows_bal.append(
            _linha(cat, ant, atu, _av(ant, base_bal_ant), _av(atu, base_bal_atu), _ah(atu, ant))
        )
    rows_dre = []
    for cat in sorted(set(dre_cur) | set(dre_prev), key=ordem_dre):
        atu, ant = dre_cur.get(cat, 0.0), dre_prev.get(cat, 0.0)
        rows_dre.append(
            _linha(cat, ant, atu, _av(ant, base_dre_ant), _av(atu, base_dre_atu), _ah(atu, ant))
        )
    return rows_bal, rows_dre


def montar_contexto(
    db: Session, org_id, *, company_id=None, grupo=None, mes: int, ano: int, anual: bool = False
) -> dict:
    """Contexto base do relatório (escalares, integrantes, indicadores). Sem gráficos/IA.

    anual=True: usa o exercício (dezembro/ano) e compara com o ano anterior,
    rotulando os períodos pelo ano em vez do mês.
    """
    mes_dados = 12 if anual else mes
    if anual:
        pm, pa = 12, ano - 1
        periodo_atual, periodo_anterior = str(ano), str(ano - 1)
        mes_nome = f"Exercício de {ano}"
    else:
        pm, pa = proximo_periodo_anterior(mes, ano)
        periodo_atual, periodo_anterior = periodo_str(mes, ano), periodo_str(pm, pa)
        mes_nome = MESES[mes]
    eh_grupo = bool(grupo)

    if eh_grupo:
        empresas = db.scalars(
            select(Company).where(Company.org_id == org_id, Company.grupo == grupo)
            .order_by(Company.nome)
        ).all()
        entidade_nome = grupo
    else:
        empresas = [db.get(Company, company_id)] if company_id else []
        entidade_nome = empresas[0].nome if empresas and empresas[0] else ""

    integrantes = []
    for c in empresas:
        if c is None:
            continue
        if anual:
            rb, rd = _comparativo_rows(db, org_id, [c.id], ano)
        else:
            rb = _rows_balanco_empresa(db, org_id, c.id, mes_dados, ano)
            rd = _rows_dre_empresa(db, org_id, c.id, mes_dados, ano)
        integrantes.append({
            "nome": c.nome, "balanco": rb, "dre": rd,
            "analise_balanco": "", "analise_dre": "",
        })

    if eh_grupo and len(empresas) > 1:
        ids = [c.id for c in empresas if c]
        if anual:
            rows_bal, rows_dre = _comparativo_rows(db, org_id, ids, ano)
        else:
            rows_bal, rows_dre = _consolidar_rows(db, org_id, ids, mes_dados, ano)
        integrantes.append({
            "nome": f"{grupo} (Consolidado)",
            "balanco": rows_bal, "dre": rows_dre,
            "analise_balanco": "", "analise_dre": "",
        })

    return {
        "grupo": entidade_nome,
        "empresa": entidade_nome,
        "entidade": entidade_nome,
        "eh_grupo": eh_grupo,
        "anual": anual,
        "mes": mes,
        "ano": ano,
        "mes_nome": mes_nome,
        "periodo_atual": periodo_atual,
        "periodo_anterior": periodo_anterior,
        "integrantes": integrantes,
        "indicadores": _indicadores(db, org_id, company_id, grupo, (mes_dados, ano), (pm, pa)),
        "_chave_atual": "atual",
        "_chave_anterior": "anterior",
    }


SINTETICOS_BALANCO_N = [normalizar_chave(c) for c in SINTETICOS_BALANCO]
SINTETICOS_DRE_N = [normalizar_chave(c) for c in SINTETICOS_DRE]
