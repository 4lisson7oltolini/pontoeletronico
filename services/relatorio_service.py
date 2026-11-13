"""Monthly work-hour reports and Excel exports scoped to one account."""

from calendar import monthrange
from copy import copy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

import pandas as pd
from openpyxl.styles import PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import AjustePonto, ConfiguracaoJornada, Feriado, Folga, RegistroPonto
from services.ponto_service import PUNCH_SEQUENCE, effective_punch_times, list_punches
from utils.datetime_utils import app_timezone, now_local

ZERO = Decimal("0.00")


@dataclass
class DailyReport:
    day: date
    status: str
    punches: dict[str, datetime]
    worked_hours: Decimal
    expected_hours: Decimal
    daily_overtime: Decimal
    weekly_overtime: Decimal = ZERO

    @property
    def overtime(self) -> Decimal:
        return self.daily_overtime + self.weekly_overtime

    @property
    def balance(self) -> Decimal:
        return self.worked_hours - self.expected_hours


@dataclass(frozen=True)
class WeeklyReport:
    week_start: date
    week_end: date
    scheduled_days: int
    worked_hours: Decimal
    expected_hours: Decimal
    daily_overtime: Decimal
    weekly_overtime: Decimal

    @property
    def total_overtime(self) -> Decimal:
        return self.daily_overtime + self.weekly_overtime


def _validate_period(year: int, month: int) -> None:
    if not 1 <= month <= 12 or year < 1:
        raise ValueError("Informe um mês e ano válidos.")


def report_period_end(year: int, month: int) -> date:
    _validate_period(year, month)
    return date(year, month, monthrange(year, month)[1])


def monthly_punches(
    session: Session, user_id: int, year: int, month: int
) -> list[RegistroPonto]:
    _validate_period(year, month)
    first_day = date(year, month, 1)
    last_day = report_period_end(year, month)
    first_week_day = first_day - timedelta(days=first_day.weekday())
    last_week_day = last_day + timedelta(days=6 - last_day.weekday())
    timezone = app_timezone()
    start = datetime.combine(first_week_day - timedelta(days=1), time.min, tzinfo=timezone)
    end = datetime.combine(last_week_day + timedelta(days=2), time.min, tzinfo=timezone)
    return list_punches(session, user_id, start, end)


def _hours_between(start: datetime, end: datetime) -> Decimal:
    seconds = Decimal(str((end - start).total_seconds()))
    return (seconds / Decimal(3600)).quantize(Decimal("0.01"))


def _workday_groups(
    punches: list[RegistroPonto], effective_times: dict[int, datetime]
) -> dict[date, list[RegistroPonto]]:
    ordered = sorted(
        punches,
        key=lambda punch: (effective_times[punch.id], punch.id),
    )
    groups: dict[date, list[RegistroPonto]] = {}
    active: list[RegistroPonto] = []
    active_day: date | None = None

    for punch in ordered:
        if punch.tipo_registro == "entrada":
            if active and active_day is not None:
                groups.setdefault(active_day, []).extend(active)
            active = [punch]
            active_day = effective_times[punch.id].date()
            continue

        if active and active_day is not None:
            active.append(punch)
            if punch.tipo_registro == "saida":
                groups.setdefault(active_day, []).extend(active)
                active = []
                active_day = None
        else:
            groups.setdefault(effective_times[punch.id].date(), []).append(punch)

    if active and active_day is not None:
        groups.setdefault(active_day, []).extend(active)

    for day in groups:
        groups[day].sort(key=lambda punch: (effective_times[punch.id], punch.id))
    return groups


def _scheduled_days_data(
    session: Session, user_id: int, first_day: date, last_day: date
) -> tuple[dict[date, Folga], dict[date, Feriado]]:
    days_off = session.scalars(
        select(Folga).where(
            Folga.usuario_id == user_id,
            Folga.status.in_(("planejada", "realizada")),
            Folga.data >= first_day,
            Folga.data <= last_day,
        )
    )
    holidays = session.scalars(
        select(Feriado).where(
            Feriado.usuario_id == user_id,
            Feriado.data >= first_day,
            Feriado.data <= last_day,
        )
    )
    return (
        {item.data: item for item in days_off},
        {item.data: item for item in holidays},
    )


def _base_daily_report(
    day: date,
    punches: list[RegistroPonto],
    effective_times: dict[int, datetime],
    daily_hours: Decimal,
    day_off: Folga | None,
    holiday: Feriado | None,
) -> DailyReport:
    times_by_type: dict[str, datetime] = {}
    kinds = [punch.tipo_registro for punch in punches]
    complete = kinds == list(PUNCH_SEQUENCE)

    for punch in punches:
        if punch.tipo_registro in times_by_type:
            complete = False
        times_by_type[punch.tipo_registro] = effective_times[punch.id]

    if complete:
        start = times_by_type["entrada"]
        end = times_by_type["saida"]
        worked = _hours_between(start, end)
        if worked < ZERO:
            complete = False
    else:
        worked = ZERO

    expected = ZERO if day_off or holiday else daily_hours
    if punches and not complete:
        status = "Incompleto"
        worked = ZERO
    elif complete and day_off:
        status = f"Trabalhado em folga ({day_off.status})"
    elif complete and holiday:
        status = f"Trabalhado em feriado: {holiday.descricao}"
    elif complete:
        status = "Completo"
    elif day_off:
        status = f"Folga {day_off.status}"
    elif holiday:
        status = f"Feriado: {holiday.descricao}"
    else:
        status = "Sem marcação"

    daily_overtime = max(ZERO, worked - expected) if complete else ZERO
    return DailyReport(
        day=day,
        status=status,
        punches=times_by_type,
        worked_hours=worked,
        expected_hours=expected,
        daily_overtime=daily_overtime,
    )


def build_monthly_report(
    session: Session,
    user_id: int,
    year: int,
    month: int,
    *,
    as_of: date | None = None,
) -> dict:
    """Build a monthly report; each user's recorded rest day is excluded from schedule."""
    _validate_period(year, month)
    month_start = date(year, month, 1)
    month_end = report_period_end(year, month)
    effective_end = min(month_end, as_of or now_local().date())
    if effective_end < month_start:
        effective_end = month_start - timedelta(days=1)

    daily_hours = Decimal("8.00")
    schedule = session.scalar(
        select(ConfiguracaoJornada).where(ConfiguracaoJornada.usuario_id == user_id)
    )
    if schedule is not None:
        daily_hours = Decimal(schedule.horas_diarias_referencia)
        weekly_hours = Decimal(schedule.horas_semanais_referencia)
    else:
        weekly_hours = daily_hours * Decimal("6")

    first_week_day = month_start - timedelta(days=month_start.weekday())
    last_week_day = (
        effective_end + timedelta(days=6 - effective_end.weekday())
        if effective_end >= month_start
        else first_week_day - timedelta(days=1)
    )
    if (as_of or now_local().date()).year == year and (as_of or now_local().date()).month == month:
        last_week_day = min(last_week_day, effective_end)

    report_punches = monthly_punches(session, user_id, year, month)
    punches = [
        punch
        for punch in report_punches
        if first_week_day - timedelta(days=1)
        <= punch.data_hora.astimezone(app_timezone()).date()
        <= last_week_day + timedelta(days=1)
    ]
    effective_times = effective_punch_times(session, user_id, punches)
    workday_groups = _workday_groups(punches, effective_times)
    days_off, holidays = _scheduled_days_data(
        session, user_id, first_week_day, last_week_day
    )

    weekly_days: dict[date, DailyReport] = {}
    if effective_end >= month_start:
        day = first_week_day
        while day <= last_week_day:
            weekly_days[day] = _base_daily_report(
                day,
                workday_groups.get(day, []),
                effective_times,
                daily_hours,
                days_off.get(day),
                holidays.get(day),
            )
            day += timedelta(days=1)

    weekly_reports: list[WeeklyReport] = []
    month_weeks: list[WeeklyReport] = []
    week_start = first_week_day
    while week_start <= last_week_day:
        week_dates = [
            week_start + timedelta(days=offset)
            for offset in range(7)
            if week_start + timedelta(days=offset) in weekly_days
        ]
        week_rows = [weekly_days[day] for day in week_dates]
        scheduled_days = sum(row.expected_hours > ZERO for row in week_rows)
        expected_hours = (
            (weekly_hours * Decimal(scheduled_days) / Decimal("6")).quantize(
                Decimal("0.01")
            )
            if scheduled_days
            else ZERO
        )
        worked_hours = sum((row.worked_hours for row in week_rows), ZERO)
        daily_overtime = sum((row.daily_overtime for row in week_rows), ZERO)
        weekly_excess = max(ZERO, worked_hours - expected_hours)
        weekly_only_overtime = max(ZERO, weekly_excess - daily_overtime)
        remaining_weekly_overtime = weekly_only_overtime

        for row in reversed(week_rows):
            available_regular = max(ZERO, row.worked_hours - row.daily_overtime)
            allocation = min(available_regular, remaining_weekly_overtime)
            row.weekly_overtime += allocation
            remaining_weekly_overtime -= allocation
            if remaining_weekly_overtime == ZERO:
                break

        weekly = WeeklyReport(
            week_start=week_start,
            week_end=week_start + timedelta(days=6),
            scheduled_days=scheduled_days,
            worked_hours=worked_hours,
            expected_hours=expected_hours,
            daily_overtime=daily_overtime,
            weekly_overtime=weekly_only_overtime,
        )
        weekly_reports.append(weekly)
        if week_start <= month_end and week_start + timedelta(days=6) >= month_start:
            month_weeks.append(weekly)
        week_start += timedelta(days=7)

    daily_rows = [
        weekly_days[month_start + timedelta(days=offset)]
        for offset in range((effective_end - month_start).days + 1)
    ] if effective_end >= month_start else []

    month_worked = sum((row.worked_hours for row in daily_rows), ZERO)
    month_expected = sum((row.expected_hours for row in daily_rows), ZERO)
    month_daily_overtime = sum((row.daily_overtime for row in daily_rows), ZERO)
    month_weekly_overtime = sum((row.weekly_overtime for row in daily_rows), ZERO)
    month_adjustment_ids = {
        punch.id
        for day, group in workday_groups.items()
        if month_start <= day <= effective_end
        for punch in group
    }
    adjustments = list(
        session.scalars(
            select(AjustePonto)
            .where(
                AjustePonto.usuario_id == user_id,
                AjustePonto.registro_ponto_id.in_(month_adjustment_ids)
                if month_adjustment_ids
                else AjustePonto.registro_ponto_id == -1,
            )
            .order_by(AjustePonto.criado_em, AjustePonto.id)
        )
    )
    return {
        "user_id": user_id,
        "year": year,
        "month": month,
        "daily_hours": daily_hours,
        "weekly_hours": weekly_hours,
        "schedule": schedule,
        "daily_rows": daily_rows,
        "weekly_rows": month_weeks,
        "adjustments": adjustments,
        "summary": {
            "worked_hours": month_worked,
            "expected_hours": month_expected,
            "balance": month_worked - month_expected,
            "daily_overtime": month_daily_overtime,
            "weekly_overtime": month_weekly_overtime,
            "total_overtime": month_daily_overtime + month_weekly_overtime,
            "days_worked": sum(row.worked_hours > ZERO for row in daily_rows),
            "incomplete_days": sum(row.status == "Incompleto" for row in daily_rows),
            "scheduled_days": sum(row.expected_hours > ZERO for row in daily_rows),
        },
    }


def _format_timestamp(value: datetime | None) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else ""


def _daily_dataframe(rows: list[DailyReport]) -> pd.DataFrame:
    labels = {
        "entrada": "Entrada",
        "saida_intervalo": "Saída intervalo",
        "retorno_intervalo": "Retorno intervalo",
        "saida": "Saída final",
    }
    return pd.DataFrame(
        [
            {
                "Data de trabalho": row.day,
                "Status": row.status,
                **{
                    labels[kind]: _format_timestamp(row.punches.get(kind))
                    for kind in PUNCH_SEQUENCE
                },
                "Horas trabalhadas": float(row.worked_hours),
                "Horas previstas": float(row.expected_hours),
                "Extra diária": float(row.daily_overtime),
                "Extra semanal adicional": float(row.weekly_overtime),
                "Total de horas extras": float(row.overtime),
                "Saldo do dia": float(row.balance),
            }
            for row in rows
        ]
    )


def export_monthly_report_xlsx(report: dict, user_name: str) -> bytes:
    """Create a formatted workbook with monthly summary, daily detail, and audit."""
    summary = report["summary"]
    output = BytesIO()
    summary_rows = [
        ("Usuário", user_name),
        ("Período", f"{report['month']:02d}/{report['year']}"),
        ("Jornada diária de referência (horas)", float(report["daily_hours"])),
        ("Jornada semanal de referência (horas)", float(report["weekly_hours"])),
        ("Dias previstos", summary["scheduled_days"]),
        ("Dias trabalhados completos", summary["days_worked"]),
        ("Dias com marcações incompletas", summary["incomplete_days"]),
        ("Horas previstas", float(summary["expected_hours"])),
        ("Horas trabalhadas", float(summary["worked_hours"])),
        ("Saldo de horas", float(summary["balance"])),
        ("Horas extras diárias", float(summary["daily_overtime"])),
        ("Horas extras semanais adicionais", float(summary["weekly_overtime"])),
        ("Total de horas extras (sem duplicação)", float(summary["total_overtime"])),
    ]
    summary_frame = pd.DataFrame(summary_rows, columns=["Indicador", "Valor"])
    weekly_frame = pd.DataFrame(
        [
            {
                "Semana (segunda-feira)": row.week_start,
                "Semana (domingo)": row.week_end,
                "Dias previstos": row.scheduled_days,
                "Horas previstas": float(row.expected_hours),
                "Horas trabalhadas": float(row.worked_hours),
                "Extra diária": float(row.daily_overtime),
                "Extra semanal adicional": float(row.weekly_overtime),
                "Total de extras": float(row.total_overtime),
            }
            for row in report["weekly_rows"]
        ]
    )
    audit_frame = pd.DataFrame(
        [
            {
                "Operação": "Inclusão" if item.operacao == "inclusao" else "Correção",
                "ID do registro": item.registro_ponto_id,
                "Horário original": (
                    ""
                    if item.operacao == "inclusao"
                    else _format_timestamp(item.horario_original)
                ),
                "Horário efetivo": _format_timestamp(item.horario_corrigido),
                "Justificativa": item.justificativa,
                "Alterado em": _format_timestamp(item.criado_em),
            }
            for item in report["adjustments"]
        ],
        columns=[
            "Operação",
            "ID do registro",
            "Horário original",
            "Horário efetivo",
            "Justificativa",
            "Alterado em",
        ],
    )

    with pd.ExcelWriter(output, engine="openpyxl", date_format="DD/MM/YYYY") as writer:
        summary_frame.to_excel(writer, sheet_name="Resumo", index=False, startrow=0)
        weekly_frame.to_excel(
            writer,
            sheet_name="Resumo",
            index=False,
            startrow=len(summary_frame) + 3,
        )
        _daily_dataframe(report["daily_rows"]).to_excel(
            writer, sheet_name="Detalhamento diário", index=False
        )
        audit_frame.to_excel(writer, sheet_name="Histórico de ajustes", index=False)
        for worksheet in writer.sheets.values():
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for column_cells in worksheet.columns:
                max_length = max(
                    (len(str(cell.value)) for cell in column_cells if cell.value is not None),
                    default=0,
                )
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(
                    max(max_length + 2, 14), 48
                )
            for cell in worksheet[1]:
                font = copy(cell.font)
                font.bold = True
                font.color = "FFFFFF"
                cell.font = font
                cell.fill = PatternFill(
                    fill_type="solid", fgColor="1F3A5F"
                )

    return output.getvalue()
