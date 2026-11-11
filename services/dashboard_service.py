"""Account-scoped dashboard summaries without full work-hour calculations."""

from calendar import monthrange
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import ConfiguracaoJornada, Folga
from services.ponto_service import effective_punch_times, list_punches


def dashboard_summary(session: Session, user_id: int, today: date) -> dict:
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    next_month = date(
        today.year + (1 if today.month == 12 else 0),
        today.month % 12 + 1,
        1,
    )
    all_punches = list_punches(session, user_id)
    effective_times = effective_punch_times(session, user_id, all_punches)
    month_punches = [
        punch
        for punch in all_punches
        if month_start <= effective_times[punch.id].date() < next_month
    ]
    working_days = len(
        {
            effective_times[punch.id].date()
            for punch in month_punches
            if punch.tipo_registro == "entrada"
        }
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
    latest = max(
        all_punches,
        key=lambda punch: (effective_times[punch.id], punch.id),
        default=None,
    )
    schedule = session.scalar(
        select(ConfiguracaoJornada).where(ConfiguracaoJornada.usuario_id == user_id)
    )
    return {
        "working_days": working_days,
        "planned_days_off": planned_days_off or 0,
        "completed_days_off": completed_days_off or 0,
        "latest_punch": latest,
        "latest_punch_time": effective_times[latest.id] if latest else None,
        "schedule": schedule,
    }
