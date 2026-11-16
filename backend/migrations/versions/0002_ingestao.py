"""Núcleo de ingestão: companies, documents, balance_lines, dre_lines, ai_calls, job_events.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("nome", sa.String(300), nullable=False),
        sa.Column("nome_canonico", sa.String(300), nullable=False),
        sa.Column("cnpj", sa.String(20), nullable=False, server_default=""),
        sa.Column("grupo", sa.String(200), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "nome_canonico", name="uq_company_org_canon"),
    )
    op.create_index("ix_companies_org", "companies", ["org_id"])
    op.create_index("ix_companies_canon", "companies", ["nome_canonico"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("nome_arquivo", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False, server_default=""),
        sa.Column("tamanho", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("origem", sa.String(20), nullable=False, server_default="UPLOAD"),
        sa.Column("empresa_nome", sa.String(300), nullable=False, server_default=""),
        sa.Column("tipo", sa.String(10), nullable=True),
        sa.Column("mes", sa.Integer(), nullable=True),
        sa.Column("ano", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="RECEBIDO"),
        sa.Column("mensagem", sa.Text(), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_org", "documents", ["org_id"])
    op.create_index("ix_documents_company", "documents", ["company_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_sha256", "documents", ["sha256"])
    op.create_index(
        "ix_documents_chave", "documents", ["org_id", "company_id", "mes", "ano", "tipo"]
    )

    for tabela in ("balance_lines", "dre_lines"):
        cols = [
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "document_id",
                sa.Uuid(),
                sa.ForeignKey("documents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=False),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=True),
            sa.Column("mes", sa.Integer(), nullable=True),
            sa.Column("ano", sa.Integer(), nullable=True),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        ]
        if tabela == "balance_lines":
            cols += [
                sa.Column("conta", sa.String(400), nullable=False, server_default=""),
                sa.Column("categoria", sa.String(60), nullable=True),
                sa.Column("is_sintetico", sa.Boolean(), nullable=False, server_default=sa.false()),
                sa.Column("saldo_anterior", sa.Numeric(18, 2), nullable=False, server_default="0"),
                sa.Column("debito", sa.Numeric(18, 2), nullable=False, server_default="0"),
                sa.Column("credito", sa.Numeric(18, 2), nullable=False, server_default="0"),
                sa.Column("saldo_atual", sa.Numeric(18, 2), nullable=False, server_default="0"),
            ]
        else:
            cols += [
                sa.Column("conta", sa.String(120), nullable=False, server_default=""),
                sa.Column("is_sintetico", sa.Boolean(), nullable=False, server_default=sa.true()),
                sa.Column("valor_atual", sa.Numeric(18, 2), nullable=False, server_default="0"),
                sa.Column("valor_anterior", sa.Numeric(18, 2), nullable=False, server_default="0"),
            ]
        cols += [
            sa.Column("av_atual", sa.Numeric(12, 4), nullable=True),
            sa.Column("av_anterior", sa.Numeric(12, 4), nullable=True),
            sa.Column("ah", sa.Numeric(12, 4), nullable=True),
        ]
        op.create_table(tabela, *cols)
        op.create_index(f"ix_{tabela}_document", tabela, ["document_id"])
        op.create_index(f"ix_{tabela}_periodo", tabela, ["org_id", "company_id", "mes", "ano"])

    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tipo", sa.String(30), nullable=False, server_default=""),
        sa.Column("modelo", sa.String(60), nullable=False, server_default=""),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("custo_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("duracao_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sucesso", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("erro", sa.Text(), nullable=False, server_default=""),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("resposta", sa.Text(), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_calls_org", "ai_calls", ["org_id"])
    op.create_index("ix_ai_calls_document", "ai_calls", ["document_id"])
    op.create_index("ix_ai_calls_criado", "ai_calls", ["criado_em"])

    op.create_table(
        "job_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("etapa", sa.String(60), nullable=False, server_default=""),
        sa.Column("progresso", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="info"),
        sa.Column("mensagem", sa.Text(), nullable=False, server_default=""),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_events_document", "job_events", ["document_id"])
    op.create_index("ix_job_events_criado", "job_events", ["criado_em"])


def downgrade() -> None:
    op.drop_table("job_events")
    op.drop_table("ai_calls")
    op.drop_table("dre_lines")
    op.drop_table("balance_lines")
    op.drop_table("documents")
    op.drop_table("companies")
