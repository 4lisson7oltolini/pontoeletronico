"""Track monthly report delivery for idempotent email jobs.

Revision ID: 0007_monthly_email
Revises: 0006_notify_reset_audit
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_monthly_email"
down_revision = "0006_notify_reset_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "envios_relatorios_mensais",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("ano", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=12),
            nullable=False,
            server_default="pendente",
        ),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mes BETWEEN 1 AND 12", name="ck_envios_relatorios_mes"),
        sa.CheckConstraint(
            "status IN ('pendente', 'enviado')",
            name="ck_envios_relatorios_status",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "usuario_id",
            "ano",
            "mes",
            name="uq_envios_relatorios_usuario_periodo",
        ),
    )
    op.create_index(
        "ix_envios_relatorios_status_periodo",
        "envios_relatorios_mensais",
        ["status", "ano", "mes"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_envios_relatorios_status_periodo",
        table_name="envios_relatorios_mensais",
    )
    op.drop_table("envios_relatorios_mensais")
