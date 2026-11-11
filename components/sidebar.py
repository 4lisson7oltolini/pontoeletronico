"""Authenticated navigation sidebar."""

import streamlit as st


def render_sidebar(user_name: str) -> None:
    with st.sidebar:
        st.markdown("## Ponto Fácil")
        st.caption(f"Olá, {user_name}")
        if st.button("Sair", width="stretch", type="secondary"):
            for key in ("user_id", "user_name"):
                st.session_state.pop(key, None)
            st.rerun()
