"""Add accessibility preferences and distinguish added punch audit entries.

Revision ID: 0002_prefs_retro
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_prefs_retro"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column(
            "tema_preferencia",
            sa.String(length=12),
            server_default="sistema",
            nullable=False,
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "alto_contraste",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "escala_texto",
            sa.Numeric(3, 2),
            server_default="1.00",
            nullable=False,
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "reduzir_animacoes",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "ajustes_ponto",
        sa.Column(
            "operacao",
            sa.String(length=12),
            server_default="correcao",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_ajustes_ponto_operacao",
        "ajustes_ponto",
        "operacao IN ('correcao', 'inclusao')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ajustes_ponto_operacao", "ajustes_ponto", type_="check"
    )
    op.drop_column("ajustes_ponto", "operacao")
    op.drop_column("usuarios", "reduzir_animacoes")
    op.drop_column("usuarios", "escala_texto")
    op.drop_column("usuarios", "alto_contraste")
    op.drop_column("usuarios", "tema_preferencia")
