"""Fila de revisão de email + toggle de varredura + relatório anual.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-17

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orgs",
        sa.Column("email_poll_ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "reports",
        sa.Column("anual", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "email_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("message_id", sa.String(800), nullable=False),
        sa.Column("remetente", sa.String(320), nullable=False, server_default=""),
        sa.Column("assunto", sa.String(500), nullable=False, server_default=""),
        sa.Column("corpo", sa.Text(), nullable=False, server_default=""),
        sa.Column("recebido_em", sa.String(40), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDENTE"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_msg_org", "email_messages", ["org_id"])
    op.create_index("ix_email_msg_status", "email_messages", ["status"])
    op.create_index("ix_email_msg_mid", "email_messages", ["message_id"])

    op.create_table(
        "email_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "email_message_id",
            sa.Uuid(),
            sa.ForeignKey("email_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("nome", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False, server_default=""),
        sa.Column("tamanho", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.String(500), nullable=False, server_default=""),
        sa.Column("suportado", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("incluido", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_email_att_msg", "email_attachments", ["email_message_id"])


def downgrade() -> None:
    op.drop_table("email_attachments")
    op.drop_table("email_messages")
    op.drop_column("reports", "anual")
    op.drop_column("orgs", "email_poll_ativo")
