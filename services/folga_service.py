"""Account-scoped rest-day planning."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import Folga
from utils.datetime_utils import now_local


class FolgaError(ValueError):
    """Raised when a rest-day transition is invalid."""


def plan_day_off(session: Session, user_id: int, day: date, observation: str = "") -> Folga:
    if session.scalar(
        select(Folga.id).where(Folga.usuario_id == user_id, Folga.data == day)
    ):
        raise FolgaError("Já existe uma folga registrada para esta data.")
    note = observation.strip() or None
    if note and len(note) > 500:
        raise FolgaError("A observação não pode ultrapassar 500 caracteres.")
    day_off = Folga(
        usuario_id=user_id,
        data=day,
        status="planejada",
        observacao=note,
        criado_em=now_local(),
    )
    session.add(day_off)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise FolgaError("Já existe uma folga registrada para esta data.") from exc
    session.refresh(day_off)
    return day_off


def update_day_off(
    session: Session, user_id: int, day_off_id: int, status: str, observation: str | None = None
) -> Folga:
    if status not in {"realizada", "cancelada"}:
        raise FolgaError("Transição de status inválida.")
    day_off = session.scalar(
        select(Folga).where(Folga.id == day_off_id, Folga.usuario_id == user_id)
    )
    if day_off is None:
        raise FolgaError("Folga não encontrada.")
    if day_off.status != "planejada":
        raise FolgaError("Somente uma folga planejada pode ser atualizada.")
    if observation is not None:
        note = observation.strip() or None
        if note and len(note) > 500:
            raise FolgaError("A observação não pode ultrapassar 500 caracteres.")
        day_off.observacao = note
    day_off.status = status
    session.commit()
    session.refresh(day_off)
    return day_off


def list_days_off(
    session: Session, user_id: int, start: date | None = None, end: date | None = None
) -> list[Folga]:
    statement = select(Folga).where(Folga.usuario_id == user_id)
    if start is not None:
        statement = statement.where(Folga.data >= start)
    if end is not None:
        statement = statement.where(Folga.data <= end)
    return list(session.scalars(statement.order_by(Folga.data.desc(), Folga.id.desc())))
