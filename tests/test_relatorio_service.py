from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from database.models import ConfiguracaoJornada, Feriado, Folga, RegistroPonto
from services.auth_service import register_user
from services.relatorio_service import (
    build_monthly_report,
    export_monthly_report_xlsx,
)

LOCAL = ZoneInfo("America/Sao_Paulo")


def _create_user_with_schedule(session, email="ana@example.com", weekly="48"):
    user = register_user(session, "Ana Silva", email, "senha-segura-123")
    session.add(
        ConfiguracaoJornada(
            usuario_id=user.id,
            horas_diarias_referencia=Decimal("8"),
            horas_semanais_referencia=Decimal(weekly),
            quantidade_intervalos=1,
            fuso_horario="America/Sao_Paulo",
        )
    )
    session.commit()
    return user


def _add_shift(session, user_id, start: datetime, end: datetime):
    duration = end - start
    interval_start = start + duration / 3
    interval_end = start + duration / 2
    punches = [
        ("entrada", start),
        ("saida_intervalo", interval_start),
        ("retorno_intervalo", interval_end),
        ("saida", end),
    ]
    for kind, timestamp in punches:
        session.add(
            RegistroPonto(
                usuario_id=user_id,
                tipo_registro=kind,
                data_hora=timestamp,
                origem="web",
                criado_em=timestamp,
            )
        )
    session.commit()


def test_monthly_report_counts_included_break_and_attributes_overnight_to_entry_day(
    session,
):
    user = _create_user_with_schedule(session)
    _add_shift(
        session,
        user.id,
        datetime(2026, 11, 11, 14, tzinfo=LOCAL),
        datetime(2026, 11, 12, 0, tzinfo=LOCAL),
    )
    session.add(
        Folga(
            usuario_id=user.id,
            data=date(2026, 11, 12),
            status="planejada",
            criado_em=datetime(2026, 11, 1, tzinfo=LOCAL),
        )
    )
    session.commit()

    report = build_monthly_report(
        session, user.id, 2026, 11, as_of=date(2026, 11, 30)
    )
    worked_day = next(row for row in report["daily_rows"] if row.day == date(2026, 11, 11))
    rest_day = next(row for row in report["daily_rows"] if row.day == date(2026, 11, 12))

    assert worked_day.status == "Completo"
    assert worked_day.worked_hours == Decimal("10.00")
    assert worked_day.daily_overtime == Decimal("2.00")
    assert worked_day.punches["saida"].date() == date(2026, 11, 12)
    assert rest_day.status == "Folga planejada"
    assert report["summary"]["total_overtime"] == Decimal("2.00")


def test_weekly_overtime_is_added_without_double_counting_daily_overtime(session):
    user = _create_user_with_schedule(session, weekly="40")
    for day in (
        date(2026, 11, 9),
        date(2026, 11, 11),
        date(2026, 11, 12),
        date(2026, 11, 13),
        date(2026, 11, 14),
        date(2026, 11, 15),
    ):
        _add_shift(
            session,
            user.id,
            datetime.combine(day, time(9), tzinfo=LOCAL),
            datetime.combine(day, time(17), tzinfo=LOCAL),
        )
    session.add(
        Folga(
            usuario_id=user.id,
            data=date(2026, 11, 10),
            status="realizada",
            criado_em=datetime(2026, 11, 1, tzinfo=LOCAL),
        )
    )
    session.commit()

    report = build_monthly_report(
        session, user.id, 2026, 11, as_of=date(2026, 11, 15)
    )
    first_week = next(row for row in report["weekly_rows"] if row.week_start == date(2026, 11, 9))

    assert first_week.expected_hours == Decimal("40.00")
    assert first_week.worked_hours == Decimal("48.00")
    assert first_week.daily_overtime == Decimal("0.00")
    assert first_week.weekly_overtime == Decimal("8.00")
    assert report["summary"]["total_overtime"] == Decimal("8.00")


def test_incomplete_days_are_flagged_and_excluded_from_worked_hours(session):
    user = _create_user_with_schedule(session)
    timestamp = datetime(2026, 11, 11, 9, tzinfo=LOCAL)
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

    report = build_monthly_report(
        session, user.id, 2026, 11, as_of=date(2026, 11, 11)
    )
    incomplete = next(row for row in report["daily_rows"] if row.day == timestamp.date())

    assert incomplete.status == "Incompleto"
    assert incomplete.worked_hours == Decimal("0.00")
    assert report["summary"]["incomplete_days"] == 1


def test_folgas_holidays_and_records_are_scoped_to_the_current_account(session):
    user = _create_user_with_schedule(session)
    other = _create_user_with_schedule(session, email="outra@example.com")
    session.add(
        Feriado(
            usuario_id=user.id,
            data=date(2026, 11, 12),
            descricao="Feriado pessoal",
            tipo="pessoal",
        )
    )
    session.add(
        Folga(
            usuario_id=other.id,
            data=date(2026, 11, 13),
            status="realizada",
            criado_em=datetime(2026, 11, 1, tzinfo=LOCAL),
        )
    )
    _add_shift(
        session,
        other.id,
        datetime(2026, 11, 11, 9, tzinfo=LOCAL),
        datetime(2026, 11, 11, 17, tzinfo=LOCAL),
    )
    session.commit()

    report = build_monthly_report(
        session, user.id, 2026, 11, as_of=date(2026, 11, 13)
    )
    holiday = next(row for row in report["daily_rows"] if row.day == date(2026, 11, 12))

    assert holiday.status == "Feriado: Feriado pessoal"
    assert holiday.expected_hours == Decimal("0.00")
    assert report["summary"]["worked_hours"] == Decimal("0.00")


def test_excel_report_contains_summary_daily_and_audit_sheets(session):
    user = _create_user_with_schedule(session)
    timestamp = datetime(2026, 11, 11, 9, tzinfo=LOCAL)
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
    report = build_monthly_report(
        session, user.id, 2026, 11, as_of=date(2026, 11, 11)
    )

    workbook_bytes = export_monthly_report_xlsx(report, user.nome)
    workbook = load_workbook(BytesIO(workbook_bytes), read_only=True)

    assert workbook.sheetnames == ["Resumo", "Detalhamento diário", "Histórico de ajustes"]
    assert workbook["Resumo"]["A1"].value == "Indicador"
    assert workbook["Detalhamento diário"]["A1"].value == "Data de trabalho"
