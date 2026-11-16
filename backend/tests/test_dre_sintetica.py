"""DRE sintética (RF-19): criação derivada, detecção de DRE real e substituição."""

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db import Base
from app.extraction.dre_sintetica import existe_dre_real, remover_dre_sintetica
from app.extraction.persist import salvar_dre
from app.models import Company, Document, DreLine, Org


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _doc(db, tipo, mes=9, ano=2025):
    org = Org(nome="T")
    db.add(org)
    db.flush()
    comp = Company(org_id=org.id, nome="ACME", nome_canonico="ACME")
    db.add(comp)
    db.flush()
    d = Document(org_id=org.id, company_id=comp.id, nome_arquivo="x", storage_key="k",
                 tipo=tipo, mes=mes, ano=ano, empresa_nome="ACME")
    db.add(d)
    db.flush()
    return org, comp, d


DADOS = {"linhas": [{"categoria": "Receita Bruta", "valor_atual": 1000},
                    {"categoria": "Lucro ou Prejuízo do Exercício", "valor_atual": 200}]}


def test_dre_sintetica_marca_derivada(db):
    org, comp, balanco = _doc(db, "BALANCO")
    salvar_dre(db, balanco, DADOS, derivada=True)
    db.flush()
    linhas = db.scalars(select(DreLine).where(DreLine.document_id == balanco.id)).all()
    assert linhas and all(ln.derivada for ln in linhas)
    # não há DRE real ainda
    assert existe_dre_real(db, org.id, comp.id, 9, 2025) is False


def test_dre_real_substitui_sintetica(db):
    org, comp, balanco = _doc(db, "BALANCO")
    salvar_dre(db, balanco, DADOS, derivada=True)
    db.flush()
    # chega a DRE real (outro documento, derivada=False)
    dre_doc = Document(org_id=org.id, company_id=comp.id, nome_arquivo="dre", storage_key="k2",
                       tipo="DRE", mes=9, ano=2025, empresa_nome="ACME")
    db.add(dre_doc)
    db.flush()
    salvar_dre(db, dre_doc, DADOS, derivada=False)
    db.flush()
    assert existe_dre_real(db, org.id, comp.id, 9, 2025) is True
    removidos = remover_dre_sintetica(db, org.id, comp.id, 9, 2025)
    db.flush()
    assert removidos > 0
    restantes = db.scalars(select(DreLine).where(DreLine.company_id == comp.id)).all()
    assert restantes and all(not ln.derivada for ln in restantes)  # só a real sobrou
