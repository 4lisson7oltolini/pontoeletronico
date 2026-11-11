"""SQLAlchemy models for individual time tracking accounts."""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all application tables."""


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (Index("ix_usuarios_email", "email", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tema_preferencia: Mapped[str] = mapped_column(
        String(12), nullable=False, default="sistema"
    )
    alto_contraste: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escala_texto: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("1.00")
    )
    reduzir_animacoes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    registros_ponto: Mapped[list["RegistroPonto"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )
    folgas: Mapped[list["Folga"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )
    ajustes_ponto: Mapped[list["AjustePonto"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )
    configuracao_jornada: Mapped["ConfiguracaoJornada | None"] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", uselist=False
    )
    feriados: Mapped[list["Feriado"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )


class RegistroPonto(Base):
    __tablename__ = "registros_ponto"
    __table_args__ = (
        CheckConstraint(
            "tipo_registro IN ('entrada', 'saida_intervalo', "
            "'retorno_intervalo', 'saida')",
            name="ck_registros_ponto_tipo",
        ),
        UniqueConstraint("id", "usuario_id", name="uq_registros_ponto_id_usuario"),
        Index("ix_registros_ponto_usuario_data", "usuario_id", "data_hora"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    tipo_registro: Mapped[str] = mapped_column(String(24), nullable=False)
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    origem: Mapped[str] = mapped_column(String(40), nullable=False, default="web")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    usuario: Mapped[Usuario] = relationship(back_populates="registros_ponto")


class Folga(Base):
    __tablename__ = "folgas"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planejada', 'realizada', 'cancelada')",
            name="ck_folgas_status",
        ),
        UniqueConstraint("usuario_id", "data", name="uq_folgas_usuario_data"),
        Index("ix_folgas_usuario_data", "usuario_id", "data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    data: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planejada")
    observacao: Mapped[str | None] = mapped_column(String(500))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    usuario: Mapped[Usuario] = relationship(back_populates="folgas")


class AjustePonto(Base):
    __tablename__ = "ajustes_ponto"
    __table_args__ = (
        ForeignKeyConstraint(
            ["registro_ponto_id", "usuario_id"],
            ["registros_ponto.id", "registros_ponto.usuario_id"],
            ondelete="RESTRICT",
            name="fk_ajustes_registro_do_usuario",
        ),
        CheckConstraint(
            "operacao IN ('correcao', 'inclusao')", name="ck_ajustes_ponto_operacao"
        ),
        Index("ix_ajustes_ponto_usuario_data", "usuario_id", "criado_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    registro_ponto_id: Mapped[int] = mapped_column(nullable=False)
    horario_original: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horario_corrigido: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    justificativa: Mapped[str] = mapped_column(String(1000), nullable=False)
    operacao: Mapped[str] = mapped_column(String(12), nullable=False, default="correcao")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    usuario: Mapped[Usuario] = relationship(back_populates="ajustes_ponto")


class ConfiguracaoJornada(Base):
    __tablename__ = "configuracoes_jornada"
    __table_args__ = (
        CheckConstraint("horas_diarias_referencia > 0", name="ck_jornada_horas_diarias"),
        CheckConstraint("horas_semanais_referencia > 0", name="ck_jornada_horas_semanais"),
        CheckConstraint("quantidade_intervalos >= 0", name="ck_jornada_intervalos"),
        UniqueConstraint("usuario_id", name="uq_configuracoes_jornada_usuario"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    horas_diarias_referencia: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, default=Decimal("8.00")
    )
    horas_semanais_referencia: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("48.00")
    )
    horario_entrada_preferencial: Mapped[time | None] = mapped_column(Time)
    horario_saida_preferencial: Mapped[time | None] = mapped_column(Time)
    quantidade_intervalos: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fuso_horario: Mapped[str] = mapped_column(
        String(64), nullable=False, default="America/Sao_Paulo"
    )

    usuario: Mapped[Usuario] = relationship(back_populates="configuracao_jornada")


class Feriado(Base):
    __tablename__ = "feriados"
    __table_args__ = (
        UniqueConstraint("usuario_id", "data", name="uq_feriados_usuario_data"),
        Index("ix_feriados_usuario_data", "usuario_id", "data"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    data: Mapped[date] = mapped_column(Date, nullable=False)
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)

    usuario: Mapped[Usuario] = relationship(back_populates="feriados")
