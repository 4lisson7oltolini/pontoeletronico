"""Account-scoped accessibility preferences."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Usuario


class PreferenciasError(ValueError):
    """Raised when an accessibility preference is invalid."""


@dataclass(frozen=True)
class PreferenciasAcessibilidade:
    tema: str = "sistema"
    alto_contraste: bool = False
    escala_texto: Decimal = Decimal("1.00")
    reduzir_animacoes: bool = False


def get_accessibility_preferences(
    session: Session, user_id: int
) -> PreferenciasAcessibilidade:
    user = session.scalar(
        select(Usuario).where(Usuario.id == user_id, Usuario.ativo.is_(True))
    )
    if user is None:
        raise PreferenciasError("Conta não encontrada ou inativa.")
    return PreferenciasAcessibilidade(
        tema=user.tema_preferencia,
        alto_contraste=user.alto_contraste,
        escala_texto=Decimal(user.escala_texto),
        reduzir_animacoes=user.reduzir_animacoes,
    )


def save_accessibility_preferences(
    session: Session,
    user_id: int,
    tema: str,
    alto_contraste: bool,
    escala_texto: Decimal,
    reduzir_animacoes: bool,
) -> PreferenciasAcessibilidade:
    if tema not in {"claro", "escuro", "sistema"}:
        raise PreferenciasError("Selecione um tema válido.")
    if escala_texto not in {
        Decimal("0.90"),
        Decimal("1.00"),
        Decimal("1.10"),
        Decimal("1.25"),
        Decimal("1.50"),
    }:
        raise PreferenciasError("Selecione um tamanho de texto disponível.")

    user = session.scalar(
        select(Usuario).where(Usuario.id == user_id, Usuario.ativo.is_(True))
    )
    if user is None:
        raise PreferenciasError("Conta não encontrada ou inativa.")
    user.tema_preferencia = tema
    user.alto_contraste = alto_contraste
    user.escala_texto = escala_texto
    user.reduzir_animacoes = reduzir_animacoes
    session.commit()
    return get_accessibility_preferences(session, user_id)
