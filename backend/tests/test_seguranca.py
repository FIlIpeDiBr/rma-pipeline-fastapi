"""Regras de segurança que não podem regredir sem alguém perceber."""

import io

import pytest
from docx import Document as DocxDocument
from docxtpl import DocxTemplate
from fastapi.routing import APIRoute
from jinja2.exceptions import SecurityError
from pydantic import ValidationError

from app.auth.deps import current_org_id, current_user
from app.config import SECRET_KEY_DEV, Settings
from app.http_utils import content_disposition
from app.main import app
from app.reports.builder import ambiente_jinja, eh_docx


def _docx(texto: str) -> bytes:
    doc = DocxDocument()
    doc.add_paragraph(texto)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _renderizar(template: bytes, ctx: dict) -> str:
    tpl = DocxTemplate(io.BytesIO(template))
    tpl.render(ctx, jinja_env=ambiente_jinja())
    out = io.BytesIO()
    tpl.save(out)
    return "\n".join(p.text for p in DocxDocument(io.BytesIO(out.getvalue())).paragraphs)


# --- Autenticação -----------------------------------------------------------

def _dependencias(dependant):
    for dep in dependant.dependencies:
        yield dep.call
        yield from _dependencias(dep)


def test_toda_rota_da_api_exige_autenticacao():
    abertas = [
        f"{sorted(rota.methods)} {rota.path}"
        for rota in app.routes
        if isinstance(rota, APIRoute)
        and rota.path.startswith("/api")
        and not {current_org_id, current_user} & set(_dependencias(rota.dependant))
    ]
    assert abertas == []


def test_fora_da_api_so_ficam_abertos_saude_e_login():
    abertas = {
        rota.path
        for rota in app.routes
        if isinstance(rota, APIRoute) and not rota.path.startswith("/api")
    }
    assert abertas <= {"/healthz", "/auth/login", "/auth/callback", "/auth/logout", "/"}


# --- Configuração -----------------------------------------------------------

def test_chave_de_sessao_padrao_e_recusada_em_producao():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, environment="production", secret_key=SECRET_KEY_DEV)


def test_chave_de_sessao_padrao_vale_em_desenvolvimento_e_propria_vale_em_producao():
    assert Settings(_env_file=None, environment="development").secret_key == SECRET_KEY_DEV
    s = Settings(_env_file=None, environment="production", secret_key="um-valor-proprio-e-longo")
    assert s.is_production


# --- Templates de relatório -------------------------------------------------

def test_template_nao_alcanca_os_internos_do_python():
    template = _docx("{{ ''.__class__.__mro__[1].__subclasses__() }}")
    with pytest.raises(SecurityError):
        _renderizar(template, {})


def test_valores_com_e_comercial_e_sinal_de_menor_nao_quebram_o_documento():
    texto = _renderizar(_docx("Empresa: {{ empresa }}"), {"empresa": "Silva & Filhos <Matriz>"})
    assert texto == "Empresa: Silva & Filhos <Matriz>"


def test_eh_docx_reconhece_docx_e_recusa_o_resto():
    assert eh_docx(_docx("qualquer")) is True
    assert eh_docx(b"%PDF-1.7 conteudo") is False
    assert eh_docx(b"PK\x03\x04 zip truncado") is False
    assert eh_docx(b"") is False


# --- Download ---------------------------------------------------------------

def test_content_disposition_preserva_acentos_no_nome_utf8():
    cab = content_disposition("RMA São João Março_2026.docx")
    assert 'filename="RMA Sao Joao Marco_2026.docx"' in cab
    assert "filename*=UTF-8''RMA%20S%C3%A3o%20Jo%C3%A3o%20Mar%C3%A7o_2026.docx" in cab
    cab.encode("latin-1")  # o servidor ASGI exige cabeçalho em Latin-1


def test_content_disposition_neutraliza_aspas_e_quebra_de_linha():
    cab = content_disposition('balancete".pdf\r\nSet-Cookie: sessao=roubada')
    assert "\r" not in cab and "\n" not in cab
    assert cab.count('"') == 2  # só as aspas que delimitam o nome


def test_content_disposition_com_nome_vazio_ou_so_simbolos():
    assert 'filename="arquivo"' in content_disposition("")
    assert 'filename="arquivo"' in content_disposition("日本語")
    assert "filename*=UTF-8''%E6%97%A5%E6%9C%AC%E8%AA%9E" in content_disposition("日本語")
