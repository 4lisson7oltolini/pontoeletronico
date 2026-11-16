from datetime import date, datetime, time

import pytest
from sqlalchemy import select

from database.models import Notificacao
from services.auth_service import register_admin_user, register_user
from services.notificacao_service import (
    NotificacaoError,
    count_unread_notifications,
    list_notifications,
    mark_notification_read,
)
from services.solicitacao_service import create_missing_punch_request, decide_request

TODAY = datetime(2026, 11, 11, 12, 0)


def _rh_user(session):
    user = register_user(session, "Pessoa RH", "rh@example.com", "senha-rh-segura-123")
    user.perfil = "rh"
    session.commit()
    return user


def test_request_and_decision_notify_relevant_accounts(session, monkeypatch):
    monkeypatch.setattr("services.solicitacao_service.now_local", lambda: TODAY)
    employee = register_user(
        session, "Funcionária", "func@example.com", "senha-func-segura-123"
    )
    reviewer = _rh_user(session)
    admin = register_admin_user(
        session, "Admin", "admin@example.com", "senha-admin-segura-123"
    )
    request = create_missing_punch_request(
        session,
        employee.id,
        date(2026, 11, 10),
        "entrada",
        time(9),
        "Esqueci de registrar a entrada.",
    )

    pending = list(session.scalars(select(Notificacao)))
    assert {item.usuario_id for item in pending} == {reviewer.id, admin.id}
    assert all(item.tipo == "solicitacao_pendente" for item in pending)
    assert count_unread_notifications(session, reviewer.id) == 1

    decide_request(
        session,
        reviewer.id,
        request.id,
        approve=True,
        decision_note="Conferido.",
    )

    employee_notifications = list_notifications(session, employee.id)
    assert len(employee_notifications) == 1
    assert employee_notifications[0].tipo == "solicitacao_decidida"
    assert "aprovou" in employee_notifications[0].mensagem


def test_notification_read_is_scoped_to_recipient(session):
    employee = register_user(
        session, "Funcionária", "func@example.com", "senha-func-segura-123"
    )
    other_employee = register_user(
        session, "Outra pessoa", "outra@example.com", "senha-outra-segura-123"
    )
    notification = Notificacao(
        usuario_id=employee.id,
        tipo="solicitacao_decidida",
        titulo="Pedido analisado",
        mensagem="Sua solicitação foi aprovada.",
        criada_em=TODAY,
    )
    session.add(notification)
    session.commit()

    with pytest.raises(NotificacaoError, match="não encontrada"):
        mark_notification_read(session, other_employee.id, notification.id)

    mark_notification_read(session, employee.id, notification.id)

    assert count_unread_notifications(session, employee.id) == 0
