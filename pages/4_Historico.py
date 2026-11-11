import logging
from datetime import datetime

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from components.sidebar import render_sidebar
from database.connection import session_scope
from services.ponto_service import PontoError, correct_punch, list_adjustments, list_punches
from utils.datetime_utils import app_timezone

logger = logging.getLogger(__name__)
user_id, user_name = require_user()
render_sidebar(user_name)

st.title("Histórico de ponto")
try:
    with session_scope() as session:
        punches = list_punches(session, user_id)
        adjustments = list_adjustments(session, user_id)
    if punches:
        frame = pd.DataFrame(
            [
                {
                    "Data": punch.data_hora.strftime("%d/%m/%Y"),
                    "Horário": punch.data_hora.strftime("%H:%M:%S"),
                    "Marcação": punch.tipo_registro.replace("_", " ").title(),
                    "Origem": punch.origem,
                }
                for punch in punches
            ]
        )
        st.dataframe(frame, hide_index=True, width="stretch")
        for punch in punches:
            with st.expander(
                f"Solicitar ajuste — {punch.data_hora:%d/%m/%Y %H:%M} "
                f"({punch.tipo_registro.replace('_', ' ')})"
            ):
                with st.form(f"adjust_{punch.id}"):
                    corrected_date = st.date_input(
                        "Data corrigida", value=punch.data_hora.date(), key=f"date_{punch.id}"
                    )
                    corrected_time = st.time_input(
                        "Horário corrigido",
                        value=punch.data_hora.time().replace(tzinfo=None),
                        key=f"time_{punch.id}",
                    )
                    justification = st.text_area(
                        "Justificativa", max_chars=1000, key=f"reason_{punch.id}"
                    )
                    submitted = st.form_submit_button("Registrar ajuste")
                if submitted:
                    corrected_at = datetime.combine(
                        corrected_date, corrected_time, tzinfo=app_timezone()
                    )
                    try:
                        with session_scope() as session:
                            correct_punch(
                                session, user_id, punch.id, corrected_at, justification
                            )
                        st.success("Ajuste registrado. A marcação original foi preservada.")
                        st.rerun()
                    except PontoError as exc:
                        st.warning(str(exc))
                    except (SQLAlchemyError, RuntimeError):
                        logger.exception("Falha ao registrar ajuste de ponto.")
                        st.error("Não foi possível registrar o ajuste.")
    else:
        st.info("Você ainda não possui marcações.")
    st.subheader("Histórico de ajustes")
    if adjustments:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Registro": item.registro_ponto_id,
                        "Original": item.horario_original.strftime("%d/%m/%Y %H:%M"),
                        "Corrigido": item.horario_corrigido.strftime("%d/%m/%Y %H:%M"),
                        "Justificativa": item.justificativa,
                        "Ajustado em": item.criado_em.strftime("%d/%m/%Y %H:%M"),
                    }
                    for item in adjustments
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("Nenhum ajuste registrado.")
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar histórico.")
    st.error("Não foi possível carregar seu histórico.")
