import logging
from decimal import Decimal
from datetime import time

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from components.sidebar import render_sidebar
from database.connection import session_scope
from services.jornada_service import JornadaError, get_schedule, save_schedule

logger = logging.getLogger(__name__)
user_id, user_name = require_user()
render_sidebar(user_name)

st.title("Configurações pessoais")
try:
    with session_scope() as session:
        schedule = get_schedule(session, user_id)
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar configurações.")
    st.error("Não foi possível carregar suas configurações.")
    st.stop()

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
        value=float(schedule.horas_semanais_referencia) if schedule else 40.0,
        step=0.25,
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
