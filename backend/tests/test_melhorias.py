"""Melhorias: fila de revisão de email e relatório anual."""

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db import Base
from app.email import ingest
from app.models import (
    EMAIL_IGNORADO,
    EMAIL_PENDENTE,
    EMAIL_PROCESSADO,
    BalanceLine,
    Company,
    Document,
    DreLine,
    EmailAttachment,
    EmailMessage,
    IndicatorValue,
    Org,
)
from app.reports.context import montar_contexto


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _org(db):
    o = Org(nome="T")
    db.add(o)
    db.flush()
    return o


def _email(db, org, suportado=True):
    em = EmailMessage(org_id=org.id, message_id="m1", remetente="cli@x.com",
                      assunto="Balancete", corpo="segue anexo", status=EMAIL_PENDENTE)
    db.add(em)
    db.flush()
    att = EmailAttachment(email_message_id=em.id, org_id=org.id, nome="bal.pdf",
                          content_type="application/pdf", tamanho=10, suportado=suportado,
                          storage_key="email/k")
    db.add(att)
    db.flush()
    return em, att


def test_listar_e_ignorar(db):
    org = _org(db)
    _email(db, org)
    assert len(ingest.listar_pendentes(db, org.id)) == 1
    em = db.scalars(select(EmailMessage)).first()
    ingest.ignorar(db, org.id, em.id)
    assert em.status == EMAIL_IGNORADO
    assert len(ingest.listar_pendentes(db, org.id)) == 0


def test_importar_cria_documento(db, monkeypatch):
    org = _org(db)
    em, att = _email(db, org)
    monkeypatch.setattr(ingest.storage, "get_bytes", lambda k: b"conteudo")
    monkeypatch.setattr(ingest.storage, "save_bytes", lambda *a, **k: None)

    res = ingest.importar(db, org.id, em.id, [str(att.id)])
    assert len(res["documentos"]) == 1
    db.refresh(att)
    db.refresh(em)
    assert att.incluido and att.document_id is not None
    assert em.status == EMAIL_PROCESSADO
    doc = db.get(Document, att.document_id)
    assert doc.origem == "EMAIL" and doc.remetente == "cli@x.com"


def test_importar_ignora_nao_suportado(db, monkeypatch):
    org = _org(db)
    em, att = _email(db, org, suportado=False)
    monkeypatch.setattr(ingest.storage, "get_bytes", lambda k: b"x")
    monkeypatch.setattr(ingest.storage, "save_bytes", lambda *a, **k: None)
    res = ingest.importar(db, org.id, em.id, [str(att.id)])
    assert len(res["documentos"]) == 0  # anexo não suportado não vira documento


def test_contexto_anual(db):
    org = _org(db)
    c = Company(org_id=org.id, nome="ACME", nome_canonico="ACME")
    db.add(c)
    db.flush()
    doc = Document(org_id=org.id, company_id=c.id, nome_arquivo="x", storage_key="k",
                   tipo="BALANCO", mes=12, ano=2025, empresa_nome="ACME")
    db.add(doc)
    db.flush()
    db.add(BalanceLine(document_id=doc.id, org_id=org.id, company_id=c.id, mes=12, ano=2025,
                       conta="ATIVO TOTAL", categoria="ATIVO TOTAL", is_sintetico=True,
                       saldo_atual=5000))
    db.add(DreLine(document_id=doc.id, org_id=org.id, company_id=c.id, mes=12, ano=2025,
                   conta="Receita Bruta", is_sintetico=True, valor_atual=1000))
    for ano, val in ((2025, 1000), (2024, 800)):
        db.add(IndicatorValue(org_id=org.id, company_id=c.id, grupo="", mes=12, ano=ano,
                              key="receita_bruta", label="Receita Bruta (R$)", formato="rs",
                              valor=val))
    # DRE do exercício anterior (2024), em outro documento
    doc24 = Document(org_id=org.id, company_id=c.id, nome_arquivo="2024", storage_key="k24",
                     tipo="DRE", mes=12, ano=2024, empresa_nome="ACME")
    db.add(doc24)
    db.flush()
    db.add(DreLine(document_id=doc24.id, org_id=org.id, company_id=c.id, mes=12, ano=2024,
                   conta="Receita Bruta", is_sintetico=True, valor_atual=800))
    db.flush()

    ctx = montar_contexto(db, org.id, company_id=c.id, mes=1, ano=2025, anual=True)
    assert ctx["anual"] is True
    assert ctx["periodo_atual"] == "2025" and ctx["periodo_anterior"] == "2024"
    assert ctx["_chave_atual"] == "atual" and ctx["_chave_anterior"] == "anterior"
    assert ctx["indicadores"]["atual"]["Receita Bruta (R$)"] == 1000
    assert ctx["indicadores"]["anterior"]["Receita Bruta (R$)"] == 800
    assert ctx["integrantes"][0]["balanco"][0]["conta"] == "ATIVO TOTAL"
    # tabela DRE anual: coluna anterior (2024) puxada do documento de 2024
    rb = next(r for r in ctx["integrantes"][0]["dre"] if r["conta"] == "Receita Bruta")
    assert rb["atual"] == "1.000,00" and rb["anterior"] == "800,00"
    assert rb["ah"] == "25,00"  # (1000-800)/800*100


def test_excel_so_primeira_aba_com_aviso():
    import io

    import openpyxl

    from app.extraction.converter import preparar_entrada_ia

    wb = openpyxl.Workbook()
    a = wb.active
    a.title = "DRE 2024"
    a.append(["DEMONSTRATIVO DE RESULTADO DO EXERCICIO - DRE 2024"])
    a.append(["Receita Bruta", 100000])
    a.append(["Custos", -30000])
    a.append(["Lucro do Exercicio 2024", 70000])
    b = wb.create_sheet("DRE 2025")
    b.append(["DRE 2025", 999999])
    wb.create_sheet("Comparativo")
    buf = io.BytesIO()
    wb.save(buf)

    e = preparar_entrada_ia(
        "x.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buf.getvalue(),
    )
    assert e.modo == "texto"
    assert "DRE 2024" in (e.texto or "") and "DRE 2025" not in (e.texto or "")
    assert "Abas ignoradas" in e.aviso and "DRE 2025" in e.aviso and "Comparativo" in e.aviso
