from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from database.models import RegistroPonto
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
    session.add_all(
        [
            RegistroPonto(
                usuario_id=first.id,
                tipo_registro="entrada",
                data_hora=timestamp,
                origem="web",
                criado_em=timestamp,
            ),
            RegistroPonto(
                usuario_id=second.id,
                tipo_registro="entrada",
                data_hora=timestamp,
                origem="web",
                criado_em=timestamp,
            ),
        ]
    )
    session.commit()

    summary = dashboard_summary(session, first.id, timestamp.date())
    assert summary["working_days"] == 1
    assert summary["latest_punch"].usuario_id == first.id
