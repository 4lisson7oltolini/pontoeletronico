from datetime import datetime, timedelta
import smtplib
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from database.models import EventoAuditoria, TokenRedefinicaoSenha
from services import password_reset_service
from services.auth_service import (
    AuthenticationError,
    AuthorizationError,
    authenticate_user,
    register_admin_user,
    register_user,
)
from services.password_reset_service import (
    PasswordResetError,
    consume_password_reset,
    create_admin_reset_link,
    list_resettable_accounts,
    request_password_reset,
)

NOW = datetime(2026, 11, 16, 12, 0)


def _configure_mail(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "mailer@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "test-smtp-password")
    monkeypatch.setenv("SMTP_FROM", "Ponto Fácil <mailer@example.com>")
    monkeypatch.setenv("SMTP_USE_SSL", "false")
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    monkeypatch.setenv("APP_BASE_URL", "https://ponto.example.com")


def test_email_reset_uses_hashed_one_time_token_and_changes_password(
    session, monkeypatch
):
    _configure_mail(monkeypatch)
    user = register_user(
        session, "Ana", "ana@example.com", "senha-antiga-segura-123"
    )
    sent = {}

    def fake_send(configuration, recipient, reset_url):
        sent["recipient"] = recipient.email
        sent["url"] = reset_url

    monkeypatch.setattr(password_reset_service, "_send_reset_email", fake_send)
    request_password_reset(session, user.email)

    token = parse_qs(urlsplit(sent["url"]).query)["reset_token"][0]
    record = session.scalar(
        select(TokenRedefinicaoSenha).where(
            TokenRedefinicaoSenha.usuario_id == user.id
        )
    )
    assert sent["recipient"] == user.email
    assert record.token_hash != token
    assert record.canal == "email"

    consume_password_reset(session, token, "senha-nova-segura-456")
    assert authenticate_user(session, user.email, "senha-nova-segura-456").id == user.id
    with pytest.raises(AuthenticationError):
        authenticate_user(session, user.email, "senha-antiga-segura-123")
    with pytest.raises(PasswordResetError, match="inválido ou expirou"):
        consume_password_reset(session, token, "outra-senha-segura-789")

    assert session.scalar(
        select(EventoAuditoria.id).where(
            EventoAuditoria.acao == "auth.password_reset_completed"
        )
    )


def test_email_delivery_failure_revokes_token_and_reports_failure(
    session, monkeypatch
):
    _configure_mail(monkeypatch)
    user = register_user(
        session, "Ana", "ana@example.com", "senha-antiga-segura-123"
    )

    def fail_send(*_args):
        raise smtplib.SMTPException("mail server unavailable")

    monkeypatch.setattr(password_reset_service, "_send_reset_email", fail_send)
    with pytest.raises(PasswordResetError, match="Não foi possível enviar"):
        request_password_reset(session, user.email)

    token = session.scalar(
        select(TokenRedefinicaoSenha).where(
            TokenRedefinicaoSenha.usuario_id == user.id
        )
    )
    assert token.usado_em is not None
    assert session.scalar(
        select(EventoAuditoria.id).where(
            EventoAuditoria.acao == "auth.password_reset_email_failed"
        )
    )


def test_admin_reset_link_is_one_time_and_expires(session, monkeypatch):
    employee = register_user(
        session, "Ana", "ana@example.com", "senha-antiga-segura-123"
    )
    admin = register_admin_user(
        session, "Admin", "admin@example.com", "senha-admin-segura-123"
    )
    monkeypatch.setattr(password_reset_service, "now_local", lambda: NOW)

    reset_url, expires_at = create_admin_reset_link(
        session, admin.id, employee.id, "http://localhost:8501"
    )
    token = parse_qs(urlsplit(reset_url).query)["reset_token"][0]
    assert expires_at == NOW + timedelta(minutes=30)

    monkeypatch.setattr(
        password_reset_service,
        "now_local",
        lambda: NOW + timedelta(minutes=31),
    )
    with pytest.raises(PasswordResetError, match="inválido ou expirou"):
        consume_password_reset(session, token, "senha-nova-segura-456")


def test_rh_can_reset_employees_but_not_privileged_accounts(session):
    rh = register_user(session, "RH", "rh@example.com", "senha-rh-segura-123")
    rh.perfil = "rh"
    employee = register_user(
        session, "Ana", "ana@example.com", "senha-ana-segura-123"
    )
    admin = register_admin_user(
        session, "Admin", "admin@example.com", "senha-admin-segura-123"
    )
    session.commit()

    assert [account.id for account in list_resettable_accounts(session, rh.id)] == [
        employee.id
    ]
    with pytest.raises(AuthorizationError):
        create_admin_reset_link(
            session, rh.id, admin.id, "http://localhost:8501"
        )
