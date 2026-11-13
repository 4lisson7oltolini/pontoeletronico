"""Registration and password authentication."""

import bcrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import Usuario
from utils.datetime_utils import now_local
from utils.validators import normalize_email, validate_password


class AuthenticationError(ValueError):
    """Raised when registration or login cannot be completed."""


def _register_user(
    session: Session, nome: str, email: str, password: str, perfil: str
) -> Usuario:
    name = nome.strip()
    if not name or len(name) > 120:
        raise AuthenticationError("Informe seu nome (até 120 caracteres).")
    try:
        normalized_email = normalize_email(email)
        validate_password(password)
    except ValueError as exc:
        raise AuthenticationError(str(exc)) from exc

    existing = session.scalar(select(Usuario.id).where(Usuario.email == normalized_email))
    if existing is not None:
        raise AuthenticationError("Já existe uma conta com este e-mail.")

    user = Usuario(
        nome=name,
        email=normalized_email,
        senha_hash=bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii"),
        criado_em=now_local(),
        perfil=perfil,
        ativo=True,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise AuthenticationError("Já existe uma conta com este e-mail.") from exc
    session.refresh(user)
    return user


def register_user(session: Session, nome: str, email: str, password: str) -> Usuario:
    return _register_user(session, nome, email, password, perfil="funcionario")


def register_admin_user(
    session: Session, nome: str, email: str, password: str
) -> Usuario:
    """Create an administrator account for the local bootstrap command only."""
    return _register_user(session, nome, email, password, perfil="admin")


def authenticate_user(session: Session, email: str, password: str) -> Usuario:
    try:
        normalized_email = normalize_email(email)
    except ValueError:
        normalized_email = ""

    user = session.scalar(select(Usuario).where(Usuario.email == normalized_email))
    if (
        user is None
        or not user.ativo
        or len(password.encode("utf-8")) > 72
        or not bcrypt.checkpw(password.encode("utf-8"), user.senha_hash.encode("ascii"))
    ):
        raise AuthenticationError("E-mail ou senha inválidos.")
    return user


def get_active_user(session: Session, user_id: int) -> Usuario:
    user = session.scalar(select(Usuario).where(Usuario.id == user_id, Usuario.ativo.is_(True)))
    if user is None:
        raise AuthenticationError("Sua sessão expirou. Entre novamente.")
    return user
