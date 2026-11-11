"""Input validation shared by services and UI."""

import re
from datetime import date


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if len(normalized) > 254 or not _EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Informe um e-mail válido.")
    return normalized


def validate_password(password: str) -> None:
    if len(password) < 10:
        raise ValueError("A senha deve ter pelo menos 10 caracteres.")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("A senha não pode ultrapassar 72 bytes.")


def validate_date(value: date) -> None:
    if not isinstance(value, date):
        raise ValueError("Informe uma data válida.")
