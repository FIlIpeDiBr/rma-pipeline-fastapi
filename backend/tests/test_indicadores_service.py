"""Integração indicadores: persistência -> cálculo -> upsert + AV/AH + período anterior."""

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.calculations import calcular_av_ah_balanco, preencher_periodo_anterior
from app.db import Base
from app.indicadores_service import calcular_e_salvar_indicadores, carregar_definicoes
from app.models import BalanceLine, Company, Document, DreLine, IndicatorValue, Org


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _setup(db, mes=12, ano=2025):
    org = Org(nome="T")
    db.add(org)
    db.flush()
    comp = Company(org_id=org.id, nome="ACME", nome_canonico="ACME")
    db.add(comp)
    db.flush()
    doc = Document(org_id=org.id, company_id=comp.id, nome_arquivo="x", storage_key="k",
                   tipo="BALANCO", mes=mes, ano=ano, empresa_nome="ACME")
    db.add(doc)
    db.flush()
    dre = [
        ("Receita Bruta", 1000), ("Deduções (-)", -100), ("Receita Líquida", 900),
        ("Custos (-)", -300), ("Lucro Bruto", 600), ("Despesas Operacionais (-)", -50),
        ("Resultado Operacional", 200), ("Lucro ou Prejuízo do Exercício", 150),
    ]
    for c, v in dre:
        db.add(DreLine(document_id=doc.id, org_id=org.id, company_id=comp.id, mes=mes, ano=ano,
                       conta=c, is_sintetico=True, valor_atual=v))
    bal = [
        ("ATIVO TOTAL", 5000), ("ATIVO CIRCULANTE", 2000), ("ATIVO NÃO CIRCULANTE", 3000),
        ("IMOBILIZADO", 1500), ("CONTAS/BANCOS", 400), ("PASSIVO CIRCULANTE", 1000),
        ("PASSIVO NÃO CIRCULANTE", 500), ("PATRIMÔNIO LÍQUIDO", 3000),
    ]
    for c, v in bal:
        db.add(BalanceLine(document_id=doc.id, org_id=org.id, company_id=comp.id, mes=mes, ano=ano,
                           conta=c, categoria=c, is_sintetico=True, saldo_atual=v))
    db.flush()
    db.flush()
    return org, comp, doc


def test_definicoes_fallback_para_constante(db):
    defs = carregar_definicoes(db, __import__("uuid").uuid4())
    assert len(defs) == 23


def test_calcular_e_salvar_indicadores(db):
    org, comp, doc = _setup(db)
    res = calcular_e_salvar_indicadores(db, org.id, comp.id, 12, 2025)
    db.commit()
    assert res["calculados"] == 23
    vals = {
        v.key: (float(v.valor) if v.valor is not None else None)
        for v in db.scalars(
            select(IndicatorValue).where(IndicatorValue.company_id == comp.id)
        ).all()
    }
    assert vals["receita_liquida"] == 900
    assert vals["endividamento"] == 0.33  # PC/PL
    assert vals["liquidez_corrente"] == 2.0  # AC/PC
    assert vals["lucratividade_percentual"] == 16.67  # 150/900*100


def test_upsert_nao_duplica(db):
    org, comp, doc = _setup(db)
    calcular_e_salvar_indicadores(db, org.id, comp.id, 12, 2025)
    calcular_e_salvar_indicadores(db, org.id, comp.id, 12, 2025)
    db.commit()
    n = len(db.scalars(select(IndicatorValue).where(IndicatorValue.company_id == comp.id)).all())
    assert n == 23  # upsert por (entidade, mes, ano, key)


def test_av_ah_balanco(db):
    org, comp, doc = _setup(db)
    calcular_av_ah_balanco(db, org.id, comp.id, 12, 2025)
    db.flush()
    ac = db.scalar(
        select(BalanceLine).where(
            BalanceLine.company_id == comp.id, BalanceLine.conta == "ATIVO CIRCULANTE"
        )
    )
    assert float(ac.av_atual) == 40.0  # 2000/5000*100


def test_preencher_periodo_anterior(db):
    org, comp, doc = _setup(db, mes=11, ano=2025)  # mês anterior com dados
    # mês atual (12) com saldo_anterior zerado
    db.add(BalanceLine(document_id=doc.id, org_id=org.id, company_id=comp.id, mes=12, ano=2025,
                       conta="ATIVO TOTAL", categoria="ATIVO TOTAL", is_sintetico=True,
                       saldo_atual=6000, saldo_anterior=0))
    db.flush()
    preencher_periodo_anterior(db, org.id, comp.id, 12, 2025)
    db.flush()
    atual = db.scalar(
        select(BalanceLine).where(
            BalanceLine.company_id == comp.id, BalanceLine.mes == 12,
            BalanceLine.conta == "ATIVO TOTAL",
        )
    )
    assert float(atual.saldo_anterior) == 5000  # veio do saldo_atual de novembro
