import logging
from decimal import Decimal
from datetime import time

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from database.connection import session_scope
from services.jornada_service import JornadaError, get_schedule, save_schedule
from services.preferencias_service import (
    PreferenciasError,
    get_accessibility_preferences,
    save_accessibility_preferences,
)
from utils.accessibility import text_scale_from_label, text_scale_label

logger = logging.getLogger(__name__)
user_id, _ = require_user()

st.title("Configurações pessoais")
try:
    with session_scope() as session:
        schedule = get_schedule(session, user_id)
        preferences = get_accessibility_preferences(session, user_id)
except (PreferenciasError, SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar configurações.")
    st.error("Não foi possível carregar suas configurações.")
    st.stop()

st.subheader("Acessibilidade e aparência")
theme_options = {
    "Sistema (acompanhar o dispositivo)": "sistema",
    "Claro": "claro",
    "Escuro": "escuro",
}
scale_options = [
    "90% (compacto)",
    "100% (padrão)",
    "110%",
    "125%",
    "150% (ampliado)",
]
with st.form("accessibility_preferences_form"):
    selected_theme = st.selectbox(
        "Tema",
        list(theme_options),
        index=list(theme_options.values()).index(preferences.tema),
        help="A opção Sistema acompanha a preferência de claro/escuro do dispositivo.",
    )
    high_contrast = st.checkbox(
        "Alto contraste",
        value=preferences.alto_contraste,
        help="Aumenta o contraste de texto, superfícies, bordas e elementos principais.",
    )
    text_size = st.selectbox(
        "Tamanho do texto",
        scale_options,
        index=scale_options.index(text_scale_label(preferences.escala_texto)),
    )
    reduced_motion = st.checkbox(
        "Reduzir animações",
        value=preferences.reduzir_animacoes,
        help="Reduz animações e transições da interface.",
    )
    accessibility_submitted = st.form_submit_button(
        "Salvar acessibilidade", type="primary"
    )
if accessibility_submitted:
    try:
        with session_scope() as session:
            save_accessibility_preferences(
                session,
                user_id,
                theme_options[selected_theme],
                high_contrast,
                text_scale_from_label(text_size),
                reduced_motion,
            )
        st.success("Preferências salvas.")
        st.rerun()
    except PreferenciasError as exc:
        st.warning(str(exc))
    except (SQLAlchemyError, RuntimeError):
        logger.exception("Falha ao salvar preferências de acessibilidade.")
        st.error("Não foi possível salvar suas preferências.")

st.divider()
st.subheader("Jornada de referência")
with st.form("schedule_form"):
    daily = st.number_input(
        "Horas diárias de referência",
        min_value=0.25,
        max_value=24.0,
        value=float(schedule.horas_diarias_referencia) if schedule else 8.0,
        step=0.25,
    )
    weekly = st.number_input(
        "Horas semanais de referência",
        min_value=0.25,
        max_value=168.0,
        value=float(schedule.horas_semanais_referencia) if schedule else 48.0,
        step=0.25,
        help="Para uma jornada de 8 horas por dia e uma folga semanal, a referência é 48 horas.",
    )
    col_start, col_end = st.columns(2)
    with col_start:
        start_time = st.time_input(
            "Entrada preferencial",
            value=schedule.horario_entrada_preferencial if schedule and schedule.horario_entrada_preferencial else time(9, 0),
        )
    with col_end:
        end_time = st.time_input(
            "Saída preferencial",
            value=schedule.horario_saida_preferencial if schedule and schedule.horario_saida_preferencial else time(18, 0),
        )
    breaks = st.number_input(
        "Quantidade de intervalos", min_value=0, max_value=10,
        value=schedule.quantidade_intervalos if schedule else 1, step=1,
    )
    timezone = st.text_input(
        "Fuso horário IANA",
        value=schedule.fuso_horario if schedule else "America/Sao_Paulo",
    )
    submitted = st.form_submit_button("Salvar jornada", type="primary")
if submitted:
    try:
        with session_scope() as session:
            save_schedule(
                session, user_id, Decimal(str(daily)), Decimal(str(weekly)),
                start_time, end_time, int(breaks), timezone,
            )
        st.success("Preferências salvas.")
    except JornadaError as exc:
        st.warning(str(exc))
    except (SQLAlchemyError, RuntimeError):
        logger.exception("Falha ao salvar configurações.")
        st.error("Não foi possível salvar suas preferências.")
