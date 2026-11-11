"""Account-scoped time punch operations."""

from datetime import datetime, time, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import AjustePonto, RegistroPonto, Usuario
from utils.datetime_utils import app_timezone, now_local

PUNCH_SEQUENCE = ("entrada", "saida_intervalo", "retorno_intervalo", "saida")


class PontoError(ValueError):
    """Raised when a time punch or correction violates business rules."""


def _day_bounds(timestamp: datetime) -> tuple[datetime, datetime]:
    local_timestamp = timestamp.astimezone(app_timezone())
    start = datetime.combine(local_timestamp.date(), time.min, tzinfo=app_timezone())
    return start, start + timedelta(days=1)


def register_punch(
    session: Session, user_id: int, tipo_registro: str, origem: str = "web"
) -> RegistroPonto:
    if tipo_registro not in PUNCH_SEQUENCE:
        raise PontoError("Tipo de marcação inválido.")
    if origem not in {"web", "mobile"}:
        raise PontoError("Origem de marcação inválida.")

    account = session.scalar(select(Usuario).where(Usuario.id == user_id).with_for_update())
    if account is None or not account.ativo:
        raise PontoError("Conta não encontrada ou inativa.")

    timestamp = now_local()
    day_start, day_end = _day_bounds(timestamp)
    last_punch = session.scalar(
        select(RegistroPonto)
        .where(
            RegistroPonto.usuario_id == user_id,
            RegistroPonto.data_hora >= day_start,
            RegistroPonto.data_hora < day_end,
        )
        .order_by(RegistroPonto.data_hora.desc(), RegistroPonto.id.desc())
        .limit(1)
    )
    expected_type = (
        PUNCH_SEQUENCE[0]
        if last_punch is None
        else PUNCH_SEQUENCE[PUNCH_SEQUENCE.index(last_punch.tipo_registro) + 1]
        if last_punch.tipo_registro != PUNCH_SEQUENCE[-1]
        else None
    )
    if expected_type != tipo_registro:
        raise PontoError(
            f"Marcação fora de sequência. Próxima marcação esperada: "
            f"{expected_type or 'nenhuma (jornada já encerrada hoje)'}."
        )

    punch = RegistroPonto(
        usuario_id=user_id,
        tipo_registro=tipo_registro,
        data_hora=timestamp,
        origem=origem,
        criado_em=timestamp,
    )
    session.add(punch)
    session.commit()
    session.refresh(punch)
    return punch


def list_punches(
    session: Session, user_id: int, start: datetime | None = None, end: datetime | None = None
) -> list[RegistroPonto]:
    statement = select(RegistroPonto).where(RegistroPonto.usuario_id == user_id)
    if start is not None:
        statement = statement.where(RegistroPonto.data_hora >= start)
    if end is not None:
        statement = statement.where(RegistroPonto.data_hora < end)
    return list(
        session.scalars(
            statement.order_by(RegistroPonto.data_hora.desc(), RegistroPonto.id.desc())
        )
    )


def correct_punch(
    session: Session, user_id: int, punch_id: int, corrected_at: datetime, justification: str
) -> AjustePonto:
    reason = justification.strip()
    if not reason or len(reason) > 1000:
        raise PontoError("A justificativa é obrigatória (até 1000 caracteres).")
    if corrected_at.tzinfo is None or corrected_at.utcoffset() is None:
        raise PontoError("O horário corrigido precisa incluir um fuso horário.")

    punch = session.scalar(
        select(RegistroPonto).where(
            RegistroPonto.id == punch_id, RegistroPonto.usuario_id == user_id
        )
    )
    if punch is None:
        raise PontoError("Registro não encontrado.")
    adjustment = AjustePonto(
        usuario_id=user_id,
        registro_ponto_id=punch.id,
        horario_original=punch.data_hora,
        horario_corrigido=corrected_at,
        justificativa=reason,
        criado_em=now_local(),
    )
    session.add(adjustment)
    session.commit()
    return adjustment


def list_adjustments(session: Session, user_id: int) -> list[AjustePonto]:
    return list(
        session.scalars(
            select(AjustePonto)
            .where(AjustePonto.usuario_id == user_id)
            .order_by(AjustePonto.criado_em.desc(), AjustePonto.id.desc())
        )
    )
