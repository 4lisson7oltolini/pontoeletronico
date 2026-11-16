import logging
from datetime import datetime, time

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from database.connection import session_scope
from services.auth_service import AuthenticationError, AuthorizationError
from services.ponto_service import (
    PUNCH_SEQUENCE,
    effective_punch_times,
    list_adjustments,
    list_punches,
)
from services.solicitacao_service import (
    SolicitacaoError,
    create_correction_request,
    create_missing_punch_request,
    list_employee_requests_for_hr,
    list_user_requests,
)
from services.rh_service import employee_selection_context, get_hr_employee
from utils.datetime_utils import app_timezone, now_local

logger = logging.getLogger(__name__)
actor_id, _ = require_user()

st.title("Histórico de ponto")
try:
    with session_scope() as session:
        actor, employees = employee_selection_context(session, actor_id)
except (AuthenticationError, AuthorizationError):
    st.error("Sua conta não tem permissão para acessar este histórico.")
    st.stop()
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar funcionários para o histórico.")
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
        key="history_employee_id",
    )
    st.caption(f"Histórico de {employee_names[selected_user_id]} · somente leitura.")
else:
    selected_user_id = actor_id

today = now_local().date()
month_start = today.replace(day=1)
latest_past_date = today.fromordinal(today.toordinal() - 1)

try:
    with session_scope() as session:
        if read_only:
            get_hr_employee(session, actor_id, selected_user_id)
        punches = list_punches(session, selected_user_id)
        effective_times = effective_punch_times(session, selected_user_id, punches)
        adjustments = list_adjustments(session, selected_user_id)
        requests = (
            list_employee_requests_for_hr(session, actor_id, selected_user_id)
            if read_only
            else list_user_requests(session, actor_id)
        )

    if punches:
        frame = pd.DataFrame(
            [
                {
                    "Data efetiva": effective_times[punch.id].strftime("%d/%m/%Y"),
                    "Horário efetivo": effective_times[punch.id].strftime("%H:%M:%S"),
                    "Data original": punch.data_hora.strftime("%d/%m/%Y"),
                    "Marcação": punch.tipo_registro.replace("_", " ").title(),
                    "Origem": "Inclusão manual" if punch.origem == "ajuste_manual" else punch.origem,
                }
                for punch in punches
            ]
        )
        st.dataframe(frame, hide_index=True, width="stretch")
    else:
        st.info(
            "Este funcionário ainda não possui marcações."
            if read_only
            else "Você ainda não possui marcações."
        )

    if read_only:
        st.info("Este histórico está em modo somente leitura.")
    elif today > month_start:
        st.subheader("Adicionar marcação esquecida")
        st.caption(
            "Disponível para dias anteriores a hoje deste mês. "
            "Se já houver uma marcação do mesmo tipo, o pedido será tratado como correção. "
            "Toda alteração exige justificativa e aprovação do RH/admin."
        )
        with st.form("add_retroactive_punch"):
            missed_date = st.date_input(
                "Dia da marcação",
                value=latest_past_date,
                min_value=month_start,
                max_value=latest_past_date,
            )
            labels = {
                "entrada": "Entrada",
                "saida_intervalo": "Saída para intervalo",
                "retorno_intervalo": "Retorno do intervalo",
                "saida": "Saída final",
            }
            missed_type = st.selectbox(
                "Tipo de marcação",
                PUNCH_SEQUENCE,
                format_func=lambda kind: labels[kind],
            )
            missed_time = st.time_input("Horário da marcação", value=time(9, 0))
            missed_reason = st.text_area(
                "Justificativa", max_chars=1000, key="missed_punch_reason"
            )
            submitted = st.form_submit_button("Adicionar marcação esquecida", type="primary")
        if submitted:
            try:
                with session_scope() as session:
                    create_missing_punch_request(
                        session,
                        actor_id,
                        missed_date,
                        missed_type,
                        missed_time,
                        missed_reason,
                    )
                st.success("Pedido enviado para análise do RH.")
                st.rerun()
            except SolicitacaoError as exc:
                st.warning(str(exc))
            except (SQLAlchemyError, RuntimeError):
                logger.exception("Falha ao adicionar marcação retroativa.")
                st.error("Não foi possível adicionar a marcação.")
    else:
        st.info("No primeiro dia do mês ainda não existem dias anteriores deste mês para editar.")

    editable_punches = (
        [
            punch
            for punch in punches
            if month_start <= effective_times[punch.id].date() < today
        ]
        if not read_only
        else []
    )
    if editable_punches:
        st.subheader("Corrigir marcações anteriores")
        st.caption(
            "Correções preservam o horário original e exigem justificativa. "
            "Somente marcações deste mês, anteriores a hoje, podem ser alteradas."
        )
        for punch in editable_punches:
            effective_time = effective_times[punch.id]
            with st.expander(
                f"Corrigir — {effective_time:%d/%m/%Y %H:%M} "
                f"({punch.tipo_registro.replace('_', ' ')})"
            ):
                with st.form(f"adjust_{punch.id}"):
                    corrected_date = st.date_input(
                        "Nova data",
                        value=effective_time.date(),
                        min_value=month_start,
                        max_value=latest_past_date,
                        key=f"date_{punch.id}",
                    )
                    corrected_time = st.time_input(
                        "Novo horário",
                        value=effective_time.time().replace(tzinfo=None),
                        key=f"time_{punch.id}",
                    )
                    justification = st.text_area(
                        "Justificativa", max_chars=1000, key=f"reason_{punch.id}"
                    )
                    submitted = st.form_submit_button("Salvar correção")
                if submitted:
                    corrected_at = datetime.combine(
                        corrected_date, corrected_time, tzinfo=app_timezone()
                    )
                    try:
                        with session_scope() as session:
                            create_correction_request(
                                session,
                                actor_id,
                                punch.id,
                                corrected_at,
                                justification,
                            )
                        st.success("Pedido de correção enviado para análise do RH.")
                        st.rerun()
                    except SolicitacaoError as exc:
                        st.warning(str(exc))
                    except (SQLAlchemyError, RuntimeError):
                        logger.exception("Falha ao registrar ajuste de ponto.")
                        st.error("Não foi possível registrar a correção.")

    st.subheader("Pedidos de alteração")
    if requests:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Pedido": "Inclusão" if item.operacao == "inclusao" else "Correção",
                        "Marcação": item.tipo_registro.replace("_", " ").title(),
                        "Horário solicitado": item.horario_solicitado.strftime("%d/%m/%Y %H:%M"),
                        "Status": item.status.title(),
                        "Justificativa": item.justificativa,
                        "Observação do RH": item.observacao_decisao or "—",
                    }
                    for item in requests
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("Nenhum pedido de alteração enviado.")

    st.subheader("Histórico de alterações aprovadas")
    if adjustments:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Tipo": "Inclusão" if item.operacao == "inclusao" else "Correção",
                        "Registro": item.registro_ponto_id,
                        "Horário anterior": (
                            "—"
                            if item.operacao == "inclusao"
                            else item.horario_original.strftime("%d/%m/%Y %H:%M")
                        ),
                        "Horário efetivo": item.horario_corrigido.strftime("%d/%m/%Y %H:%M"),
                        "Justificativa": item.justificativa,
                        "Alterado em": item.criado_em.strftime("%d/%m/%Y %H:%M"),
                    }
                    for item in adjustments
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("Nenhuma alteração registrada.")
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar histórico.")
    st.error("Não foi possível carregar seu histórico.")
except (AuthenticationError, AuthorizationError) as exc:
    st.error(str(exc))
    st.stop()
