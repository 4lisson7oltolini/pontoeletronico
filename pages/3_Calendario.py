import logging
from datetime import date

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from components.calendario import month_bounds, show_days_off
from database.connection import session_scope
from services.auth_service import AuthenticationError, AuthorizationError
from services.folga_service import FolgaError, list_days_off, plan_day_off, update_day_off
from services.rh_service import employee_selection_context, get_hr_employee
from utils.datetime_utils import now_local

logger = logging.getLogger(__name__)
user_id, _ = require_user()

st.title("Calendário e folgas")

try:
    with session_scope() as session:
        actor, employees = employee_selection_context(session, user_id)
except (AuthenticationError, AuthorizationError):
    st.error("Sua conta não tem permissão para acessar este calendário.")
    st.stop()
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar funcionários para o calendário.")
    st.error("Não foi possível carregar os funcionários.")
    st.stop()

read_only = actor.perfil in {"rh", "admin"}
if read_only:
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
        key="calendar_employee_id",
    )
    st.caption(f"Calendário de {employee_names[selected_user_id]} · somente leitura.")
else:
    selected_user_id = user_id

selected_day = st.date_input("Selecione uma data", value=now_local().date())
if not read_only:
    observation = st.text_input("Observação (opcional)", max_chars=500)
    if st.button("Marcar como folga planejada", type="primary"):
        try:
            with session_scope() as session:
                plan_day_off(session, selected_user_id, selected_day, observation)
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
        if read_only:
            get_hr_employee(session, user_id, selected_user_id)
        days_off = list_days_off(session, selected_user_id, start, end)
    show_days_off(days_off)
    if not read_only:
        planned = [day_off for day_off in days_off if day_off.status == "planejada"]
        if planned:
            options = {
                f"{item.data:%d/%m/%Y} — {item.observacao or 'Sem observação'}": item.id
                for item in planned
            }
            selected_label = st.selectbox("Atualizar uma folga planejada", list(options))
            action = st.selectbox("Ação", ["Confirmar como realizada", "Cancelar folga"])
            if st.button("Salvar alteração"):
                new_status = (
                    "realizada" if action.startswith("Confirmar") else "cancelada"
                )
                with session_scope() as session:
                    update_day_off(
                        session, selected_user_id, options[selected_label], new_status
                    )
                st.success("Status da folga atualizado.")
                st.rerun()
except FolgaError as exc:
    st.warning(str(exc))
except AuthorizationError as exc:
    st.error(str(exc))
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar calendário.")
    st.error("Não foi possível carregar suas folgas.")
