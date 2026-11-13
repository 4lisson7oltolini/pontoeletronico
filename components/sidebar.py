"""Authenticated account header shown above the active page."""

import streamlit as st


def render_account_header(user_name: str) -> None:
    with st.container(border=True):
        identity, actions = st.columns([4, 1], vertical_alignment="center")
        with identity:
            st.subheader("Ponto Fácil")
            st.caption(f"Olá, {user_name}")
        with actions:
            if st.button(
                "Sair",
                key="account_header_logout",
                type="secondary",
                width="stretch",
            ):
                for key in ("user_id", "user_name", "monthly_report_result"):
                    st.session_state.pop(key, None)
                st.rerun()
