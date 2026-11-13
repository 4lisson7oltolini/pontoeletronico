"""Add account roles.

Revision ID: 0004_user_roles
Revises: 0003_latest_punch_index
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_user_roles"
down_revision = "0003_latest_punch_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuarios",
        sa.Column(
            "perfil",
            sa.String(length=16),
            server_default="funcionario",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_usuarios_perfil",
        "usuarios",
        "perfil IN ('admin', 'rh', 'funcionario')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_usuarios_perfil", "usuarios", type_="check")
    op.drop_column("usuarios", "perfil")