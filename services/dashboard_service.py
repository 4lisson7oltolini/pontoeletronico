"""Account-scoped dashboard summaries using the monthly report calculations."""

from calendar import monthrange
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import ConfiguracaoJornada, Folga
from services.ponto_service import effective_punch_times, list_punches
from services.relatorio_service import build_monthly_report


def dashboard_summary(session: Session, user_id: int, today: date) -> dict:
    month_start = today.replace(day=1)
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    monthly_report = build_monthly_report(
        session, user_id, today.year, today.month, as_of=today
    )
    all_punches = list_punches(session, user_id)
    effective_times = effective_punch_times(session, user_id, all_punches)
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
        "working_days": monthly_report["summary"]["days_worked"],
        "monthly_worked_hours": monthly_report["summary"]["worked_hours"],
        "monthly_overtime": monthly_report["summary"]["total_overtime"],
        "incomplete_days": monthly_report["summary"]["incomplete_days"],
        "planned_days_off": planned_days_off or 0,
        "completed_days_off": completed_days_off or 0,
        "latest_punch": latest,
        "latest_punch_time": effective_times[latest.id] if latest else None,
        "schedule": schedule,
    }
