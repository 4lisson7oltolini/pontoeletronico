"""Account-scoped report data access; spreadsheet generation is a later stage."""

from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from database.models import RegistroPonto
from services.ponto_service import list_punches
from utils.datetime_utils import app_timezone


def monthly_punches(
    session: Session, user_id: int, year: int, month: int
) -> list[RegistroPonto]:
    if not 1 <= month <= 12 or year < 1:
        raise ValueError("Informe um mês e ano válidos.")
    first_day = date(year, month, 1)
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    timezone = app_timezone()
    start = datetime.combine(first_day, time.min, tzinfo=timezone)
    end = datetime.combine(next_month, time.min, tzinfo=timezone)
    return list_punches(session, user_id, start, end)


def report_period_end(year: int, month: int) -> date:
    if not 1 <= month <= 12 or year < 1:
        raise ValueError("Informe um mês e ano válidos.")
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return next_month - timedelta(days=1)
