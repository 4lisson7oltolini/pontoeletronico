"""Authentication guard shared by all internal pages."""

import logging

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from database.connection import session_scope
from services.auth_service import (
    AuthenticationError,
    AuthorizationError,
    assert_user_role,
    get_active_user,
)

logger = logging.getLogger(__name__)


def require_user(*allowed_roles: str):
    user_id = st.session_state.get("user_id")
    if not isinstance(user_id, int):
        st.warning("Entre na sua conta para acessar esta página.")
        st.switch_page("app.py")
        st.stop()
    try:
        with session_scope() as session:
            user = get_active_user(session, user_id)
            if allowed_roles:
                assert_user_role(user, allowed_roles)
            return user.id, user.nome
    except AuthorizationError as exc:
        st.error(str(exc))
        st.switch_page("app.py")
        st.stop()
    except AuthenticationError:
        st.session_state.pop("user_id", None)
        st.session_state.pop("user_name", None)
        st.warning("Sua sessão expirou. Entre novamente.")
        st.switch_page("app.py")
        st.stop()
    except (SQLAlchemyError, RuntimeError):
        logger.exception("Falha ao validar a sessão autenticada.")
        st.error("Não foi possível validar sua sessão. Tente novamente mais tarde.")
        st.stop()
