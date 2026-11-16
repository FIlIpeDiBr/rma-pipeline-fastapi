"""Grupos: consolidação por soma das integrantes (RF-25) e override de definições (RF-27b)."""

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db import Base
from app.indicadores_service import (
    calcular_e_salvar_indicadores_grupo,
    carregar_definicoes,
    companies_do_grupo,
)
from app.models import Company, Document, DreLine, IndicatorDefinition, IndicatorValue, Org


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _empresa_com_dre(db, org, nome, grupo, dre, mes=12, ano=2025):
    c = Company(org_id=org.id, nome=nome, nome_canonico=nome.upper(), grupo=grupo)
    db.add(c)
    db.flush()
    d = Document(org_id=org.id, company_id=c.id, nome_arquivo="x", storage_key="k",
                 tipo="DRE", mes=mes, ano=ano, empresa_nome=nome)
    db.add(d)
    db.flush()
    for conta, v in dre:
        db.add(DreLine(document_id=d.id, org_id=org.id, company_id=c.id, mes=mes, ano=ano,
                       conta=conta, is_sintetico=True, valor_atual=v))
    db.flush()
    return c


def test_consolidacao_soma_integrantes(db):
    org = Org(nome="T")
    db.add(org)
    db.flush()
    _empresa_com_dre(db, org, "Empresa A", "GRUPO X", [
        ("Receita Bruta", 1000), ("Receita Líquida", 900),
        ("Lucro ou Prejuízo do Exercício", 150),
    ])
    _empresa_com_dre(db, org, "Empresa B", "GRUPO X", [
        ("Receita Bruta", 500), ("Receita Líquida", 450),
        ("Lucro ou Prejuízo do Exercício", 50),
    ])
    assert len(companies_do_grupo(db, org.id, "GRUPO X")) == 2

    res = calcular_e_salvar_indicadores_grupo(db, org.id, "GRUPO X", 12, 2025)
    db.commit()
    assert res["integrantes"] == 2
    vals = {
        v.key: (float(v.valor) if v.valor is not None else None)
        for v in db.scalars(
            select(IndicatorValue).where(
                IndicatorValue.grupo == "GRUPO X", IndicatorValue.company_id.is_(None)
            )
        ).all()
    }
    assert vals["receita_bruta"] == 1500  # 1000 + 500
    assert vals["receita_liquida"] == 1350  # 900 + 450
    assert vals["lucro_liquido"] == 200  # 150 + 50
    assert vals["lucratividade_percentual"] == 14.81  # 200/1350*100


def test_definicao_org_sobrepoe_e_preserva_padroes(db):
    from app.domain.indicadores import INDICADORES

    org = Org(nome="T")
    db.add(org)
    db.flush()
    # Cenário do bug: APENAS overrides da org, sem linhas de sistema no banco.
    db.add(IndicatorDefinition(org_id=org.id, key="ebitda", label="EBITDA custom",
                               formula="lucro_liquido", formato="rs", ordem=5))
    db.add(IndicatorDefinition(org_id=org.id, key="meu_indicador", label="Meu",
                               formula="receita_bruta * 2", formato="rs", ordem=99))
    db.flush()
    defs = carregar_definicoes(db, org.id)
    keys = {d.key for d in defs}
    # As 23 padrão continuam presentes mesmo com overrides da org
    assert {d.key for d in INDICADORES} <= keys
    # Override aplicado e indicador novo presente
    assert next(d for d in defs if d.key == "ebitda").label == "EBITDA custom"
    assert "meu_indicador" in keys
    assert len(defs) == len(INDICADORES) + 1
