import json
import logging

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from components.auth import require_user
from database.connection import session_scope
from services.audit_service import (
    AUDIT_EXPORT_LIMIT,
    export_audit_events_xlsx,
    list_audit_events,
)
from services.auth_service import AuthenticationError, AuthorizationError
from utils.datetime_utils import now_local

logger = logging.getLogger(__name__)
viewer_id, _ = require_user("admin", "rh")

st.title("Trilha de auditoria")
today = now_local().date()
start_col, end_col = st.columns(2)
with start_col:
    start_date = st.date_input(
        "De",
        value=today.replace(day=1),
        max_value=today,
        key="audit_start_date",
    )
with end_col:
    end_date = st.date_input(
        "Até",
        value=today,
        max_value=today,
        key="audit_end_date",
    )

if start_date > end_date:
    st.error("A data inicial não pode ser posterior à data final.")
    st.stop()

try:
    with session_scope() as session:
        audit_rows = list_audit_events(
            session, viewer_id, start_date=start_date, end_date=end_date
        )
except (AuthenticationError, AuthorizationError) as exc:
    st.error(str(exc))
    st.stop()
except (SQLAlchemyError, RuntimeError):
    logger.exception("Falha ao carregar a trilha de auditoria.")
    st.error("Não foi possível carregar a trilha de auditoria.")
    st.stop()

st.caption(
    f"Exibindo até {AUDIT_EXPORT_LIMIT:,} eventos, sem registrar senhas ou "
    "o conteúdo digitado nos campos de senha."
)
if audit_rows:
    display_rows = [
        {
            "Data/hora": row["criado_em"].strftime("%d/%m/%Y %H:%M:%S"),
            "Ação": row["acao"],
            "Autor": row["ator"],
            "Alvo": row["alvo"],
            "Entidade": row["entidade"],
            "ID": row["entidade_id"],
            "Detalhes": json.dumps(
                row["detalhes"], ensure_ascii=False, sort_keys=True
            ),
        }
        for row in audit_rows
    ]
    st.dataframe(pd.DataFrame(display_rows), hide_index=True, width="stretch")
    st.download_button(
        "Exportar Excel",
        data=export_audit_events_xlsx(audit_rows),
        file_name=f"auditoria-{start_date:%Y%m%d}-{end_date:%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        width="stretch",
    )
else:
    st.info("Nenhum evento foi registrado neste período.")
