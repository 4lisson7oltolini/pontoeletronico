"""Ponto Fácil Streamlit application entry point."""

import logging
from pathlib import Path

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from database.connection import session_scope
from services.preferencias_service import (
    PreferenciasError,
    get_accessibility_preferences,
)
from services.auth_service import (
    AuthenticationError,
    authenticate_user,
    get_active_user,
    register_user,
)
from components.sidebar import render_account_header
from services.notificacao_service import count_unread_notifications
from services.password_reset_service import (
    PasswordResetError,
    consume_password_reset,
    email_reset_is_configured,
    request_password_reset,
)
from services.session_service import (
    create_remember_token,
    get_remembered_user_id,
)
from utils.accessibility import (
    apply_accessibility_preferences,
    apply_mobile_layout,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Ponto Fácil",
    page_icon="🕒",
    layout="wide",
    initial_sidebar_state="auto",
)

from components.session_cookie import (
    COOKIE_NAME,
    get_session_secret,
    set_session_cookie,
    sync_browser_consent,
)

apply_mobile_layout()

CONSENT_VERSION = "2026-11-v2"
LEGAL_DOCS_DIR = Path(__file__).parent / "docs"


def restore_remembered_session() -> None:
    if st.session_state.get("remembered_session_checked"):
        return
    st.session_state["remembered_session_checked"] = True

    token = st.context.cookies.get(COOKIE_NAME)
    if not token:
        return
    user_id = get_remembered_user_id(token, get_session_secret())
    if user_id is None:
        st.session_state["clear_session_cookie"] = True
        return
    st.session_state["user_id"] = user_id
    st.session_state["remember_token"] = token


def clear_reset_query_parameter() -> None:
    if "reset_token" in st.query_params:
        del st.query_params["reset_token"]


def render_login() -> None:
    st.title("Ponto Fácil")
    st.subheader("Sua jornada, organizada.")
    st.write("Controle seus registros e folgas em um espaço pessoal e seguro.")

    with st.expander("Termos de Uso"):
        st.markdown(
            (LEGAL_DOCS_DIR / "termos-de-uso.md").read_text(encoding="utf-8")
        )
    with st.expander("Política de Cookies"):
        st.markdown(
            (LEGAL_DOCS_DIR / "politica-de-cookies.md").read_text(
                encoding="utf-8"
            )
        )

    if consent_accepted and not st.session_state.get("show_consent_prompt", False):
        st.caption("Seu aceite está salvo neste navegador para a versão atual.")
        if st.button("Gerenciar consentimento", key="manage_consent"):
            st.session_state["show_consent_prompt"] = True
            st.session_state.pop("cookie_consent_choice", None)
            st.rerun()
    else:
        choice = st.segmented_control(
            "Aceita os Termos de Uso e a Política de Cookies?",
            ["Sim", "Não"],
            default=None,
            key="cookie_consent_choice",
        )
        if choice == "Não":
            st.error(
                "O acesso foi bloqueado porque o aceite não foi concedido. "
                "Esta página não pode fechar a aba automaticamente; você pode "
                "fechá-la ou alterar sua resposta."
            )
            return
        if choice is None:
            if not consent_storage_available:
                st.error(
                    "Não foi possível acessar o armazenamento do navegador. "
                    "Habilite o armazenamento local para continuar."
                )
            else:
                st.info("Leia os documentos e selecione Sim ou Não para continuar.")
            return
        if not consent_storage_available:
            st.error(
                "Não foi possível salvar o aceite neste navegador. "
                "Habilite o armazenamento local para continuar."
            )
            return
        if not consent_accepted:
            st.info("Registrando seu aceite no navegador. Aguarde um instante.")
            return
        st.session_state["show_consent_prompt"] = False
        st.rerun()

    if not consent_accepted or not consent_storage_available:
        return

    if st.session_state.pop("password_reset_completed", False):
        st.success("Senha redefinida. Entre com sua nova senha.")

    reset_token = st.query_params.get("reset_token")
    if reset_token:
        st.subheader("Redefinir senha")
        with st.form("password_reset_form"):
            new_password = st.text_input(
                "Nova senha (mínimo de 10 caracteres)",
                type="password",
                autocomplete="new-password",
            )
            confirmation = st.text_input(
                "Confirme a nova senha",
                type="password",
                key="password_reset_confirmation",
                autocomplete="new-password",
            )
            submitted = st.form_submit_button(
                "Salvar nova senha", type="primary", width="stretch"
            )
        if submitted:
            if new_password != confirmation:
                st.error("As senhas não conferem.")
            else:
                try:
                    with session_scope() as session:
                        consume_password_reset(session, reset_token, new_password)
                    for key in (
                        "user_id",
                        "user_name",
                        "remember_token",
                        "admin_reset_link_result",
                    ):
                        st.session_state.pop(key, None)
                    st.session_state["remembered_session_checked"] = True
                    st.session_state["clear_session_cookie"] = True
                    st.session_state["password_reset_completed"] = True
                    clear_reset_query_parameter()
                    st.rerun()
                except PasswordResetError as exc:
                    st.error(str(exc))
                except (SQLAlchemyError, RuntimeError):
                    logger.exception("Falha ao redefinir senha.")
                    st.error("Não foi possível redefinir a senha.")
        if st.button("Voltar para o login", key="back_from_password_reset"):
            clear_reset_query_parameter()
            st.session_state.pop("remembered_session_checked", None)
            st.rerun()
        return

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
                st.session_state["remembered_session_checked"] = True
                st.session_state["remember_token"] = create_remember_token(
                    user.id, get_session_secret()
                )
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
                st.session_state["remembered_session_checked"] = True
                st.session_state["remember_token"] = create_remember_token(
                    user.id, get_session_secret()
                )
                st.rerun()
            except AuthenticationError as exc:
                st.error(str(exc))
            except (SQLAlchemyError, RuntimeError):
                logger.exception("Falha de banco de dados durante o cadastro.")
                st.error("Não foi possível criar sua conta. Verifique a conexão com o banco.")

    with st.expander("Esqueci a senha"):
        try:
            email_recovery_available = email_reset_is_configured()
        except PasswordResetError as exc:
            logger.error("Configuração de recuperação por e-mail inválida: %s", exc)
            st.error(str(exc))
            email_recovery_available = False

        if not email_recovery_available:
            st.info(
                "A recuperação por e-mail ainda não está configurada. "
                "Peça um link temporário ao RH/admin."
            )
        else:
            with st.form("request_password_reset_form"):
                recovery_email = st.text_input(
                    "E-mail da conta", autocomplete="email"
                )
                reset_requested = st.form_submit_button(
                    "Enviar link de redefinição", width="stretch"
                )
            if reset_requested:
                try:
                    with session_scope() as session:
                        request_password_reset(session, recovery_email)
                except PasswordResetError:
                    logger.exception("Falha ao enviar e-mail de redefinição.")
                    st.info(
                        "Se o e-mail estiver cadastrado, enviaremos um link válido "
                        "por 30 minutos. Se não receber a mensagem, procure RH/admin."
                    )
                except (SQLAlchemyError, RuntimeError):
                    logger.exception("Falha ao processar pedido de redefinição.")
                    st.error("Não foi possível processar o pedido.")
                else:
                    st.info(
                        "Se o e-mail estiver cadastrado, enviaremos um link válido "
                        "por 30 minutos. Se não receber a mensagem, procure RH/admin."
                    )


if st.session_state.get("consent_choice_version") != CONSENT_VERSION:
    st.session_state.pop("cookie_consent_choice", None)
    st.session_state.pop("show_consent_prompt", None)
    st.session_state["consent_choice_version"] = CONSENT_VERSION

consent_choice = st.session_state.get("cookie_consent_choice")
if consent_choice not in {"Sim", "Não"}:
    consent_choice = None
browser_consent_accepted, consent_storage_available = sync_browser_consent(
    CONSENT_VERSION, consent_choice
)
consent_accepted = (
    consent_storage_available
    and browser_consent_accepted
    and consent_choice != "Não"
)

if not consent_accepted:
    for key in (
        "user_id",
        "user_name",
        "remember_token",
        "remembered_session_checked",
        "monthly_report_result",
        "admin_reset_link_result",
    ):
        st.session_state.pop(key, None)
    if consent_choice == "Não":
        st.session_state["clear_session_cookie"] = True
elif st.query_params.get("reset_token"):
    for key in (
        "user_id",
        "user_name",
        "remember_token",
        "remembered_session_checked",
        "monthly_report_result",
        "admin_reset_link_result",
    ):
        st.session_state.pop(key, None)
    st.session_state["remembered_session_checked"] = True
else:
    restore_remembered_session()

if not isinstance(st.session_state.get("user_id"), int):
    navigation = st.navigation(
        [st.Page(render_login, title="Entrar", icon=":material/login:")],
        position="hidden",
    )
else:
    try:
        with session_scope() as session:
            active_user = get_active_user(session, st.session_state["user_id"])
            preferences = get_accessibility_preferences(
                session, st.session_state["user_id"]
            )
            unread_notification_count = count_unread_notifications(
                session, st.session_state["user_id"]
            )
        user_role = active_user.perfil
        apply_accessibility_preferences(preferences)
    except (AuthenticationError, PreferenciasError):
        st.session_state.pop("user_id", None)
        st.session_state.pop("user_name", None)
        st.session_state.pop("remember_token", None)
        st.session_state.pop("admin_reset_link_result", None)
        st.session_state["clear_session_cookie"] = True
        st.session_state.pop("monthly_report_result", None)
        st.rerun()
    except (SQLAlchemyError, RuntimeError):
        logger.exception("Falha ao carregar preferências de acessibilidade.")
        st.error("Não foi possível carregar sua conta. Verifique a conexão com o banco.")
        st.stop()

    pages = [
        st.Page("pages/1_Dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
        st.Page("pages/3_Calendario.py", title="Calendário", icon=":material/calendar_month:"),
        st.Page("pages/4_Historico.py", title="Histórico", icon=":material/history:"),
        st.Page("pages/5_Relatorios.py", title="Relatórios", icon=":material/description:"),
        st.Page("pages/6_Configuracoes.py", title="Configurações", icon=":material/settings:"),
        st.Page(
            "pages/9_Notificacoes.py",
            title=(
                f"Notificações ({unread_notification_count})"
                if unread_notification_count
                else "Notificações"
            ),
            icon=":material/notifications:",
        ),
    ]
    if user_role == "funcionario":
        pages.insert(
            1,
            st.Page(
                "pages/2_Registrar_Ponto.py",
                title="Registrar ponto",
                icon=":material/schedule:",
            ),
        )
    if user_role in {"rh", "admin"}:
        pages.append(st.Page("pages/7_RH.py", title="Gestão de RH", icon=":material/groups:"))
    if user_role == "admin":
        pages.append(st.Page("pages/8_Admin.py", title="Administração", icon=":material/admin_panel_settings:"))
    if user_role in {"rh", "admin"}:
        pages.append(
            st.Page(
                "pages/10_Auditoria.py",
                title="Auditoria",
                icon=":material/manage_search:",
            )
        )
    with st.sidebar:
        render_account_header(
            st.session_state.get("user_name", ""),
            unread_notification_count,
        )
    navigation = st.navigation(pages, position="hidden")
    with st.sidebar:
        for page in pages:
            st.page_link(page, width="stretch")

if isinstance(st.session_state.get("user_id"), int):
    token = create_remember_token(
        st.session_state["user_id"], get_session_secret()
    )
    st.session_state["remember_token"] = token
    st.session_state.pop("clear_session_cookie", None)
    set_session_cookie(token)
elif st.session_state.pop("clear_session_cookie", False):
    set_session_cookie(None)

navigation.run()
