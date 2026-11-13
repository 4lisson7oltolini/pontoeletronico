"""Index punch adjustments for efficient latest-effective-time lookups.

Revision ID: 0003_latest_punch_index
Revises: 0002_prefs_retro
"""
from alembic import op

revision = "0003_latest_punch_index"
down_revision = "0002_prefs_retro"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_ajustes_usuario_registro_data",
        "ajustes_ponto",
        ["usuario_id", "registro_ponto_id", "criado_em", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ajustes_usuario_registro_data", table_name="ajustes_ponto"
    )
