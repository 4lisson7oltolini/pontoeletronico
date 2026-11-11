"""Account-scoped dashboard summaries without full work-hour calculations."""

from calendar import monthrange
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import ConfiguracaoJornada, Folga, RegistroPonto
from utils.datetime_utils import app_timezone


def dashboard_summary(session: Session, user_id: int, today: date) -> dict:
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    next_month = date(
        today.year + (1 if today.month == 12 else 0),
        today.month % 12 + 1,
        1,
    )
    timezone = app_timezone()
    month_start_at = datetime.combine(month_start, time.min, tzinfo=timezone)
    next_month_at = datetime.combine(next_month, time.min, tzinfo=timezone)

    entry_times = session.scalars(
        select(RegistroPonto.data_hora).where(
            RegistroPonto.usuario_id == user_id,
            RegistroPonto.tipo_registro == "entrada",
            RegistroPonto.data_hora >= month_start_at,
            RegistroPonto.data_hora < next_month_at,
        )
    )
    working_days = len(
        {timestamp.astimezone(timezone).date() for timestamp in entry_times}
    )
    planned_days_off = session.scalar(
        select(func.count(Folga.id)).where(
            Folga.usuario_id == user_id,
            Folga.status == "planejada",
            Folga.data >= month_start,
            Folga.data <= month_end,
        )
    )
    completed_days_off = session.scalar(
        select(func.count(Folga.id)).where(
            Folga.usuario_id == user_id,
            Folga.status == "realizada",
            Folga.data >= month_start,
            Folga.data <= month_end,
        )
    )
    latest = session.scalar(
        select(RegistroPonto)
        .where(RegistroPonto.usuario_id == user_id)
        .order_by(RegistroPonto.data_hora.desc(), RegistroPonto.id.desc())
        .limit(1)
    )
    schedule = session.scalar(
        select(ConfiguracaoJornada).where(ConfiguracaoJornada.usuario_id == user_id)
    )
    return {
        "working_days": working_days,
        "planned_days_off": planned_days_off or 0,
        "completed_days_off": completed_days_off or 0,
        "latest_punch": latest,
        "schedule": schedule,
    }
