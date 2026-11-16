"""RH/admin interface for creating one-time account recovery links."""

import logging

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from database.connection import session_scope
from services.auth_service import AuthenticationError, AuthorizationError
from services.password_reset_service import (
    PasswordResetError,
    app_base_url,
    create_admin_reset_link,
    list_resettable_accounts,
)

logger = logging.getLogger(__name__)


def render_admin_reset_links(actor_id: int) -> None:
    st.subheader("Redefinição de senha assistida")
    try:
        with session_scope() as session:
            accounts = list_resettable_accounts(session, actor_id)
    except (
        AuthenticationError,
        AuthorizationError,
        SQLAlchemyError,
        RuntimeError,
    ):
        logger.exception("Falha ao carregar contas para redefinição assistida.")
        st.error("Não foi possível carregar as contas.")
        return

    if not accounts:
        st.info("Não há contas ativas disponíveis para redefinição.")
        return

    labels = {
        account.id: f"{account.nome} · {account.email}" for account in accounts
    }
    with st.form(f"admin_reset_link_form_{actor_id}"):
        target_id = st.selectbox(
            "Conta",
            options=list(labels),
            format_func=labels.__getitem__,
        )
        submitted = st.form_submit_button(
            "Gerar link temporário", type="primary", width="stretch"
        )

    if submitted:
        try:
            with session_scope() as session:
                reset_url, expires_at = create_admin_reset_link(
                    session, actor_id, target_id, app_base_url()
                )
            st.session_state["admin_reset_link_result"] = {
                "url": reset_url,
                "expires_at": expires_at,
                "target": labels[target_id],
            }
        except (AuthorizationError, PasswordResetError) as exc:
            st.warning(str(exc))
        except (SQLAlchemyError, RuntimeError):
            logger.exception("Falha ao gerar link de redefinição assistida.")
            st.error("Não foi possível gerar o link.")

    result = st.session_state.get("admin_reset_link_result")
    if result:
        st.warning(
            f"Link de uso único para {result['target']}; expira em "
            f"{result['expires_at']:%d/%m/%Y %H:%M}. Compartilhe somente por "
            "um canal seguro."
        )
        st.code(result["url"], language=None)
        if st.button("Ocultar link", key=f"hide_admin_reset_link_{actor_id}"):
            st.session_state.pop("admin_reset_link_result", None)
            st.rerun()
