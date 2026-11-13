from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from database.models import RegistroPonto
from services.auth_service import AuthorizationError, register_admin_user, register_user
from services.ponto_service import effective_punch_times, list_punches
from services.solicitacao_service import (
    SolicitacaoError,
    create_correction_request,
    create_missing_punch_request,
    decide_request,
    list_pending_requests,
    list_user_requests,
)

LOCAL = ZoneInfo("America/Sao_Paulo")
TODAY = datetime(2026, 11, 11, 12, 0, tzinfo=LOCAL)


def _freeze_today(monkeypatch):
    monkeypatch.setattr("services.solicitacao_service.now_local", lambda: TODAY)
    monkeypatch.setattr("services.ponto_service.now_local", lambda: TODAY)


def _rh_user(session):
    reviewer = register_user(
        session, "Pessoa RH", "rh@example.com", "senha-rh-segura-123"
    )
    reviewer.perfil = "rh"
    session.commit()
    return reviewer


def test_missing_punch_waits_for_hr_approval(session, monkeypatch):
    _freeze_today(monkeypatch)
    employee = register_user(
        session, "Funcionária", "func@example.com", "senha-func-segura-123"
    )
    reviewer = _rh_user(session)

    request = create_missing_punch_request(
        session,
        employee.id,
        date(2026, 11, 10),
        "entrada",
        time(9),
        "Esqueci de registrar a entrada.",
    )

    assert request.status == "pendente"
    assert list_punches(session, employee.id) == []
    assert len(list_pending_requests(session, reviewer.id)) == 1
    assert len(list_user_requests(session, employee.id)) == 1

    decided = decide_request(
        session,
        reviewer.id,
        request.id,
        approve=True,
        decision_note="Conferido com a folha de presença.",
    )

    assert decided.status == "aprovada"
    assert decided.decidido_por_id == reviewer.id
    punches = list_punches(session, employee.id)
    assert len(punches) == 1
    assert punches[0].tipo_registro == "entrada"
    assert punches[0].origem == "ajuste_manual"


def test_employee_cannot_decide_requests(session, monkeypatch):
    _freeze_today(monkeypatch)
    employee = register_user(
        session, "Funcionária", "func@example.com", "senha-func-segura-123"
    )
    request = create_missing_punch_request(
        session,
        employee.id,
        date(2026, 11, 10),
        "entrada",
        time(9),
        "Esqueci de registrar.",
    )

    with pytest.raises(AuthorizationError):
        decide_request(
            session,
            employee.id,
            request.id,
            approve=True,
            decision_note="Autodecisão",
        )

    assert list_punches(session, employee.id) == []


def test_hr_cannot_decide_own_request(session, monkeypatch):
    _freeze_today(monkeypatch)
    reviewer = _rh_user(session)
    request = create_missing_punch_request(
        session,
        reviewer.id,
        date(2026, 11, 10),
        "entrada",
        time(9),
        "Esqueci de registrar.",
    )

    with pytest.raises(SolicitacaoError, match="próprio pedido"):
        decide_request(
            session,
            reviewer.id,
            request.id,
            approve=True,
            decision_note="Autodecisão",
        )


def test_correction_is_applied_only_after_approval(session, monkeypatch):
    _freeze_today(monkeypatch)
    employee = register_user(
        session, "Funcionária", "func@example.com", "senha-func-segura-123"
    )
    reviewer = register_admin_user(
        session, "Admin", "admin@example.com", "senha-admin-segura-123"
    )
    original = datetime(2026, 11, 10, 9, 0, tzinfo=LOCAL)
    punch = RegistroPonto(
        usuario_id=employee.id,
        tipo_registro="entrada",
        data_hora=original,
        origem="web",
        criado_em=original,
    )
    session.add(punch)
    session.commit()

    request = create_correction_request(
        session,
        employee.id,
        punch.id,
        datetime(2026, 11, 10, 9, 15, tzinfo=LOCAL),
        "O relógio estava atrasado.",
    )
    assert effective_punch_times(session, employee.id, [punch])[punch.id].minute == 0

    decide_request(
        session,
        reviewer.id,
        request.id,
        approve=True,
        decision_note="Conferido.",
    )

    assert effective_punch_times(session, employee.id, [punch])[punch.id].minute == 15


def test_correction_request_rejects_original_punch_outside_current_month(
    session, monkeypatch
):
    _freeze_today(monkeypatch)
    employee = register_user(
        session, "Funcionária", "func@example.com", "senha-func-segura-123"
    )
    original = datetime(2026, 10, 31, 9, 0, tzinfo=LOCAL)
    punch = RegistroPonto(
        usuario_id=employee.id,
        tipo_registro="entrada",
        data_hora=original,
        origem="web",
        criado_em=original,
    )
    session.add(punch)
    session.commit()

    with pytest.raises(SolicitacaoError, match="mês atual"):
        create_correction_request(
            session,
            employee.id,
            punch.id,
            datetime(2026, 11, 10, 9, 15, tzinfo=LOCAL),
            "Ajuste de horário.",
        )