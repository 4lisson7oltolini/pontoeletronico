import pytest

from services.auth_service import (
    AuthenticationError,
    AuthorizationError,
    authenticate_user,
    assert_user_role,
    get_active_user,
    register_user,
)
from services.admin_service import AdminError, update_account_access


def test_register_and_authenticate_user(session):
    user = register_user(session, "Ana Silva", "ANA@example.com", "senha-segura-123")

    assert user.email == "ana@example.com"
    assert user.perfil == "funcionario"
    assert user.senha_hash != "senha-segura-123"
    assert authenticate_user(session, "ana@example.com", "senha-segura-123").id == user.id
    with pytest.raises(AuthenticationError, match="inválidos"):
        authenticate_user(session, "ana@example.com", "senha-errada")


def test_admin_registration_creates_separate_admin_account(session):
    from services.auth_service import register_admin_user

    user = register_admin_user(
        session, "Admin da Empresa", "admin@example.com", "senha-admin-segura-123"
    )

    assert user.perfil == "admin"
    assert user.email == "admin@example.com"


def test_role_guard_rejects_employee_from_admin_page(session):
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")

    with pytest.raises(AuthorizationError, match="permissão"):
        assert_user_role(user, ("admin",))


def test_admin_cannot_demote_last_active_admin(session):
    from services.auth_service import register_admin_user

    admin = register_admin_user(
        session, "Admin", "admin@example.com", "senha-admin-segura-123"
    )

    with pytest.raises(AdminError, match="pelo menos um administrador"):
        update_account_access(session, admin.id, admin.id, "rh", True)


def test_duplicate_accounts_are_rejected_case_insensitively(session):
    register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")

    with pytest.raises(AuthenticationError, match="Já existe"):
        register_user(session, "Outra Ana", "ANA@example.com", "outra-senha-123")


def test_inactive_account_cannot_authenticate(session):
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")
    user.ativo = False
    session.commit()

    with pytest.raises(AuthenticationError):
        authenticate_user(session, user.email, "senha-segura-123")
    with pytest.raises(AuthenticationError):
        get_active_user(session, user.id)
