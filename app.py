"""Ponto Fácil Streamlit application entry point."""

import logging

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from database.connection import session_scope
from services.auth_service import (
    AuthenticationError,
    authenticate_user,
    register_user,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Ponto Fácil",
    page_icon="🕒",
    layout="wide",
    initial_sidebar_state="expanded",
)

def render_login() -> None:
    st.title("Ponto Fácil")
    st.subheader("Sua jornada, organizada.")
    st.write("Controle seus registros e folgas em um espaço pessoal e seguro.")
    login_tab, signup_tab = st.tabs(["Entrar", "Criar conta"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("E-mail", autocomplete="email")
            password = st.text_input("Senha", type="password", autocomplete="current-password")
            submitted = st.form_submit_button(
                "Entrar", type="primary", width="stretch"
            )
        if submitted:
            try:
                with session_scope() as session:
                    user = authenticate_user(session, email, password)
                st.session_state["user_id"] = user.id
                st.session_state["user_name"] = user.nome
                st.rerun()
            except AuthenticationError as exc:
                st.error(str(exc))
            except (SQLAlchemyError, RuntimeError):
                logger.exception("Falha de banco de dados durante o login.")
                st.error("Não foi possível acessar sua conta. Verifique a conexão com o banco.")

    with signup_tab:
        with st.form("signup_form"):
            name = st.text_input("Nome", autocomplete="name")
            email = st.text_input("E-mail", key="signup_email", autocomplete="email")
            password = st.text_input(
                "Senha (mínimo de 10 caracteres)",
                type="password",
                key="signup_password",
                autocomplete="new-password",
            )
            confirmation = st.text_input(
                "Confirme a senha",
                type="password",
                autocomplete="new-password",
            )
            submitted = st.form_submit_button(
                "Criar minha conta", type="primary", width="stretch"
            )
        if submitted:
            if password != confirmation:
                st.error("As senhas não conferem.")
                return
            try:
                with session_scope() as session:
                    user = register_user(session, name, email, password)
                st.session_state["user_id"] = user.id
                st.session_state["user_name"] = user.nome
                st.rerun()
            except AuthenticationError as exc:
                st.error(str(exc))
            except (SQLAlchemyError, RuntimeError):
                logger.exception("Falha de banco de dados durante o cadastro.")
                st.error("Não foi possível criar sua conta. Verifique a conexão com o banco.")


if not isinstance(st.session_state.get("user_id"), int):
    navigation = st.navigation(
        [st.Page(render_login, title="Entrar", icon=":material/login:")],
        position="hidden",
    )
else:
    pages = [
        st.Page("pages/1_Dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
        st.Page("pages/2_Registrar_Ponto.py", title="Registrar ponto", icon=":material/schedule:"),
        st.Page("pages/3_Calendario.py", title="Calendário", icon=":material/calendar_month:"),
        st.Page("pages/4_Historico.py", title="Histórico", icon=":material/history:"),
        st.Page("pages/5_Relatorios.py", title="Relatórios", icon=":material/description:"),
        st.Page("pages/6_Configuracoes.py", title="Configurações", icon=":material/settings:"),
    ]
    navigation = st.navigation(pages)
navigation.run()
