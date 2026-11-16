import logging

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from database.connection import session_scope
from services.auth_service import AuthenticationError
from services.notificacao_service import (
    NotificacaoError,
    count_unread_notifications,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)

logger = logging.getLogger(__name__)
user_id, _ = require_user()

st.title("Notificações")

try:
    with session_scope() as session:
        notifications = list_notifications(session, user_id)
        unread_count = count_unread_notifications(session, user_id)
except (AuthenticationError, SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar notificações.")
    st.error("Não foi possível carregar suas notificações.")
    st.stop()

if unread_count:
    st.caption(f"{unread_count} notificação(ões) não lida(s).")
    if st.button("Marcar todas como lidas", width="stretch"):
        try:
            with session_scope() as session:
                mark_all_notifications_read(session, user_id)
            st.rerun()
        except (SQLAlchemyError, RuntimeError):
            logger.exception("Falha ao marcar notificações como lidas.")
            st.error("Não foi possível atualizar as notificações.")

if not notifications:
    st.info("Você ainda não tem notificações.")
else:
    for notification in notifications:
        with st.container(border=True):
            st.subheader(notification.titulo)
            st.caption(
                f"{notification.criada_em:%d/%m/%Y %H:%M}"
                + (" · Não lida" if notification.lida_em is None else " · Lida")
            )
            st.write(notification.mensagem)
            if notification.solicitacao_id is not None:
                st.caption(f"Solicitação #{notification.solicitacao_id}")
            if notification.lida_em is None and st.button(
                "Marcar como lida",
                key=f"read_notification_{notification.id}",
                width="stretch",
            ):
                try:
                    with session_scope() as session:
                        mark_notification_read(session, user_id, notification.id)
                    st.rerun()
                except NotificacaoError as exc:
                    st.warning(str(exc))
                except (SQLAlchemyError, RuntimeError):
                    logger.exception("Falha ao atualizar notificação.")
                    st.error("Não foi possível atualizar esta notificação.")
