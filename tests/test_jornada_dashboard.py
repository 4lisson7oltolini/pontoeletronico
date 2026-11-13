from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event

from database.models import AjustePonto, ConfiguracaoJornada, RegistroPonto
from services.auth_service import register_user
from services.dashboard_service import dashboard_summary
from services.jornada_service import JornadaError, get_schedule, save_schedule


def test_schedule_is_account_scoped_and_validates_timezone(session):
    first = register_user(session, "Conta Um", "um@example.com", "senha-conta-um-123")
    second = register_user(session, "Conta Dois", "dois@example.com", "senha-conta-dois-123")

    saved = save_schedule(
        session, first.id, Decimal("8"), Decimal("40"), None, None, 1, "America/Sao_Paulo"
    )

    assert get_schedule(session, first.id).id == saved.id
    assert get_schedule(session, second.id) is None
    with pytest.raises(JornadaError, match="Fuso"):
        save_schedule(
            session, second.id, Decimal("8"), Decimal("40"), None, None, 1, "Invalid/Zone"
        )


def test_dashboard_summary_only_counts_authenticated_account(session):
    first = register_user(session, "Conta Um", "um@example.com", "senha-conta-um-123")
    second = register_user(session, "Conta Dois", "dois@example.com", "senha-conta-dois-123")
    timestamp = datetime(2026, 11, 10, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    first_punch = RegistroPonto(
        usuario_id=first.id,
        tipo_registro="entrada",
        data_hora=timestamp,
        origem="web",
        criado_em=timestamp,
    )
    second_punch = RegistroPonto(
        usuario_id=second.id,
        tipo_registro="entrada",
        data_hora=timestamp,
        origem="web",
        criado_em=timestamp,
    )
    session.add_all([first_punch, second_punch])
    session.commit()
    session.add(
        AjustePonto(
            usuario_id=first.id,
            registro_ponto_id=first_punch.id,
            horario_original=timestamp,
            horario_corrigido=timestamp.replace(hour=10),
            justificativa="Correção de teste",
            operacao="correcao",
            criado_em=timestamp,
        )
    )
    session.commit()

    summary = dashboard_summary(session, first.id, timestamp.date())
    assert summary["working_days"] == 0
    assert summary["incomplete_days"] == 1
    assert summary["monthly_worked_hours"] == Decimal("0.00")
    assert summary["latest_punch"].usuario_id == first.id
    assert summary["latest_punch_time"].hour == 10


def test_dashboard_query_count_stays_bounded_with_long_history(session):
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")
    session.add(
        ConfiguracaoJornada(
            usuario_id=user.id,
            horas_diarias_referencia=Decimal("8"),
            horas_semanais_referencia=Decimal("48"),
            quantidade_intervalos=1,
            fuso_horario="America/Sao_Paulo",
        )
    )
    for day in range(1, 21):
        timestamp = datetime(2020, 1, day, 9, tzinfo=ZoneInfo("America/Sao_Paulo"))
        session.add(
            RegistroPonto(
                usuario_id=user.id,
                tipo_registro="entrada",
                data_hora=timestamp,
                origem="web",
                criado_em=timestamp,
            )
        )
    session.commit()

    statements = []

    def count_selects(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", count_selects)
    try:
        dashboard_summary(session, user.id, datetime(2026, 11, 13).date())
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", count_selects)

    assert len(statements) <= 8
