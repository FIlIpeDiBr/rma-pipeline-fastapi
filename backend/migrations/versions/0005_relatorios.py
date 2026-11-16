"""Relatórios (Passo 5): templates + reports.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-16

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("descricao", sa.String(500), nullable=False, server_default=""),
        sa.Column("suporta_grupo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_templates_org", "templates", ["org_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("templates.id"), nullable=False),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("grupo", sa.String(200), nullable=False, server_default=""),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("ano", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="FILA"),
        sa.Column("progresso", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("etapa", sa.String(60), nullable=False, server_default=""),
        sa.Column("erro", sa.Text(), nullable=False, server_default=""),
        sa.Column("nome_arquivo", sa.String(300), nullable=False, server_default=""),
        sa.Column("storage_key", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "source_document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_org", "reports", ["org_id"])
    op.create_index("ix_reports_company", "reports", ["company_id"])
    op.create_index("ix_reports_status", "reports", ["status"])


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("templates")
