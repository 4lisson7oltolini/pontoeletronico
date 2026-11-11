"""Personal work schedule preferences."""

from decimal import Decimal
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import ConfiguracaoJornada


class JornadaError(ValueError):
    """Raised when schedule preferences are invalid."""


def get_schedule(session: Session, user_id: int) -> ConfiguracaoJornada | None:
    return session.scalar(
        select(ConfiguracaoJornada).where(ConfiguracaoJornada.usuario_id == user_id)
    )


def save_schedule(
    session: Session,
    user_id: int,
    daily_hours: Decimal,
    weekly_hours: Decimal,
    preferred_start: time | None,
    preferred_end: time | None,
    break_count: int,
    timezone: str,
) -> ConfiguracaoJornada:
    if not Decimal("0") < daily_hours <= Decimal("24"):
        raise JornadaError("A jornada diária deve estar entre 0 e 24 horas.")
    if not Decimal("0") < weekly_hours <= Decimal("168"):
        raise JornadaError("A jornada semanal deve estar entre 0 e 168 horas.")
    if not 0 <= break_count <= 10:
        raise JornadaError("A quantidade de intervalos deve estar entre 0 e 10.")
    try:
        ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise JornadaError("Fuso horário inválido.") from exc

    schedule = get_schedule(session, user_id)
    if schedule is None:
        schedule = ConfiguracaoJornada(usuario_id=user_id)
        session.add(schedule)
    schedule.horas_diarias_referencia = daily_hours
    schedule.horas_semanais_referencia = weekly_hours
    schedule.horario_entrada_preferencial = preferred_start
    schedule.horario_saida_preferencial = preferred_end
    schedule.quantidade_intervalos = break_count
    schedule.fuso_horario = timezone
    session.commit()
    session.refresh(schedule)
    return schedule
