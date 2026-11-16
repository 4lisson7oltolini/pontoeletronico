"""Add in-app notifications, password reset tokens, and audit events.

Revision ID: 0006_notifications_password_audit
Revises: 0005_punch_requests
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_notifications_password_audit"
down_revision = "0005_punch_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notificacoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("solicitacao_id", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("mensagem", sa.String(length=500), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lida_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["solicitacao_id"],
            ["solicitacoes_ajuste_ponto.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_notificacoes_usuario_lida_criada",
        "notificacoes",
        ["usuario_id", "lida_em", "criada_em"],
    )

    op.create_table(
        "eventos_auditoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ator_usuario_id", sa.Integer(), nullable=True),
        sa.Column("alvo_usuario_id", sa.Integer(), nullable=True),
        sa.Column("acao", sa.String(length=64), nullable=False),
        sa.Column("entidade", sa.String(length=40), nullable=True),
        sa.Column("entidade_id", sa.Integer(), nullable=True),
        sa.Column("detalhes", sa.JSON(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ator_usuario_id"], ["usuarios.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["alvo_usuario_id"], ["usuarios.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_eventos_auditoria_criado_id",
        "eventos_auditoria",
        ["criado_em", "id"],
    )
    op.create_index(
        "ix_eventos_auditoria_alvo_criado",
        "eventos_auditoria",
        ["alvo_usuario_id", "criado_em"],
    )

    op.create_table(
        "tokens_redefinicao_senha",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("canal", sa.String(length=12), nullable=False),
        sa.Column("criado_por_id", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["criado_por_id"], ["usuarios.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_tokens_redefinicao_usuario_expira",
        "tokens_redefinicao_senha",
        ["usuario_id", "expira_em"],
    )
    op.create_index(
        "ix_tokens_redefinicao_hash",
        "tokens_redefinicao_senha",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_tokens_redefinicao_hash", table_name="tokens_redefinicao_senha")
    op.drop_index(
        "ix_tokens_redefinicao_usuario_expira",
        table_name="tokens_redefinicao_senha",
    )
    op.drop_table("tokens_redefinicao_senha")
    op.drop_index(
        "ix_eventos_auditoria_alvo_criado", table_name="eventos_auditoria"
    )
    op.drop_index(
        "ix_eventos_auditoria_criado_id", table_name="eventos_auditoria"
    )
    op.drop_table("eventos_auditoria")
    op.drop_index(
        "ix_notificacoes_usuario_lida_criada", table_name="notificacoes"
    )
    op.drop_table("notificacoes")
