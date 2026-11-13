import logging

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from database.connection import session_scope
from services.admin_service import (
	USER_ROLES,
	AdminError,
	list_accounts,
	update_account_access,
)
from services.auth_service import AuthorizationError

logger = logging.getLogger(__name__)
admin_id, _ = require_user("admin")

st.title("Administração")
st.caption("Gerencie os acessos das contas da empresa.")

try:
	with session_scope() as session:
		accounts = list_accounts(session, admin_id)
except (AuthorizationError, SQLAlchemyError, RuntimeError):
	logger.exception("Falha ao carregar contas para administração.")
	st.error("Não foi possível carregar as contas.")
	st.stop()

st.dataframe(
	[
		{
			"Nome": account.nome,
			"E-mail": account.email,
			"Perfil": account.perfil,
			"Ativa": "Sim" if account.ativo else "Não",
		}
		for account in accounts
	],
	hide_index=True,
	width="stretch",
)

st.subheader("Acessos")
account_labels = {
	f"{account.nome} · {account.email}": account.id for account in accounts
}
selected_label = st.selectbox("Conta", list(account_labels))
selected_id = account_labels[selected_label]
selected_account = next(account for account in accounts if account.id == selected_id)

with st.form("account_access_form"):
	profile = st.selectbox(
		"Perfil",
		USER_ROLES,
		index=USER_ROLES.index(selected_account.perfil),
	)
	active = st.checkbox("Conta ativa", value=selected_account.ativo)
	submitted = st.form_submit_button("Salvar acesso", type="primary")

if submitted:
	try:
		with session_scope() as session:
			update_account_access(
				session, admin_id, selected_id, profile, active
			)
		st.success("Acesso atualizado.")
		st.rerun()
	except AdminError as exc:
		st.warning(str(exc))
	except (AuthorizationError, SQLAlchemyError, RuntimeError):
		logger.exception("Falha ao atualizar acesso da conta.")
		st.error("Não foi possível atualizar o acesso.")