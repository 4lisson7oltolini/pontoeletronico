"""Administrator-only account management operations."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import Usuario
from services.auth_service import (
    AuthorizationError,
    assert_user_role,
    get_active_user,
)

USER_ROLES = ("admin", "rh", "funcionario")


class AdminError(ValueError):
    """Raised when an account-management operation is not allowed."""


def _require_admin(session: Session, actor_id: int) -> None:
    actor = get_active_user(session, actor_id)
    assert_user_role(actor, ("admin",))


def list_accounts(session: Session, actor_id: int) -> list[Usuario]:
    _require_admin(session, actor_id)
    return list(session.scalars(select(Usuario).order_by(Usuario.nome, Usuario.id)))


def update_account_access(
    session: Session,
    actor_id: int,
    target_id: int,
    profile: str,
    active: bool,
) -> Usuario:
    _require_admin(session, actor_id)
    if profile not in USER_ROLES:
        raise AdminError("Perfil inválido.")
    if actor_id == target_id and not active:
        raise AdminError("Não é permitido desativar a própria conta.")

    target = session.scalar(
        select(Usuario).where(Usuario.id == target_id).with_for_update()
    )
    if target is None:
        raise AdminError("Conta não encontrada.")

    removing_active_admin = (
        target.perfil == "admin"
        and target.ativo
        and (profile != "admin" or not active)
    )
    if removing_active_admin:
        other_admin_count = session.scalar(
            select(func.count())
            .select_from(Usuario)
            .where(
                Usuario.perfil == "admin",
                Usuario.ativo.is_(True),
                Usuario.id != target.id,
            )
        )
        if not other_admin_count:
            raise AdminError("É necessário manter pelo menos um administrador ativo.")

    target.perfil = profile
    target.ativo = active
    session.commit()
    session.refresh(target)
    return target