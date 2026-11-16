import logging

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from components.cards import metric_card
from database.connection import session_scope
from services.auth_service import (
    AuthenticationError,
    AuthorizationError,
)
from services.dashboard_service import (
    dashboard_context,
    dashboard_summary_for_actor,
)
from utils.datetime_utils import now_local

logger = logging.getLogger(__name__)
user_id, _ = require_user()

st.title("Dashboard")

try:
    with session_scope() as session:
            user_role, employees = dashboard_context(session, user_id)
except (AuthenticationError, AuthorizationError):
    st.error("Sua conta não tem permissão para consultar este dashboard.")
    st.stop()
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar funcionários para o dashboard.")
    st.error("Não foi possível carregar os funcionários.")
    st.stop()

if user_role in {"rh", "admin"}:
    if not employees:
        st.info("Ainda não há funcionários cadastrados.")
        st.stop()
    employee_names = {employee.id: employee.nome for employee in employees}
    employee_labels = {
        employee.id: f"{employee.nome} · {employee.email}" for employee in employees
    }
    selected_user_id = st.selectbox(
        "Funcionário",
        options=list(employee_names),
        format_func=employee_labels.__getitem__,
        key="dashboard_employee_id",
    )
    selected_employee_name = employee_names[selected_user_id]
    st.caption(f"Resumo da jornada de {selected_employee_name} neste mês.")
else:
    selected_user_id = user_id
    selected_employee_name = ""
    st.caption("Resumo pessoal da sua jornada neste mês.")

try:
    with session_scope() as session:
        summary = dashboard_summary_for_actor(
            session, user_id, selected_user_id, now_local().date()
        )
except AuthorizationError as exc:
    st.error(str(exc))
    st.stop()
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar o painel.")
    st.error("Não foi possível carregar seu resumo.")
    st.stop()

with st.container(horizontal=True):
    metric_card("Horas trabalhadas no mês", f"{summary['monthly_worked_hours']:.2f} h")
    metric_card("Dias trabalhados", str(summary["working_days"]))
    latest = summary["latest_punch"]
    latest_label = (
        f"{latest.tipo_registro.replace('_', ' ').title()} · "
        f"{summary['latest_punch_time']:%d/%m %H:%M}"
        if latest
        else "—"
    )
    metric_card("Último registro", latest_label)
with st.container(horizontal=True):
    metric_card("Folgas planejadas", str(summary["planned_days_off"]))
    metric_card("Folgas realizadas", str(summary["completed_days_off"]))
    metric_card("Horas extras no mês", f"{summary['monthly_overtime']:.2f} h")

st.subheader(
    f"Jornada de {selected_employee_name}"
    if selected_employee_name
    else "Sua jornada"
)
schedule = summary["schedule"]
if schedule:
    st.info(
        f"{schedule.horas_diarias_referencia:g} h/dia · "
        f"{schedule.horas_semanais_referencia:g} h/semana · "
        f"{schedule.quantidade_intervalos} intervalo(s) · "
        f"Fuso {schedule.fuso_horario}"
    )
else:
    st.info(
        "Este funcionário ainda não configurou a jornada de referência."
        if selected_employee_name
        else "Configure sua jornada de referência nas Configurações."
    )
if summary["incomplete_days"]:
    st.warning(
        f"{summary['incomplete_days']} dia(s) com marcações incompletas não entraram nas horas trabalhadas."
    )
