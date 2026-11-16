"""Persistência transacional em SQLite em memória (sem Postgres/IA)."""

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db import Base
from app.domain.categories import SINTETICOS_BALANCO, SINTETICOS_DRE
from app.extraction.persist import (
    dedup_por_chave,
    get_or_create_company,
    salvar_balanco,
    salvar_dre,
)
from app.models import BalanceLine, Document, DreLine, Org


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _org_doc(db, tipo, mes=12, ano=2025):
    org = Org(nome="Teste")
    db.add(org)
    db.flush()
    doc = Document(
        org_id=org.id, nome_arquivo="x", storage_key="k", tipo=tipo, mes=mes, ano=ano,
        empresa_nome="ACME",
    )
    db.add(doc)
    db.flush()
    return org, doc


def test_company_dedup_por_canonico(db):
    org, _ = _org_doc(db, "BALANCO")
    c1 = get_or_create_company(db, org.id, "Iguiporã Agro Ltda – Holding")
    c2 = get_or_create_company(db, org.id, "IGUIPORA AGRO LTDA HOLDING")
    assert c1.id == c2.id


def test_salvar_balanco_garante_todas_categorias(db):
    org, doc = _org_doc(db, "BALANCO")
    dados = {
        "linhas": [
            {"conta": "1.1.01 CAIXA", "saldo_atual": 5497.70},
        ],
        "sinteticos": [
            {"categoria": "ATIVO", "saldo_atual": 4069025.38},
            {"categoria": "Caixa e Bancos", "saldo_atual": 5497.70},  # alias -> CONTAS/BANCOS
        ],
    }
    salvar_balanco(db, doc, dados)
    db.commit()
    sint = db.scalars(
        select(BalanceLine).where(
            BalanceLine.document_id == doc.id, BalanceLine.is_sintetico.is_(True)
        )
    ).all()
    assert len(sint) == len(SINTETICOS_BALANCO)  # RF-18: todas presentes
    cats = {s.categoria for s in sint}
    assert "CONTAS/BANCOS" in cats  # alias normalizado
    contas_banco = next(s for s in sint if s.categoria == "CONTAS/BANCOS")
    assert float(contas_banco.saldo_atual) == 5497.70
    analiticas = db.scalars(
        select(BalanceLine).where(
            BalanceLine.document_id == doc.id, BalanceLine.is_sintetico.is_(False)
        )
    ).all()
    assert len(analiticas) == 1


def test_salvar_dre_completa_e_substitui(db):
    org, doc = _org_doc(db, "DRE")
    salvar_dre(db, doc, {"linhas": [{"categoria": "Receita Bruta", "valor_atual": 1000}]})
    db.commit()
    linhas = db.scalars(select(DreLine).where(DreLine.document_id == doc.id)).all()
    assert len(linhas) == len(SINTETICOS_DRE)
    # Reprocessa: substitui (RF-16) sem duplicar
    salvar_dre(db, doc, {"linhas": [{"categoria": "Receita Bruta", "valor_atual": 2000}]})
    db.commit()
    linhas = db.scalars(select(DreLine).where(DreLine.document_id == doc.id)).all()
    assert len(linhas) == len(SINTETICOS_DRE)
    rb = next(x for x in linhas if x.conta == "Receita Bruta")
    assert float(rb.valor_atual) == 2000


def test_dedup_por_chave_remove_antigo(db):
    org, doc_novo = _org_doc(db, "BALANCO")
    company = get_or_create_company(db, org.id, "ACME")
    doc_novo.company_id = company.id
    # Documento antigo com a mesma chave de negócio
    antigo = Document(
        org_id=org.id, company_id=company.id, nome_arquivo="old", storage_key="o",
        tipo="BALANCO", mes=12, ano=2025, empresa_nome="ACME",
    )
    db.add(antigo)
    db.flush()
    removidos = dedup_por_chave(db, doc_novo)
    db.commit()
    assert removidos == 1
    restantes = db.scalars(select(Document)).all()
    assert len(restantes) == 1 and restantes[0].id == doc_novo.id
