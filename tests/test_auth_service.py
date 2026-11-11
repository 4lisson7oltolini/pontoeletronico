import pytest

from services.auth_service import (
    AuthenticationError,
    authenticate_user,
    get_active_user,
    register_user,
)


def test_register_and_authenticate_user(session):
    user = register_user(session, "Ana Silva", "ANA@example.com", "senha-segura-123")

    assert user.email == "ana@example.com"
    assert user.senha_hash != "senha-segura-123"
    assert authenticate_user(session, "ana@example.com", "senha-segura-123").id == user.id
    with pytest.raises(AuthenticationError, match="inválidos"):
        authenticate_user(session, "ana@example.com", "senha-errada")


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
