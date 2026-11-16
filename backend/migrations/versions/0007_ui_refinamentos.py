"""enviado_por em documents + fórmulas simplificadas dos indicadores padrão.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-17

- Adiciona `documents.enviado_por` (quem subiu o arquivo no upload manual).
- Reescreve as fórmulas dos indicadores padrão (org_id NULL) para a sintaxe
  simplificada (sem {{}}, dre./bal./acum. ou safe_divide), refletindo o seed
  atualizado de app.domain.indicadores.INDICADORES.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

from app.domain.indicadores import INDICADORES

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("enviado_por", sa.String(320), nullable=False, server_default=""),
    )
    conn = op.get_bind()
    for d in INDICADORES:
        conn.execute(
            text(
                "UPDATE indicator_definitions SET formula = :f "
                "WHERE org_id IS NULL AND key = :k"
            ),
            {"f": d.formula, "k": d.key},
        )


def downgrade() -> None:
    op.drop_column("documents", "enviado_por")
