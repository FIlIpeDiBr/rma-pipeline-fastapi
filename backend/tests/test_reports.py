"""Relatórios: contexto a partir do banco e render docxtpl (sem IA, offline)."""

import io

import pytest
from docx import Document as Docx
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db import Base
from app.models import BalanceLine, Company, Document, DreLine, IndicatorValue, Org
from app.reports.builder import nome_arquivo, renderizar
from app.reports.context import montar_contexto
from app.reports.default_template import gerar_template_bytes


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_nome_arquivo():
    assert nome_arquivo("Grupo X/Y", 3, 2025) == "RMA Grupo X_Y Março_2025.docx"


def test_montar_contexto_empresa(db):
    org = Org(nome="T")
    db.add(org)
    db.flush()
    c = Company(org_id=org.id, nome="ACME", nome_canonico="ACME")
    db.add(c)
    db.flush()
    doc = Document(org_id=org.id, company_id=c.id, nome_arquivo="x", storage_key="k",
                   tipo="BALANCO", mes=12, ano=2025, empresa_nome="ACME")
    db.add(doc)
    db.flush()
    db.add(BalanceLine(document_id=doc.id, org_id=org.id, company_id=c.id, mes=12, ano=2025,
                       conta="ATIVO TOTAL", categoria="ATIVO TOTAL", is_sintetico=True,
                       saldo_atual=5000, av_atual=100))
    db.add(DreLine(document_id=doc.id, org_id=org.id, company_id=c.id, mes=12, ano=2025,
                   conta="Receita Bruta", is_sintetico=True, valor_atual=1000))
    db.add(IndicatorValue(
        org_id=org.id, company_id=c.id, grupo="", mes=12, ano=2025,
        key="receita_bruta", label="Receita Bruta (R$)", formato="rs", valor=1000,
    ))
    db.flush()

    ctx = montar_contexto(db, org.id, company_id=c.id, mes=12, ano=2025)
    assert ctx["entidade"] == "ACME"
    assert ctx["integrantes"][0]["balanco"][0]["conta"] == "ATIVO TOTAL"
    assert ctx["integrantes"][0]["balanco"][0]["atual"] == "5.000,00"  # pt-BR
    assert "atual" in ctx["indicadores"] and "anterior" in ctx["indicadores"]


def test_renderizar_sem_ia_gera_docx():
    ctx = {
        "entidade": "ACME", "grupo": "ACME", "eh_grupo": False, "mes": 12, "ano": 2025,
        "mes_nome": "Dezembro", "periodo_atual": "Dezembro/2025",
        "periodo_anterior": "Novembro/2025",
        "integrantes": [{
            "nome": "ACME",
            "balanco": [{"conta": "ATIVO TOTAL", "anterior": "0,00", "av_ant": "",
                         "atual": "5.000,00", "av_atu": "100,00", "ah": ""}],
            "dre": [{"conta": "Receita Bruta", "anterior": "0,00", "av_ant": "",
                     "atual": "1.000,00", "av_atu": "100,00", "ah": ""}],
            "analise_balanco": "", "analise_dre": "",
        }],
        "indicadores": {"12": {"Receita Bruta (R$)": 1000.0}, "11": {"Receita Bruta (R$)": 0.0}},
        "_chave_atual": "12", "_chave_anterior": "11",
    }
    docx = renderizar(gerar_template_bytes(), ctx, com_ia=False)
    d = Docx(io.BytesIO(docx))
    assert len(d.inline_shapes) == 6  # 6 gráficos
    sobrando = [p.text for p in d.paragraphs if "{{" in p.text or "{%" in p.text]
    assert not sobrando  # nenhuma tag Jinja sobrando
