from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from database.models import RegistroPonto
from services.auth_service import AuthorizationError, register_admin_user, register_user
from services.ponto_service import effective_punch_times, list_punches
from services.relatorio_service import (
    build_monthly_report,
    report_adjustment_revision,
)
from services.solicitacao_service import (
    SolicitacaoError,
    create_correction_request,
    create_missing_punch_request,
    decide_request,
    list_employee_requests_for_hr,
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


def test_approved_missing_punch_updates_monthly_report(session, monkeypatch):
    _freeze_today(monkeypatch)
    employee = register_user(
        session, "Funcionária", "func@example.com", "senha-func-segura-123"
    )
    reviewer = _rh_user(session)
    day = date(2026, 11, 10)
    for kind, hour in (
        ("entrada", 9),
        ("retorno_intervalo", 13),
        ("saida", 17),
    ):
        timestamp = datetime(2026, 11, 10, hour, tzinfo=LOCAL)
        session.add(
            RegistroPonto(
                usuario_id=employee.id,
                tipo_registro=kind,
                data_hora=timestamp,
                origem="web",
                criado_em=timestamp,
            )
        )
    session.commit()

    before = build_monthly_report(
        session, employee.id, 2026, 11, as_of=date(2026, 11, 11)
    )
    before_day = next(row for row in before["daily_rows"] if row.day == day)
    assert before_day.status == "Incompleto"
    assert report_adjustment_revision(session, employee.id) == 0
    request = create_missing_punch_request(
        session,
        employee.id,
        day,
        "saida_intervalo",
        time(12),
        "Esqueci de registrar a saída para intervalo.",
    )
    assert report_adjustment_revision(session, employee.id) == 0

    decide_request(
        session,
        reviewer.id,
        request.id,
        approve=True,
        decision_note="Conferido com a folha de presença.",
    )

    after = build_monthly_report(
        session, employee.id, 2026, 11, as_of=date(2026, 11, 11)
    )
    after_day = next(row for row in after["daily_rows"] if row.day == day)
    assert report_adjustment_revision(session, employee.id) == 1
    assert after_day.status == "Completo"
    assert after_day.punches["saida_intervalo"].hour == 12
    assert after["summary"]["incomplete_days"] == 0


def test_missing_punch_request_replaces_existing_mark_after_approval(
    session, monkeypatch
):
    _freeze_today(monkeypatch)
    employee = register_user(
        session, "Funcionária", "func@example.com", "senha-func-segura-123"
    )
    reviewer = _rh_user(session)
    day = date(2026, 11, 10)
    for kind, hour in (
        ("entrada", 9),
        ("saida_intervalo", 12),
        ("retorno_intervalo", 13),
        ("saida", 17),
    ):
        timestamp = datetime.combine(day, time(hour), tzinfo=LOCAL)
        session.add(
            RegistroPonto(
                usuario_id=employee.id,
                tipo_registro=kind,
                data_hora=timestamp,
                origem="web",
                criado_em=timestamp,
            )
        )
    session.commit()
    existing_punch = next(
        punch
        for punch in list_punches(session, employee.id)
        if punch.tipo_registro == "saida_intervalo"
    )
    original_timestamp = existing_punch.data_hora
    before = build_monthly_report(
        session, employee.id, 2026, 11, as_of=date(2026, 11, 11)
    )
    before_day = next(row for row in before["daily_rows"] if row.day == day)
    assert before_day.punches["saida_intervalo"].minute == 0

    request = create_missing_punch_request(
        session,
        employee.id,
        day,
        "saida_intervalo",
        time(12, 15),
        "O horário da saída para intervalo foi registrado incorretamente.",
    )

    assert request.operacao == "correcao"
    assert request.registro_ponto_id == existing_punch.id
    assert effective_punch_times(session, employee.id, [existing_punch])[
        existing_punch.id
    ].minute == 0
    assert report_adjustment_revision(session, employee.id) == 0
    assert len(list_punches(session, employee.id)) == 4

    decide_request(
        session,
        reviewer.id,
        request.id,
        approve=True,
        decision_note="Horário atualizado após conferência.",
    )

    assert existing_punch.data_hora.minute == 0
    assert effective_punch_times(session, employee.id, [existing_punch])[
        existing_punch.id
    ].minute == 15
    after = build_monthly_report(
        session, employee.id, 2026, 11, as_of=date(2026, 11, 11)
    )
    after_day = next(row for row in after["daily_rows"] if row.day == day)
    assert after_day.punches["saida_intervalo"].minute == 15
    assert report_adjustment_revision(session, employee.id) == 1
    assert existing_punch.data_hora == original_timestamp
    assert len(list_punches(session, employee.id)) == 4


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


def test_hr_can_view_selected_employee_requests_only(session, monkeypatch):
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
        "Esqueci de registrar.",
    )

    assert list_employee_requests_for_hr(session, reviewer.id, employee.id) == [request]
    with pytest.raises(AuthorizationError):
        list_employee_requests_for_hr(session, employee.id, employee.id)


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
    punches = []
    for kind, hour in (
        ("entrada", 9),
        ("saida_intervalo", 12),
        ("retorno_intervalo", 13),
        ("saida", 17),
    ):
        timestamp = datetime(2026, 11, 10, hour, tzinfo=LOCAL)
        punch = RegistroPonto(
            usuario_id=employee.id,
            tipo_registro=kind,
            data_hora=timestamp,
            origem="web",
            criado_em=timestamp,
        )
        punches.append(punch)
        session.add(punch)
    session.commit()
    entry_punch = punches[0]
    day = date(2026, 11, 10)
    before = build_monthly_report(
        session, employee.id, 2026, 11, as_of=date(2026, 11, 11)
    )
    before_day = next(row for row in before["daily_rows"] if row.day == day)
    assert before_day.punches["entrada"].minute == 0
    assert report_adjustment_revision(session, employee.id) == 0

    request = create_correction_request(
        session,
        employee.id,
        entry_punch.id,
        datetime(2026, 11, 10, 9, 15, tzinfo=LOCAL),
        "O relógio estava atrasado.",
    )
    assert effective_punch_times(session, employee.id, [entry_punch])[
        entry_punch.id
    ].minute == 0
    assert report_adjustment_revision(session, employee.id) == 0

    decide_request(
        session,
        reviewer.id,
        request.id,
        approve=True,
        decision_note="Conferido.",
    )

    after = build_monthly_report(
        session, employee.id, 2026, 11, as_of=date(2026, 11, 11)
    )
    after_day = next(row for row in after["daily_rows"] if row.day == day)
    assert effective_punch_times(session, employee.id, [entry_punch])[
        entry_punch.id
    ].minute == 15
    assert report_adjustment_revision(session, employee.id) == 1
    assert after_day.punches["entrada"].minute == 15


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