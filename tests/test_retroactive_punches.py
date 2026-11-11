from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from database.models import RegistroPonto
from services.auth_service import register_user
from services.ponto_service import (
    PontoError,
    add_retroactive_punch,
    correct_punch,
    effective_punch_times,
    list_adjustments,
)

LOCAL = ZoneInfo("America/Sao_Paulo")


def _fixed_today(monkeypatch, day=date(2026, 11, 11)):
    monkeypatch.setattr(
        "services.ponto_service.now_local",
        lambda: datetime.combine(day, time(12), tzinfo=LOCAL),
    )


def test_add_missing_punch_requires_sequence_and_stores_audit(session, monkeypatch):
    _fixed_today(monkeypatch)
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")

    with pytest.raises(PontoError, match="sequência"):
        add_retroactive_punch(
            session, user.id, date(2026, 11, 10), "saida_intervalo", time(12), "Esquecimento"
        )

    entrance = add_retroactive_punch(
        session, user.id, date(2026, 11, 10), "entrada", time(9), "Esqueci de registrar"
    )
    final_exit = add_retroactive_punch(
        session, user.id, date(2026, 11, 10), "saida", time(17), "Esqueci de registrar"
    )

    entries = list_adjustments(session, user.id)
    assert entrance.origem == "ajuste_manual"
    assert len(entries) == 2
    assert all(item.operacao == "inclusao" for item in entries)
    assert effective_punch_times(session, user.id, [final_exit])[final_exit.id].hour == 17


def test_retroactive_punches_are_limited_to_previous_days_in_current_month(
    session, monkeypatch
):
    _fixed_today(monkeypatch)
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")

    for day in (date(2026, 10, 31), date(2026, 11, 11), date(2026, 11, 12)):
        with pytest.raises(PontoError):
            add_retroactive_punch(session, user.id, day, "entrada", time(9), "Ajuste")


def test_correction_updates_effective_time_but_preserves_original(session, monkeypatch):
    _fixed_today(monkeypatch)
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")
    original = datetime(2026, 11, 10, 9, tzinfo=LOCAL)
    record = RegistroPonto(
        usuario_id=user.id,
        tipo_registro="entrada",
        data_hora=original,
        origem="web",
        criado_em=original,
    )
    session.add(record)
    session.commit()
    corrected = datetime(2026, 11, 10, 9, 15, tzinfo=LOCAL)

    correct_punch(session, user.id, record.id, corrected, "Relógio do celular atrasado")

    effective = effective_punch_times(session, user.id, [record])
    assert effective[record.id].minute == 15
    assert record.data_hora.replace(tzinfo=LOCAL) == original
    assert list_adjustments(session, user.id)[0].horario_original.replace(tzinfo=LOCAL) == original


def test_retroactive_changes_cannot_access_another_users_punch(session, monkeypatch):
    _fixed_today(monkeypatch)
    first = register_user(session, "Conta Um", "um@example.com", "senha-conta-um-123")
    second = register_user(session, "Conta Dois", "dois@example.com", "senha-conta-dois-123")
    timestamp = datetime(2026, 11, 10, 9, tzinfo=LOCAL)
    punch = RegistroPonto(
        usuario_id=first.id,
        tipo_registro="entrada",
        data_hora=timestamp,
        origem="web",
        criado_em=timestamp,
    )
    session.add(punch)
    session.commit()

    with pytest.raises(PontoError, match="não encontrado"):
        correct_punch(
            session,
            second.id,
            punch.id,
            datetime(2026, 11, 10, 9, 5, tzinfo=LOCAL),
            "Ajuste indevido",
        )
    assert list_adjustments(session, second.id) == []
