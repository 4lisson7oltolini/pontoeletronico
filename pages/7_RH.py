from io import BytesIO
import logging

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from database.connection import session_scope
from services.auth_service import AuthorizationError
from services.rh_service import get_hr_overview
from services.solicitacao_service import (
	SolicitacaoError,
	decide_request,
	list_pending_requests,
)

logger = logging.getLogger(__name__)
reviewer_id, _ = require_user("admin", "rh")

st.title("Gestão de RH")
try:
	with session_scope() as session:
		employees, schedule_rows, punch_rows = get_hr_overview(session, reviewer_id)
		pending_requests = list_pending_requests(session, reviewer_id)
except (AuthorizationError, SQLAlchemyError, RuntimeError):
	logger.exception("Falha ao carregar dados de RH.")
	st.error("Não foi possível carregar os dados de RH.")
	st.stop()

st.subheader("Jornadas da equipe")
if employees:
	schedule_frame = pd.DataFrame(schedule_rows)
	schedule_display = schedule_frame[
		[
			"Funcionário",
			"Horas diárias",
			"Horas semanais",
			"Entrada prevista",
			"Saída prevista",
			"Intervalos",
		]
	]
	st.dataframe(schedule_display, hide_index=True, width="stretch")
	output = BytesIO()
	with pd.ExcelWriter(output, engine="openpyxl") as writer:
		schedule_frame.to_excel(writer, sheet_name="Jornadas", index=False)
	st.download_button(
		"Baixar planilha de jornadas",
		data=output.getvalue(),
		file_name="jornadas_funcionarios.xlsx",
		mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		icon=":material/download:",
	)
else:
	st.info("Ainda não há funcionários cadastrados.")

st.subheader("Marcações dos funcionários")
if punch_rows:
	st.dataframe(pd.DataFrame(punch_rows), hide_index=True, width="stretch")
else:
	st.info("Nenhuma marcação encontrada.")

st.subheader("Pedidos pendentes")
if pending_requests:
	for request, employee_name, employee_email in pending_requests:
		operation = "Inclusão esquecida" if request.operacao == "inclusao" else "Correção"
		with st.expander(
			f"{employee_name} · {operation} · "
			f"{request.horario_solicitado:%d/%m/%Y %H:%M}"
		):
			st.caption(employee_email)
			st.write(f"Marcação: {request.tipo_registro.replace('_', ' ').title()}")
			st.write(f"Justificativa: {request.justificativa}")
			with st.form(f"review_request_{request.id}"):
				decision = st.radio(
					"Decisão", ("Aprovar", "Rejeitar"), horizontal=True
				)
				note = st.text_area("Observação da decisão", max_chars=1000)
				submitted = st.form_submit_button("Registrar decisão", type="primary")
			if submitted:
				try:
					with session_scope() as session:
						decide_request(
							session,
							reviewer_id,
							request.id,
							approve=decision == "Aprovar",
							decision_note=note,
						)
					st.success("Decisão registrada.")
					st.rerun()
				except SolicitacaoError as exc:
					st.warning(str(exc))
				except (AuthorizationError, SQLAlchemyError, RuntimeError):
					logger.exception("Falha ao decidir solicitação.")
					st.error("Não foi possível registrar a decisão.")
else:
	st.caption("Nenhum pedido aguardando análise.")