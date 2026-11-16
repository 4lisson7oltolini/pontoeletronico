"""Account-scoped dashboard summaries using the monthly report calculations."""

from datetime import date
from calendar import monthrange

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from database.models import Folga, Usuario
from services.auth_service import (
    AuthorizationError,
    get_active_user,
)
from services.ponto_service import latest_punch
from services.relatorio_service import build_monthly_report
from services.rh_service import employee_selection_context, get_hr_employee


def dashboard_context(session: Session, actor_id: int) -> tuple[str, list[Usuario]]:
    actor, employees = employee_selection_context(session, actor_id)
    return actor.perfil, employees


def dashboard_summary(session: Session, user_id: int, today: date) -> dict:
    month_start = today.replace(day=1)
    monthly_report = build_monthly_report(
        session, user_id, today.year, today.month, as_of=today
    )
    month_end = today.replace(day=monthrange(today.year, today.month)[1])
    day_off_counts = session.execute(
        select(
            func.sum(case((Folga.status == "planejada", 1), else_=0)),
            func.sum(case((Folga.status == "realizada", 1), else_=0)),
        ).where(
            Folga.usuario_id == user_id,
            Folga.status.in_(("planejada", "realizada")),
            Folga.data >= month_start,
            Folga.data <= month_end,
        )
    ).one()
    latest, latest_time = latest_punch(session, user_id)
    return {
        "working_days": monthly_report["summary"]["days_worked"],
        "monthly_worked_hours": monthly_report["summary"]["worked_hours"],
        "monthly_overtime": monthly_report["summary"]["total_overtime"],
        "incomplete_days": monthly_report["summary"]["incomplete_days"],
        "planned_days_off": day_off_counts[0] or 0,
        "completed_days_off": day_off_counts[1] or 0,
        "latest_punch": latest,
        "latest_punch_time": latest_time,
        "schedule": monthly_report["schedule"],
    }


def dashboard_summary_for_actor(
    session: Session, actor_id: int, target_user_id: int, today: date
) -> dict:
    actor = get_active_user(session, actor_id)
    if actor.perfil in {"rh", "admin"}:
        get_hr_employee(session, actor_id, target_user_id)
    elif actor.id != target_user_id:
        raise AuthorizationError("Você não tem permissão para consultar este dashboard.")

    return dashboard_summary(session, target_user_id, today)
