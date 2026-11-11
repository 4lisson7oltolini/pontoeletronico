import logging

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from components.sidebar import render_sidebar
from database.connection import session_scope
from services.ponto_service import PUNCH_SEQUENCE, PontoError, register_punch

logger = logging.getLogger(__name__)
user_id, user_name = require_user()
render_sidebar(user_name)

st.title("Registrar ponto")
st.write("As marcações usam o horário do servidor no fuso configurado. Registros não são sobrescritos.")

labels = {
    "entrada": "Entrada",
    "saida_intervalo": "Saída para intervalo",
    "retorno_intervalo": "Retorno do intervalo",
    "saida": "Saída final",
}
for punch_type in PUNCH_SEQUENCE:
    if st.button(
        labels[punch_type], key=f"punch_{punch_type}", type="primary", width="stretch"
    ):
        try:
            with session_scope() as session:
                punch = register_punch(session, user_id, punch_type)
            st.success(f"{labels[punch_type]} registrada às {punch.data_hora:%H:%M:%S}.")
        except PontoError as exc:
            st.warning(str(exc))
        except (SQLAlchemyError, RuntimeError):
            logger.exception("Falha ao registrar marcação.")
            st.error("Não foi possível registrar o ponto. Tente novamente.")
