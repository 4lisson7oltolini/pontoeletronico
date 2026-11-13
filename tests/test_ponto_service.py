from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from database.models import AjustePonto, RegistroPonto
from services.auth_service import register_user
from services.ponto_service import (
    PontoError,
    correct_punch,
    latest_punch,
    register_punch,
)


def test_punch_sequence_is_enforced(session, monkeypatch):
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")
    monkeypatch.setattr(
        "services.ponto_service.now_local",
        lambda: datetime(2026, 11, 10, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
    )
    first = register_punch(session, user.id, "entrada")
    assert first.tipo_registro == "entrada"
    with pytest.raises(PontoError, match="fora de sequência"):
        register_punch(session, user.id, "entrada")

    for kind in ("saida_intervalo", "retorno_intervalo", "saida"):
        register_punch(session, user.id, kind)
    with pytest.raises(PontoError, match="jornada já encerrada"):
        register_punch(session, user.id, "entrada")


def test_final_punch_after_midnight_continues_yesterdays_shift(session, monkeypatch):
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")
    timestamps = iter(
        [
            datetime(2026, 11, 11, 14, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
            datetime(2026, 11, 11, 18, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
            datetime(2026, 11, 11, 18, 30, tzinfo=ZoneInfo("America/Sao_Paulo")),
            datetime(2026, 11, 12, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
        ]
    )
    monkeypatch.setattr("services.ponto_service.now_local", lambda: next(timestamps))

    punches = [
        register_punch(session, user.id, kind)
        for kind in ("entrada", "saida_intervalo", "retorno_intervalo", "saida")
    ]

    assert punches[-1].data_hora.date() == datetime(2026, 11, 12).date()
    assert punches[-1].tipo_registro == "saida"


def test_punch_rejects_unknown_kind(session):
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")
    with pytest.raises(PontoError, match="Tipo"):
        register_punch(session, user.id, "invalid")


def test_correction_creates_audit_without_overwriting_original(session):
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")
    original_time = datetime(
        2026, 11, 10, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo")
    )
    record = RegistroPonto(
        usuario_id=user.id,
        tipo_registro="entrada",
        data_hora=original_time,
        origem="web",
        criado_em=original_time,
    )
    session.add(record)
    session.commit()
    corrected_time = datetime(
        2026, 11, 10, 9, 5, tzinfo=ZoneInfo("America/Sao_Paulo")
    )

    adjustment = correct_punch(session, user.id, record.id, corrected_time, "Esqueci a marcação")

    session.refresh(record)
    assert adjustment.registro_ponto_id == record.id
    assert adjustment.horario_original == original_time
    assert record.data_hora.replace(tzinfo=ZoneInfo("America/Sao_Paulo")) == original_time


def test_latest_punch_query_uses_effective_time_and_account_scope(session):
    first = register_user(session, "Conta Um", "um@example.com", "senha-conta-um-123")
    second = register_user(session, "Conta Dois", "dois@example.com", "senha-conta-dois-123")
    base = datetime(2026, 11, 10, 9, tzinfo=ZoneInfo("America/Sao_Paulo"))
    earlier = RegistroPonto(
        usuario_id=first.id,
        tipo_registro="entrada",
        data_hora=base,
        origem="web",
        criado_em=base,
    )
    later = RegistroPonto(
        usuario_id=first.id,
        tipo_registro="saida",
        data_hora=base.replace(hour=17),
        origem="web",
        criado_em=base.replace(hour=17),
    )
    other_user = RegistroPonto(
        usuario_id=second.id,
        tipo_registro="entrada",
        data_hora=base.replace(day=11),
        origem="web",
        criado_em=base.replace(day=11),
    )
    session.add_all([earlier, later, other_user])
    session.commit()
    session.add(
        AjustePonto(
            usuario_id=first.id,
            registro_ponto_id=earlier.id,
            horario_original=base,
            horario_corrigido=base.replace(day=12, hour=20),
            justificativa="Correção",
            operacao="correcao",
            criado_em=base.replace(day=12, hour=20),
        )
    )
    session.commit()

    punch, effective_time = latest_punch(session, first.id)

    assert punch.id == earlier.id
    assert effective_time.date() == base.replace(day=12).date()
