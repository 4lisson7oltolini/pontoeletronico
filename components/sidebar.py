"""Authenticated account header shown above the active page."""

import streamlit as st


def render_account_header(user_name: str, unread_notification_count: int) -> None:
    with st.container(border=True):
        st.subheader("Ponto Fácil")
        st.caption(f"Olá, {user_name}")
        if unread_notification_count:
            st.caption(
                f"{unread_notification_count} notificação(ões) não lida(s)."
            )
        if st.button(
            "Sair",
            key="account_header_logout",
            type="secondary",
            width="stretch",
        ):
            for key in (
                "user_id",
                "user_name",
                "remember_token",
                "monthly_report_result",
                "admin_reset_link_result",
            ):
                st.session_state.pop(key, None)
            st.session_state["clear_session_cookie"] = True
            st.rerun()
