import logging
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from components.sidebar import render_sidebar
from database.connection import session_scope
from services.relatorio_service import monthly_punches
from utils.datetime_utils import now_local

logger = logging.getLogger(__name__)
user_id, user_name = require_user()
render_sidebar(user_name)

st.title("Relatórios mensais")
today = now_local().date()
selected_month = st.date_input("Selecione um mês", value=today.replace(day=1))
st.info("A exportação Excel e os cálculos completos serão disponibilizados em uma próxima etapa.")
if st.button("Consultar marcações do mês"):
    try:
        with session_scope() as session:
            punches = monthly_punches(session, user_id, selected_month.year, selected_month.month)
        st.write(f"{len(punches)} marcação(ões) no período.")
    except (ValueError, SQLAlchemyError, RuntimeError) as exc:
        if isinstance(exc, ValueError):
            st.warning(str(exc))
        else:
            logger.exception("Falha ao consultar dados do relatório.")
            st.error("Não foi possível consultar os registros do período.")
