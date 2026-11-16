"""Indicadores: definitions (seed das 23) + values.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-16

"""
import datetime as dt
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.domain.indicadores import INDICADORES

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    defs = op.create_table(
        "indicator_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=True),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False, server_default=""),
        sa.Column("formato", sa.String(10), nullable=False, server_default="rs"),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "key", name="uq_ind_def_org_key"),
    )
    op.create_index("ix_ind_def_org", "indicator_definitions", ["org_id"])
    op.create_index("ix_ind_def_key", "indicator_definitions", ["key"])

    op.create_table(
        "indicator_values",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("grupo", sa.String(200), nullable=False, server_default=""),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("ano", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("label", sa.String(120), nullable=False, server_default=""),
        sa.Column("formato", sa.String(10), nullable=False, server_default=""),
        sa.Column("valor", sa.Numeric(18, 4), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "org_id", "company_id", "grupo", "mes", "ano", "key", name="uq_ind_val_entidade"
        ),
    )
    op.create_index("ix_ind_val_org", "indicator_values", ["org_id"])
    op.create_index("ix_ind_val_company", "indicator_values", ["company_id"])
    op.create_index("ix_ind_val_periodo", "indicator_values", ["org_id", "mes", "ano"])
    op.create_index("ix_ind_val_key", "indicator_values", ["key"])

    # Seed das 23 definições padrão do sistema (org_id NULL).
    agora = dt.datetime.now(dt.UTC)
    op.bulk_insert(
        defs,
        [
            {
                "id": uuid.uuid4(),
                "org_id": None,
                "key": d.key,
                "label": d.label,
                "formula": d.formula,
                "formato": d.formato,
                "ordem": i,
                "ativo": True,
                "criado_em": agora,
            }
            for i, d in enumerate(INDICADORES)
        ],
    )


def downgrade() -> None:
    op.drop_table("indicator_values")
    op.drop_table("indicator_definitions")
