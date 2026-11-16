"""Append-only audit events and authorized export operations."""

import json
from datetime import date, datetime, time, timedelta
from io import BytesIO
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from database.models import EventoAuditoria, Usuario
from utils.datetime_utils import app_timezone, now_local

AUDIT_EXPORT_LIMIT = 5000


def record_audit_event(
    session: Session,
    action: str,
    *,
    actor_id: int | None = None,
    target_id: int | None = None,
    entity: str | None = None,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> EventoAuditoria:
    event = EventoAuditoria(
        ator_usuario_id=actor_id,
        alvo_usuario_id=target_id,
        acao=action,
        entidade=entity,
        entidade_id=entity_id,
        detalhes=details or {},
        criado_em=now_local(),
    )
    session.add(event)
    return event


def list_audit_events(
    session: Session,
    viewer_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    from services.auth_service import assert_user_role, get_active_user

    viewer = get_active_user(session, viewer_id)
    assert_user_role(viewer, ("admin", "rh"))

    actor = aliased(Usuario)
    target = aliased(Usuario)
    statement = (
        select(EventoAuditoria, actor.nome, target.nome)
        .outerjoin(actor, actor.id == EventoAuditoria.ator_usuario_id)
        .outerjoin(target, target.id == EventoAuditoria.alvo_usuario_id)
        .order_by(EventoAuditoria.criado_em.desc(), EventoAuditoria.id.desc())
        .limit(AUDIT_EXPORT_LIMIT)
    )
    if start_date is not None:
        start_at = datetime.combine(
            start_date, time.min, tzinfo=app_timezone()
        )
        statement = statement.where(EventoAuditoria.criado_em >= start_at)
    if end_date is not None:
        end_at = datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=app_timezone()
        )
        statement = statement.where(EventoAuditoria.criado_em < end_at)

    rows = session.execute(statement)
    return [
        {
            "id": event.id,
            "criado_em": event.criado_em,
            "acao": event.acao,
            "ator": actor_name or "Sistema/conta removida",
            "alvo": target_name or "—",
            "entidade": event.entidade or "—",
            "entidade_id": event.entidade_id,
            "detalhes": event.detalhes,
        }
        for event, actor_name, target_name in rows
    ]


def export_audit_events_xlsx(rows: list[dict[str, Any]]) -> bytes:
    def safe_text(value: str) -> str:
        if value.startswith(("=", "+", "-", "@", "\t", "\r")):
            return f"'{value}"
        return value

    frame = pd.DataFrame(
        [
            {
                "ID": row["id"],
                "Data/hora": _format_local_time(row["criado_em"]),
                "Ação": safe_text(row["acao"]),
                "Autor": safe_text(row["ator"]),
                "Alvo": safe_text(row["alvo"]),
                "Entidade": safe_text(row["entidade"]),
                "ID da entidade": row["entidade_id"],
                "Detalhes": safe_text(
                    json.dumps(row["detalhes"], ensure_ascii=False, sort_keys=True)
                ),
            }
            for row in rows
        ],
        columns=[
            "ID",
            "Data/hora",
            "Ação",
            "Autor",
            "Alvo",
            "Entidade",
            "ID da entidade",
            "Detalhes",
        ],
    )
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Auditoria", index=False)
    return output.getvalue()


def _format_local_time(value: datetime) -> str:
    local_value = (
        value.replace(tzinfo=app_timezone())
        if value.tzinfo is None or value.utcoffset() is None
        else value.astimezone(app_timezone())
    )
    return local_value.strftime("%d/%m/%Y %H:%M:%S")
