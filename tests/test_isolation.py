from datetime import date

import pytest

from services.auth_service import register_user
from services.folga_service import FolgaError, list_days_off, plan_day_off, update_day_off
from services.ponto_service import PontoError, correct_punch, list_punches


def test_accounts_cannot_read_or_change_each_others_records(session, monkeypatch):
    first = register_user(session, "Conta Um", "um@example.com", "senha-conta-um-123")
    second = register_user(session, "Conta Dois", "dois@example.com", "senha-conta-dois-123")
    first_day_off = plan_day_off(session, first.id, date(2026, 12, 25))

    assert list_days_off(session, second.id) == []
    with pytest.raises(FolgaError, match="não encontrada"):
        update_day_off(session, second.id, first_day_off.id, "cancelada")

    from datetime import datetime
    from zoneinfo import ZoneInfo

    from database.models import RegistroPonto

    timestamp = datetime(2026, 11, 10, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    punch = RegistroPonto(
        usuario_id=first.id,
        tipo_registro="entrada",
        data_hora=timestamp,
        origem="web",
        criado_em=timestamp,
    )
    session.add(punch)
    session.commit()

    assert list_punches(session, second.id) == []
    with pytest.raises(PontoError, match="não encontrado"):
        correct_punch(session, second.id, punch.id, timestamp, "Ajuste indevido")
