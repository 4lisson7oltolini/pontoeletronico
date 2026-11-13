import logging

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from database.connection import session_scope
from services.relatorio_service import (
    build_monthly_report,
    export_monthly_report_xlsx,
)
from utils.datetime_utils import now_local

logger = logging.getLogger(__name__)
user_id, user_name = require_user()

st.title("Relatórios mensais")
today = now_local().date()
with st.form("monthly_report_form"):
    selected_month = st.date_input(
        "Selecione um mês",
        value=today.replace(day=1),
        max_value=today,
        help="O relatório do mês atual considera os dias até hoje.",
    )
    generate_report = st.form_submit_button(
        "Gerar ou atualizar relatório", type="primary"
    )

report_key = (user_id, selected_month.year, selected_month.month)
if generate_report:
    try:
        with session_scope() as session:
            report = build_monthly_report(
                session,
                user_id,
                selected_month.year,
                selected_month.month,
                as_of=today,
            )
        workbook = export_monthly_report_xlsx(report, user_name)
        st.session_state["monthly_report_result"] = {
            "key": report_key,
            "report": report,
            "workbook": workbook,
        }
    except (ValueError, SQLAlchemyError, RuntimeError) as exc:
        st.session_state.pop("monthly_report_result", None)
        if isinstance(exc, ValueError):
            st.warning(str(exc))
        else:
            logger.exception("Falha ao gerar relatório mensal.")
            st.error("Não foi possível gerar o relatório. Tente novamente.")

result = st.session_state.get("monthly_report_result")
if not result or result["key"] != report_key:
    st.caption("Selecione o período e gere o relatório para consultar os resultados.")
    st.stop()

report = result["report"]
summary = report["summary"]
st.caption(
    f"Jornada de {report['daily_hours']:g} h por dia · "
    f"{report['weekly_hours']:g} h semanais · "
    "semana de segunda a domingo. O período de intervalo conta como jornada."
)
if report["weekly_hours"] != report["daily_hours"] * 6:
    st.caption(
        "As horas extras semanais usam a carga semanal configurada em Configurações. "
        "Para 8 horas por dia e uma folga semanal, a referência recomendada é 48 horas."
    )

with st.container(horizontal=True):
    st.metric("Horas trabalhadas", f"{summary['worked_hours']:.2f} h", border=True)
    st.metric("Horas previstas", f"{summary['expected_hours']:.2f} h", border=True)
    st.metric("Saldo do período", f"{summary['balance']:+.2f} h", border=True)
with st.container(horizontal=True):
    st.metric("Horas extras diárias", f"{summary['daily_overtime']:.2f} h", border=True)
    st.metric(
        "Horas extras semanais adicionais",
        f"{summary['weekly_overtime']:.2f} h",
        help="Horas acima da referência semanal, sem repetir horas já contadas como extra diária.",
        border=True,
    )
    st.metric("Total de horas extras", f"{summary['total_overtime']:.2f} h", border=True)
st.caption(
    f"{summary['days_worked']} dia(s) completo(s) · "
    f"{summary['scheduled_days']} dia(s) previsto(s) · "
    f"{summary['incomplete_days']} dia(s) incompleto(s)"
)
st.info(
    "O intervalo entre entrada e saída final é contado como jornada, conforme sua regra. "
    "Turnos que passam da meia-noite são atribuídos à data da entrada."
)
if summary["incomplete_days"]:
    st.warning(
        "Dias com marcações incompletas são sinalizados, mas suas horas não entram nos totais."
    )

st.subheader("Resumo semanal")
weekly_frame = pd.DataFrame(
    [
        {
            "Semana": f"{row.week_start:%d/%m/%Y} – {row.week_end:%d/%m/%Y}",
            "Dias previstos": row.scheduled_days,
            "Horas previstas": f"{row.expected_hours:.2f}",
            "Horas trabalhadas": f"{row.worked_hours:.2f}",
            "Extra diária": f"{row.daily_overtime:.2f}",
            "Extra semanal adicional": f"{row.weekly_overtime:.2f}",
            "Total de extras": f"{row.total_overtime:.2f}",
        }
        for row in report["weekly_rows"]
    ]
)
if not weekly_frame.empty:
    st.dataframe(weekly_frame, hide_index=True, width="stretch")
else:
    st.info("Não há semanas neste período.")

st.subheader("Detalhamento diário")
labels = {
    "entrada": "Entrada",
    "saida_intervalo": "Saída intervalo",
    "retorno_intervalo": "Retorno intervalo",
    "saida": "Saída final",
}
daily_frame = pd.DataFrame(
    [
        {
            "Data de trabalho": row.day.strftime("%d/%m/%Y"),
            "Status": row.status,
            **{
                labels[kind]: (
                    row.punches[kind].strftime("%d/%m %H:%M")
                    if kind in row.punches
                    else "—"
                )
                for kind in labels
            },
            "Horas trabalhadas": f"{row.worked_hours:.2f}",
            "Horas previstas": f"{row.expected_hours:.2f}",
            "Extra diária": f"{row.daily_overtime:.2f}",
            "Extra semanal adicional": f"{row.weekly_overtime:.2f}",
            "Total de extras": f"{row.overtime:.2f}",
            "Saldo do dia": f"{row.balance:+.2f}",
        }
        for row in report["daily_rows"]
    ]
)
if not daily_frame.empty:
    st.dataframe(daily_frame, hide_index=True, width="stretch")
else:
    st.info("Não há dias para exibir neste período.")

st.subheader("Histórico de ajustes")
if report["adjustments"]:
    adjustments_frame = pd.DataFrame(
        [
            {
                "Operação": "Inclusão" if item.operacao == "inclusao" else "Correção",
                "Registro": item.registro_ponto_id,
                "Horário original": (
                    "—"
                    if item.operacao == "inclusao"
                    else item.horario_original.strftime("%d/%m/%Y %H:%M")
                ),
                "Horário efetivo": item.horario_corrigido.strftime("%d/%m/%Y %H:%M"),
                "Justificativa": item.justificativa,
                "Alterado em": item.criado_em.strftime("%d/%m/%Y %H:%M"),
            }
            for item in report["adjustments"]
        ]
    )
    st.dataframe(adjustments_frame, hide_index=True, width="stretch")
else:
    st.caption("Nenhum ajuste registrado neste período.")

st.download_button(
    "Baixar relatório Excel",
    data=result["workbook"],
    file_name=f"ponto-facil-{user_id}-{selected_month:%Y-%m}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
    width="stretch",
)
