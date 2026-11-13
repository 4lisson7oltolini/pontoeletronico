from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from database.models import ConfiguracaoJornada, RegistroPonto
from services.auth_service import AuthorizationError, register_admin_user, register_user
from services.rh_service import get_hr_overview


def test_hr_can_access_employee_schedules_and_punches(session):
    employee = register_user(
        session, "Funcionária", "func@example.com", "senha-func-segura-123"
    )
    hr = register_user(session, "Pessoa RH", "rh@example.com", "senha-rh-segura-123")
    hr.perfil = "rh"
    session.add(
        ConfiguracaoJornada(
            usuario_id=employee.id,
            horas_diarias_referencia=8,
            horas_semanais_referencia=40,
            quantidade_intervalos=1,
            fuso_horario="America/Sao_Paulo",
        )
    )
    timestamp = datetime(2026, 11, 12, 9, tzinfo=ZoneInfo("America/Sao_Paulo"))
    session.add(
        RegistroPonto(
            usuario_id=employee.id,
            tipo_registro="entrada",
            data_hora=timestamp,
            origem="web",
            criado_em=timestamp,
        )
    )
    session.commit()

    employees, schedules, punches = get_hr_overview(session, hr.id)

    assert [item.id for item in employees] == [employee.id]
    assert schedules[0]["Horas semanais"] == 40.0
    assert punches[0]["Funcionário"] == "Funcionária"
    assert punches[0]["Tipo"] == "Entrada"


def test_employee_cannot_access_hr_overview(session):
    employee = register_user(
        session, "Funcionária", "func@example.com", "senha-func-segura-123"
    )

    with pytest.raises(AuthorizationError):
        get_hr_overview(session, employee.id)


def test_admin_can_access_hr_overview(session):
    admin = register_admin_user(
        session, "Admin", "admin@example.com", "senha-admin-segura-123"
    )

    employees, schedules, punches = get_hr_overview(session, admin.id)

    assert employees == []
    assert schedules == []
    assert punches == []