import logging
from datetime import date

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from components.calendario import month_bounds, show_days_off
from components.sidebar import render_sidebar
from database.connection import session_scope
from services.folga_service import FolgaError, list_days_off, plan_day_off, update_day_off
from utils.datetime_utils import now_local

logger = logging.getLogger(__name__)
user_id, user_name = require_user()
render_sidebar(user_name)

st.title("Calendário e folgas")
selected_day = st.date_input("Selecione uma data", value=now_local().date())
observation = st.text_input("Observação (opcional)", max_chars=500)
if st.button("Marcar como folga planejada", type="primary"):
    try:
        with session_scope() as session:
            plan_day_off(session, user_id, selected_day, observation)
        st.success(f"Folga de {selected_day:%d/%m/%Y} planejada.")
        st.rerun()
    except FolgaError as exc:
        st.warning(str(exc))
    except (SQLAlchemyError, RuntimeError):
        logger.exception("Falha ao planejar folga.")
        st.error("Não foi possível planejar a folga.")

st.subheader(f"Folgas de {selected_day:%m/%Y}")
start, end = month_bounds(selected_day)
try:
    with session_scope() as session:
        days_off = list_days_off(session, user_id, start, end)
    show_days_off(days_off)
    planned = [day_off for day_off in days_off if day_off.status == "planejada"]
    if planned:
        options = {f"{item.data:%d/%m/%Y} — {item.observacao or 'Sem observação'}": item.id for item in planned}
        selected_label = st.selectbox("Atualizar uma folga planejada", list(options))
        action = st.selectbox("Ação", ["Confirmar como realizada", "Cancelar folga"])
        if st.button("Salvar alteração"):
            new_status = "realizada" if action.startswith("Confirmar") else "cancelada"
            with session_scope() as session:
                update_day_off(session, user_id, options[selected_label], new_status)
            st.success("Status da folga atualizado.")
            st.rerun()
except FolgaError as exc:
    st.warning(str(exc))
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar calendário.")
    st.error("Não foi possível carregar suas folgas.")
