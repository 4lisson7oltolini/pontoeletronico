import logging

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from components.cards import metric_card
from components.sidebar import render_sidebar
from database.connection import session_scope
from services.dashboard_service import dashboard_summary
from utils.datetime_utils import now_local

logger = logging.getLogger(__name__)
user_id, user_name = require_user()
render_sidebar(user_name)

st.title("Dashboard")
st.caption("Resumo pessoal da sua jornada neste mês.")
try:
    with session_scope() as session:
        summary = dashboard_summary(session, user_id, now_local().date())
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar o painel.")
    st.error("Não foi possível carregar seu resumo.")
    st.stop()

with st.container(horizontal=True):
    metric_card("Horas trabalhadas no mês", "—", "O cálculo de jornada será implementado em etapa futura.")
    metric_card("Dias trabalhados", str(summary["working_days"]))
    latest = summary["latest_punch"]
    latest_label = (
        f"{latest.tipo_registro.replace('_', ' ').title()} · "
        f"{latest.data_hora:%d/%m %H:%M}"
        if latest
        else "—"
    )
    metric_card("Último registro", latest_label)
with st.container(horizontal=True):
    metric_card("Folgas planejadas", str(summary["planned_days_off"]))
    metric_card("Folgas realizadas", str(summary["completed_days_off"]))

st.subheader("Sua jornada")
schedule = summary["schedule"]
if schedule:
    st.info(
        f"{schedule.horas_diarias_referencia:g} h/dia · "
        f"{schedule.horas_semanais_referencia:g} h/semana · "
        f"{schedule.quantidade_intervalos} intervalo(s) · "
        f"Fuso {schedule.fuso_horario}"
    )
else:
    st.info("Configure sua jornada de referência nas Configurações.")
