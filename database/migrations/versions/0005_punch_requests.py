"""Add employee punch-change requests.

Revision ID: 0005_punch_requests
Revises: 0004_user_roles
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_punch_requests"
down_revision = "0004_user_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "solicitacoes_ajuste_ponto",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("registro_ponto_id", sa.Integer(), nullable=True),
        sa.Column("operacao", sa.String(length=12), nullable=False),
        sa.Column("tipo_registro", sa.String(length=24), nullable=False),
        sa.Column("horario_solicitado", sa.DateTime(timezone=True), nullable=False),
        sa.Column("justificativa", sa.String(length=1000), nullable=False),
        sa.Column(
            "status",
            sa.String(length=12),
            server_default="pendente",
            nullable=False,
        ),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decidido_por_id", sa.Integer(), nullable=True),
        sa.Column("decidido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observacao_decisao", sa.String(length=1000), nullable=True),
        sa.CheckConstraint(
            "operacao IN ('correcao', 'inclusao')",
            name="ck_solicitacoes_ajuste_operacao",
        ),
        sa.CheckConstraint(
            "status IN ('pendente', 'aprovada', 'rejeitada')",
            name="ck_solicitacoes_ajuste_status",
        ),
        sa.CheckConstraint(
            "(operacao = 'inclusao' AND registro_ponto_id IS NULL) OR "
            "(operacao = 'correcao' AND registro_ponto_id IS NOT NULL)",
            name="ck_solicitacoes_ajuste_registro",
        ),
        sa.CheckConstraint(
            "tipo_registro IN ('entrada', 'saida_intervalo', "
            "'retorno_intervalo', 'saida')",
            name="ck_solicitacoes_ajuste_tipo",
        ),
        sa.CheckConstraint(
            "(status = 'pendente' AND decidido_por_id IS NULL AND decidido_em IS NULL) "
            "OR (status IN ('aprovada', 'rejeitada') AND decidido_por_id IS NOT NULL "
            "AND decidido_em IS NOT NULL)",
            name="ck_solicitacoes_ajuste_decisao",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["decidido_por_id"], ["usuarios.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["registro_ponto_id", "usuario_id"],
            ["registros_ponto.id", "registros_ponto.usuario_id"],
            ondelete="RESTRICT",
            name="fk_solicitacoes_registro_do_usuario",
        ),
    )
    op.create_index(
        "ix_solicitacoes_status_data",
        "solicitacoes_ajuste_ponto",
        ["status", "criado_em"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_solicitacoes_status_data", table_name="solicitacoes_ajuste_ponto"
    )
    op.drop_table("solicitacoes_ajuste_ponto")