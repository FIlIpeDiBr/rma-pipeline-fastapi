"""Testes de integração: a API sobre um Postgres de verdade.

Rodam só quando pedidos (`pytest -m integracao`), com RMA_TESTE_INTEGRACAO=1 e contra um
banco cujo nome termine em `_teste`, porque as tabelas são esvaziadas a cada teste.

O que é real: o banco (esquema criado pelas migrations do Alembic), a fila (esquema do
Procrastinate, `defer` de verdade), as chaves estrangeiras e o LISTEN/NOTIFY.
O que é dublê: a IA e o storage de arquivos. O worker não sobe: a tarefa enfileirada é
conferida na tabela da fila e executada em linha.
"""

import asyncio
import os

import pytest
from dados_de_teste import ARQUIVO_TEXTO, BACKEND, IaFalsa
from sqlalchemy import text


def _exigir_banco_de_teste() -> None:
    if os.environ.get("RMA_TESTE_INTEGRACAO") != "1":
        pytest.skip("defina RMA_TESTE_INTEGRACAO=1 para rodar os testes de integração")
    from app.db import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("os testes de integração exigem Postgres")
    nome = engine.url.database or ""
    if not nome.endswith("_teste"):
        pytest.fail(f"recusado: o banco {nome!r} não termina em _teste e os testes apagam dados")


def _criar_esquema() -> None:
    """Sobe o esquema como em produção: migrations do Alembic e esquema da fila."""
    from alembic import command
    from alembic.config import Config

    from app.db import engine
    from app.jobs import job_app

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        fila_existe = conn.execute(text("SELECT to_regclass('procrastinate_jobs')")).scalar()
    if fila_existe:
        return

    async def aplicar() -> None:
        async with job_app.open_async():
            await job_app.schema_manager.apply_schema_async()

    asyncio.run(aplicar())


@pytest.fixture(scope="session")
def esquema() -> None:
    _exigir_banco_de_teste()
    _criar_esquema()


@pytest.fixture()
def banco(esquema):
    """Esvazia as tabelas do domínio. As definições padrão de indicador (seed) ficam."""
    from app import models  # noqa: F401 - registra as tabelas no metadata
    from app.db import Base, engine

    with engine.begin() as conn:
        for tabela in reversed(Base.metadata.sorted_tables):
            if tabela.name == "indicator_definitions":
                conn.execute(text("DELETE FROM indicator_definitions WHERE org_id IS NOT NULL"))
            else:
                conn.execute(tabela.delete())
    return engine


def _criar_org(nome: str):
    from app.db import SessionLocal
    from app.models import Org

    with SessionLocal() as db:
        org = Org(nome=nome)
        db.add(org)
        db.commit()
        return org


@pytest.fixture()
def org(banco):
    return _criar_org("Escritório Teste")


@pytest.fixture()
def outra_org(banco):
    return _criar_org("Outro Escritório")


@pytest.fixture()
def arquivos(monkeypatch) -> dict[str, bytes]:
    """Storage em memória no lugar do S3."""
    from app import storage

    guardados: dict[str, bytes] = {}

    def save_bytes(key: str, data: bytes, content_type: str = "") -> str:
        guardados[key] = data
        return key

    def get_bytes(key: str) -> bytes:
        return guardados[key]

    def delete(key: str) -> None:
        guardados.pop(key, None)

    monkeypatch.setattr(storage, "save_bytes", save_bytes)
    monkeypatch.setattr(storage, "get_bytes", get_bytes)
    monkeypatch.setattr(storage, "delete", delete)
    return guardados


@pytest.fixture()
def ia(monkeypatch) -> IaFalsa:
    from app import ai

    falsa = IaFalsa()
    for nome in ("triar", "extrair", "derivar_dre_de_balanco", "gerar_analise"):
        monkeypatch.setattr(ai, nome, getattr(falsa, nome))
    return falsa


@pytest.fixture()
def sessao(org) -> dict:
    """Quem está "logado". Trocar `sessao["org_id"]` muda a organização das próximas chamadas."""
    return {"org_id": org.id}


@pytest.fixture()
def cliente(sessao, arquivos, ia):
    """Cliente HTTP com o ciclo de vida da aplicação: fila aberta e barramento em LISTEN."""
    from fastapi.testclient import TestClient

    from app.auth.deps import current_org_id, current_user
    from app.main import app

    app.dependency_overrides[current_org_id] = lambda: sessao["org_id"]
    app.dependency_overrides[current_user] = lambda: {
        "nome": "Pessoa de Teste",
        "email": "teste@exemplo.com",
        "org_id": str(sessao["org_id"]),
    }
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


class Fila:
    """Consulta a tabela de jobs do Procrastinate."""

    def __init__(self, engine) -> None:
        self._engine = engine

    def pendentes(self, tarefa: str, **args) -> int:
        filtros = "".join(f" AND args->>'{nome}' = :{nome}" for nome in args)
        sql = text(
            "SELECT count(*) FROM procrastinate_jobs "
            f"WHERE task_name = :tarefa AND status = 'todo'{filtros}"
        )
        parametros = {"tarefa": tarefa, **{nome: str(valor) for nome, valor in args.items()}}
        with self._engine.connect() as conn:
            return conn.execute(sql, parametros).scalar()


@pytest.fixture()
def fila(banco) -> Fila:
    return Fila(banco)


@pytest.fixture()
def enviar(cliente):
    """Faz o upload de um arquivo e devolve o item criado."""

    def _enviar(nome: str, conteudo: bytes = ARQUIVO_TEXTO) -> dict:
        r = cliente.post(
            "/api/documents/upload", files=[("arquivos", (nome, conteudo, "text/csv"))]
        )
        assert r.status_code == 200, r.text
        (item,) = r.json()["criados"]
        return item

    return _enviar


@pytest.fixture()
def processar(enviar, fila):
    """Upload → confere o job na fila → executa a tarefa em linha. Devolve (id, resultado)."""
    from app.jobs.tasks import processar_documento

    def _processar(nome: str) -> tuple[str, dict]:
        item = enviar(nome)
        assert not item["aviso"], item["aviso"]  # a fila aceitou o job
        assert fila.pendentes("processar_documento", document_id=item["id"]) == 1
        return item["id"], processar_documento(document_id=item["id"])

    return _processar
