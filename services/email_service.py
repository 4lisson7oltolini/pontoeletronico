"""Shared SMTP configuration and message delivery."""

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


class EmailConfigurationError(ValueError):
    """Raised when SMTP settings are incomplete or unsafe."""


@dataclass(frozen=True)
class SMTPConfiguration:
    host: str
    port: int
    sender: str
    username: str | None
    password: str | None
    use_ssl: bool
    use_starttls: bool


def setting(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        configured = st.secrets.get(name)
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        configured = None
    return str(configured) if configured else None


def get_smtp_configuration() -> SMTPConfiguration | None:
    host = setting("SMTP_HOST")
    sender = setting("SMTP_FROM")
    if not host or not sender:
        return None

    try:
        port = int(setting("SMTP_PORT") or "587")
    except ValueError as exc:
        raise EmailConfigurationError("SMTP_PORT deve ser um número.") from exc
    if not 1 <= port <= 65535:
        raise EmailConfigurationError("SMTP_PORT está fora do intervalo permitido.")

    username = setting("SMTP_USER")
    password = setting("SMTP_PASSWORD")
    if bool(username) != bool(password):
        raise EmailConfigurationError(
            "Configure SMTP_USER e SMTP_PASSWORD juntos ou deixe ambos vazios."
        )

    use_ssl = (setting("SMTP_USE_SSL") or "false").strip().casefold() == "true"
    use_starttls = (setting("SMTP_STARTTLS") or "true").strip().casefold() == "true"
    if use_ssl and use_starttls:
        raise EmailConfigurationError(
            "Use SMTP_USE_SSL ou SMTP_STARTTLS, não os dois ao mesmo tempo."
        )
    if not use_ssl and not use_starttls and host.casefold() not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise EmailConfigurationError("O servidor SMTP precisa usar TLS.")

    return SMTPConfiguration(
        host=host,
        port=port,
        sender=sender,
        username=username,
        password=password,
        use_ssl=use_ssl,
        use_starttls=use_starttls,
    )


def send_email_message(
    configuration: SMTPConfiguration,
    message: EmailMessage,
    recipients: list[str],
) -> None:
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
        smtp.send_message(message, to_addrs=recipients)
