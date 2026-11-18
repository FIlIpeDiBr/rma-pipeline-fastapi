"""O esquema que as migrations criam num Postgres vazio."""

import pytest
from dados_de_teste import BACKEND
from sqlalchemy import text

pytestmark = pytest.mark.integracao


def test_migrations_chegam_ao_head(banco):
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with banco.connect() as conn:
        atual = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert atual == head


def test_modelos_e_migrations_descrevem_o_mesmo_esquema(banco):
    """Tabelas, colunas, tipos, chaves e índices: o que o ORM declara é o que o banco tem.

    Os testes de unidade criam o esquema a partir dos modelos (`create_all`); produção cria
    pelas migrations. Se os dois lados divergirem, os testes de unidade passam a testar um
    banco que não existe.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app import models  # noqa: F401 - registra as tabelas no metadata
    from app.db import Base

    do_dominio = set(Base.metadata.tables)

    def incluir(_objeto, nome, tipo, _refletido, _comparado) -> bool:
        # A fila (procrastinate_*) tem esquema próprio, fora dos modelos.
        return nome in do_dominio if tipo == "table" else True

    with banco.connect() as conn:
        contexto = MigrationContext.configure(conn, opts={"include_object": incluir})
        diferencas = compare_metadata(contexto, Base.metadata)
    assert diferencas == []


def test_definicoes_padrao_de_indicador_vem_das_migrations(banco):
    with banco.connect() as conn:
        padrao = conn.execute(
            text("SELECT count(*) FROM indicator_definitions WHERE org_id IS NULL")
        ).scalar()
    assert padrao == 23


def test_esquema_da_fila_foi_aplicado(banco):
    with banco.connect() as conn:
        tabela = conn.execute(text("SELECT to_regclass('procrastinate_jobs')")).scalar()
    assert tabela is not None
