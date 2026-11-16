"""One-time password reset tokens and mail delivery."""

import hashlib
import os
import secrets
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from urllib.parse import urlencode, urlsplit

import bcrypt
import streamlit as st
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from streamlit.errors import StreamlitSecretNotFoundError

from database.models import TokenRedefinicaoSenha, Usuario
from services.audit_service import record_audit_event
from services.auth_service import (
    AuthorizationError,
    assert_user_role,
    get_active_user,
)
from utils.datetime_utils import app_timezone, now_local
from utils.validators import normalize_email, validate_password

PASSWORD_RESET_TTL = timedelta(minutes=30)


class PasswordResetError(ValueError):
    """Raised when a password reset cannot be completed."""


@dataclass(frozen=True)
class MailConfiguration:
    host: str
    port: int
    sender: str
    base_url: str
    username: str | None
    password: str | None
    use_ssl: bool
    use_starttls: bool


def _setting(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        configured = st.secrets.get(name)
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        configured = None
    return str(configured) if configured else None


def _validated_base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise PasswordResetError("APP_BASE_URL deve ser uma URL http(s) válida.")
    if parsed.scheme != "https" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise PasswordResetError("Links de redefinição em produção exigem HTTPS.")
    return value.strip().rstrip("/")


def _mail_configuration() -> MailConfiguration | None:
    host = _setting("SMTP_HOST")
    sender = _setting("SMTP_FROM")
    base_url = _setting("APP_BASE_URL")
    if not host or not sender or not base_url:
        return None

    try:
        port = int(_setting("SMTP_PORT") or "587")
    except ValueError as exc:
        raise PasswordResetError("SMTP_PORT deve ser um número.") from exc
    if not 1 <= port <= 65535:
        raise PasswordResetError("SMTP_PORT está fora do intervalo permitido.")

    username = _setting("SMTP_USER")
    password = _setting("SMTP_PASSWORD")
    if bool(username) != bool(password):
        raise PasswordResetError(
            "Configure SMTP_USER e SMTP_PASSWORD juntos ou deixe ambos vazios."
        )

    use_ssl = (_setting("SMTP_USE_SSL") or "false").strip().casefold() == "true"
    use_starttls = (_setting("SMTP_STARTTLS") or "true").strip().casefold() == "true"
    if use_ssl and use_starttls:
        raise PasswordResetError(
            "Use SMTP_USE_SSL ou SMTP_STARTTLS, não os dois ao mesmo tempo."
        )
    if not use_ssl and not use_starttls and host.casefold() not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise PasswordResetError("O servidor SMTP precisa usar TLS.")

    return MailConfiguration(
        host=host,
        port=port,
        sender=sender,
        base_url=_validated_base_url(base_url),
        username=username,
        password=password,
        use_ssl=use_ssl,
        use_starttls=use_starttls,
    )


def email_reset_is_configured() -> bool:
    return _mail_configuration() is not None


def app_base_url() -> str:
    configured_url = _setting("APP_BASE_URL")
    if not configured_url:
        raise PasswordResetError("Configure APP_BASE_URL para gerar links de redefinição.")
    return _validated_base_url(configured_url)


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=app_timezone())
    return value.astimezone(app_timezone())


def _issue_token(
    session: Session,
    user: Usuario,
    *,
    channel: str,
    created_by_id: int | None,
) -> tuple[TokenRedefinicaoSenha, str]:
    issued_at = now_local()
    session.execute(
        update(TokenRedefinicaoSenha)
        .where(
            TokenRedefinicaoSenha.usuario_id == user.id,
            TokenRedefinicaoSenha.usado_em.is_(None),
        )
        .values(usado_em=issued_at)
    )
    raw_token = secrets.token_urlsafe(32)
    token_record = TokenRedefinicaoSenha(
        usuario_id=user.id,
        token_hash=_token_digest(raw_token),
        canal=channel,
        criado_por_id=created_by_id,
        criado_em=issued_at,
        expira_em=issued_at + PASSWORD_RESET_TTL,
    )
    session.add(token_record)
    session.flush()
    record_audit_event(
        session,
        "auth.password_reset_link_created",
        actor_id=created_by_id,
        target_id=user.id,
        entity="password_reset_token",
        entity_id=token_record.id,
        details={"channel": channel},
    )
    return token_record, raw_token


def _reset_url(base_url: str, raw_token: str) -> str:
    return f"{base_url}/?{urlencode({'reset_token': raw_token})}"


def _send_reset_email(
    configuration: MailConfiguration, user: Usuario, reset_url: str
) -> None:
    message = EmailMessage()
    message["Subject"] = "Redefinição de senha — Ponto Fácil"
    message["From"] = configuration.sender
    message["To"] = user.email
    message.set_content(
        "Recebemos uma solicitação para redefinir a senha da sua conta Ponto Fácil.\n\n"
        f"Acesse este link em até 30 minutos para escolher uma nova senha:\n{reset_url}\n\n"
        "Se você não solicitou a redefinição, ignore esta mensagem."
    )

    context = ssl.create_default_context()
    if configuration.use_ssl:
        smtp = smtplib.SMTP_SSL(
            configuration.host,
            configuration.port,
            timeout=15,
            context=context,
        )
    else:
        smtp = smtplib.SMTP(
            configuration.host, configuration.port, timeout=15
        )
    with smtp:
        if configuration.use_starttls:
            smtp.starttls(context=context)
        if configuration.username and configuration.password:
            smtp.login(configuration.username, configuration.password)
        smtp.send_message(message)


def request_password_reset(session: Session, email: str) -> None:
    configuration = _mail_configuration()
    if configuration is None:
        raise PasswordResetError(
            "A recuperação por e-mail não está configurada. Procure RH/admin."
        )

    try:
        normalized_email = normalize_email(email)
    except ValueError:
        return
    user = session.scalar(
        select(Usuario).where(
            Usuario.email == normalized_email,
            Usuario.ativo.is_(True),
        )
    )
    if user is None:
        return

    token_record, raw_token = _issue_token(
        session, user, channel="email", created_by_id=None
    )
    session.commit()
    try:
        _send_reset_email(
            configuration,
            user,
            _reset_url(configuration.base_url, raw_token),
        )
    except (OSError, smtplib.SMTPException, ssl.SSLError) as exc:
        token_record.usado_em = now_local()
        record_audit_event(
            session,
            "auth.password_reset_email_failed",
            target_id=user.id,
            entity="password_reset_token",
            entity_id=token_record.id,
            details={"channel": "email"},
        )
        session.commit()
        raise PasswordResetError(
            "Não foi possível enviar o e-mail. Solicite um link ao RH/admin."
        ) from exc


def list_resettable_accounts(session: Session, actor_id: int) -> list[Usuario]:
    actor = get_active_user(session, actor_id)
    assert_user_role(actor, ("admin", "rh"))
    statement = select(Usuario).where(Usuario.ativo.is_(True))
    if actor.perfil == "rh":
        statement = statement.where(Usuario.perfil == "funcionario")
    return list(session.scalars(statement.order_by(Usuario.nome, Usuario.id)))


def create_admin_reset_link(
    session: Session,
    actor_id: int,
    target_id: int,
    base_url: str,
) -> tuple[str, datetime]:
    actor = get_active_user(session, actor_id)
    assert_user_role(actor, ("admin", "rh"))
    target = session.scalar(
        select(Usuario)
        .where(Usuario.id == target_id, Usuario.ativo.is_(True))
        .with_for_update()
    )
    if target is None:
        raise PasswordResetError("Conta ativa não encontrada.")
    if actor.perfil == "rh" and target.perfil != "funcionario":
        raise AuthorizationError(
            "RH só pode gerar link de redefinição para contas de funcionários."
        )

    safe_base_url = _validated_base_url(base_url)
    token_record, raw_token = _issue_token(
        session,
        target,
        channel="admin",
        created_by_id=actor_id,
    )
    session.commit()
    return _reset_url(safe_base_url, raw_token), token_record.expira_em


def consume_password_reset(
    session: Session, raw_token: str, new_password: str
) -> Usuario:
    try:
        validate_password(new_password)
    except ValueError as exc:
        raise PasswordResetError(str(exc)) from exc
    if not isinstance(raw_token, str) or not 32 <= len(raw_token) <= 128:
        raise PasswordResetError("Este link de redefinição é inválido ou expirou.")

    token_record = session.scalar(
        select(TokenRedefinicaoSenha)
        .where(TokenRedefinicaoSenha.token_hash == _token_digest(raw_token))
        .with_for_update()
    )
    current_time = _local_datetime(now_local())
    if (
        token_record is None
        or token_record.usado_em is not None
        or _local_datetime(token_record.expira_em) <= current_time
    ):
        raise PasswordResetError("Este link de redefinição é inválido ou expirou.")

    user = session.scalar(
        select(Usuario)
        .where(Usuario.id == token_record.usuario_id, Usuario.ativo.is_(True))
        .with_for_update()
    )
    if user is None:
        raise PasswordResetError("Este link de redefinição é inválido ou expirou.")

    user.senha_hash = bcrypt.hashpw(
        new_password.encode("utf-8"), bcrypt.gensalt()
    ).decode("ascii")
    token_record.usado_em = current_time
    session.execute(
        update(TokenRedefinicaoSenha)
        .where(
            TokenRedefinicaoSenha.usuario_id == user.id,
            TokenRedefinicaoSenha.id != token_record.id,
            TokenRedefinicaoSenha.usado_em.is_(None),
        )
        .values(usado_em=current_time)
    )
    record_audit_event(
        session,
        "auth.password_reset_completed",
        actor_id=user.id,
        target_id=user.id,
        entity="usuario",
        entity_id=user.id,
        details={
            "channel": token_record.canal,
            "initiated_by": token_record.criado_por_id,
        },
    )
    session.commit()
    session.refresh(user)
    return user
