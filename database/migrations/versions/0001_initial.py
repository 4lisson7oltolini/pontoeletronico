"""Create the initial individual-account schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)
    op.create_table(
        "configuracoes_jornada",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("horas_diarias_referencia", sa.Numeric(4, 2), nullable=False),
        sa.Column("horas_semanais_referencia", sa.Numeric(5, 2), nullable=False),
        sa.Column("horario_entrada_preferencial", sa.Time(), nullable=True),
        sa.Column("horario_saida_preferencial", sa.Time(), nullable=True),
        sa.Column("quantidade_intervalos", sa.Integer(), nullable=False),
        sa.Column("fuso_horario", sa.String(length=64), nullable=False),
        sa.CheckConstraint("horas_diarias_referencia > 0", name="ck_jornada_horas_diarias"),
        sa.CheckConstraint("horas_semanais_referencia > 0", name="ck_jornada_horas_semanais"),
        sa.CheckConstraint("quantidade_intervalos >= 0", name="ck_jornada_intervalos"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("usuario_id", name="uq_configuracoes_jornada_usuario"),
    )
    op.create_table(
        "feriados",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("usuario_id", "data", name="uq_feriados_usuario_data"),
    )
    op.create_index("ix_feriados_usuario_data", "feriados", ["usuario_id", "data"])
    op.create_table(
        "folgas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("observacao", sa.String(length=500), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('planejada', 'realizada', 'cancelada')", name="ck_folgas_status"
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("usuario_id", "data", name="uq_folgas_usuario_data"),
    )
    op.create_index("ix_folgas_usuario_data", "folgas", ["usuario_id", "data"])
    op.create_table(
        "registros_ponto",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("tipo_registro", sa.String(length=24), nullable=False),
        sa.Column("data_hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origem", sa.String(length=40), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tipo_registro IN ('entrada', 'saida_intervalo', "
            "'retorno_intervalo', 'saida')",
            name="ck_registros_ponto_tipo",
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "usuario_id", name="uq_registros_ponto_id_usuario"),
    )
    op.create_index(
        "ix_registros_ponto_usuario_data", "registros_ponto", ["usuario_id", "data_hora"]
    )
    op.create_table(
        "ajustes_ponto",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("registro_ponto_id", sa.Integer(), nullable=False),
        sa.Column("horario_original", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horario_corrigido", sa.DateTime(timezone=True), nullable=False),
        sa.Column("justificativa", sa.String(length=1000), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["registro_ponto_id", "usuario_id"],
            ["registros_ponto.id", "registros_ponto.usuario_id"],
            ondelete="RESTRICT",
            name="fk_ajustes_registro_do_usuario",
        ),
    )
    op.create_index("ix_ajustes_ponto_usuario_data", "ajustes_ponto", ["usuario_id", "criado_em"])


def downgrade() -> None:
    op.drop_index("ix_ajustes_ponto_usuario_data", table_name="ajustes_ponto")
    op.drop_table("ajustes_ponto")
    op.drop_index("ix_registros_ponto_usuario_data", table_name="registros_ponto")
    op.drop_table("registros_ponto")
    op.drop_index("ix_folgas_usuario_data", table_name="folgas")
    op.drop_table("folgas")
    op.drop_index("ix_feriados_usuario_data", table_name="feriados")
    op.drop_table("feriados")
    op.drop_table("configuracoes_jornada")
    op.drop_index("ix_usuarios_email", table_name="usuarios")
    op.drop_table("usuarios")
