"""Recepção por email (RF-47): documents.remetente e companies.email.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-16

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("remetente", sa.String(320), nullable=False, server_default=""),
    )
    op.add_column(
        "companies",
        sa.Column("email", sa.String(320), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("companies", "email")
    op.drop_column("documents", "remetente")
