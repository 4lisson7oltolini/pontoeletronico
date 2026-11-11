"""Account-scoped time punch operations."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import AjustePonto, RegistroPonto, Usuario
from utils.datetime_utils import app_timezone, now_local

PUNCH_SEQUENCE = ("entrada", "saida_intervalo", "retorno_intervalo", "saida")


class PontoError(ValueError):
    """Raised when a time punch or correction violates business rules."""


def _day_bounds(timestamp: datetime) -> tuple[datetime, datetime]:
    local_timestamp = _to_local(timestamp)
    start = datetime.combine(local_timestamp.date(), time.min, tzinfo=app_timezone())
    return start, start + timedelta(days=1)


def _to_local(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return timestamp.replace(tzinfo=app_timezone())
    return timestamp.astimezone(app_timezone())


def _validate_retroactive_date(day: date) -> None:
    today = now_local().date()
    if day >= today:
        raise PontoError("Só é possível alterar dias anteriores a hoje.")
    if (day.year, day.month) != (today.year, today.month):
        raise PontoError("Alterações retroativas estão disponíveis somente no mês atual.")


def _latest_adjustments(
    session: Session, user_id: int, punches: list[RegistroPonto]
) -> dict[int, AjustePonto]:
    if not punches:
        return {}
    adjustments = session.scalars(
        select(AjustePonto)
        .where(
            AjustePonto.usuario_id == user_id,
            AjustePonto.registro_ponto_id.in_([punch.id for punch in punches]),
        )
        .order_by(AjustePonto.criado_em, AjustePonto.id)
    )
    latest: dict[int, AjustePonto] = {}
    for adjustment in adjustments:
        latest[adjustment.registro_ponto_id] = adjustment
    return latest


def effective_punch_times(
    session: Session, user_id: int, punches: list[RegistroPonto]
) -> dict[int, datetime]:
    latest = _latest_adjustments(session, user_id, punches)
    return {
        punch.id: _to_local(
            latest[punch.id].horario_corrigido
            if punch.id in latest
            else punch.data_hora
        )
        for punch in punches
    }


def _validate_day_sequence(
    punches: list[RegistroPonto],
    effective_times: dict[int, datetime],
    *,
    candidate_type: str | None = None,
    candidate_time: datetime | None = None,
    excluded_id: int | None = None,
) -> None:
    entries = [
        (effective_times[punch.id], punch.tipo_registro)
        for punch in punches
        if punch.id != excluded_id
    ]
    if candidate_type is not None and candidate_time is not None:
        entries.append((candidate_time, candidate_type))
    entries.sort(key=lambda item: item[0])

    types = [kind for _, kind in entries]
    if len({timestamp for timestamp, _ in entries}) != len(entries):
        raise PontoError("Já existe uma marcação neste mesmo horário.")
    if len(set(types)) != len(types):
        raise PontoError("Já existe uma marcação desse tipo neste dia.")
    positions = [PUNCH_SEQUENCE.index(kind) for kind in types]
    if positions and (
        positions[0] != 0
        or any(current <= previous for previous, current in zip(positions, positions[1:]))
    ):
        raise PontoError(
            "As marcações do dia precisam manter a sequência: entrada, "
            "saída para intervalo, retorno e saída final."
        )


def _punches_for_day(
    session: Session, user_id: int, day: date
) -> list[RegistroPonto]:
    month_start = day.replace(day=1)
    if day.month == 12:
        next_month = date(day.year + 1, 1, 1)
    else:
        next_month = date(day.year, day.month + 1, 1)
    month_start_at = datetime.combine(month_start, time.min, tzinfo=app_timezone())
    next_month_at = datetime.combine(next_month, time.min, tzinfo=app_timezone())
    punches = list(
        session.scalars(
            select(RegistroPonto)
            .where(
                RegistroPonto.usuario_id == user_id,
                RegistroPonto.data_hora >= month_start_at,
                RegistroPonto.data_hora < next_month_at,
            )
            .order_by(RegistroPonto.data_hora, RegistroPonto.id)
        )
    )
    effective_times = effective_punch_times(session, user_id, punches)
    return [punch for punch in punches if effective_times[punch.id].date() == day]


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
    corrected_local = _to_local(corrected_at)
    _validate_retroactive_date(corrected_local.date())

    account = session.scalar(
        select(Usuario).where(Usuario.id == user_id).with_for_update()
    )
    if account is None or not account.ativo:
        raise PontoError("Conta não encontrada ou inativa.")
    punch = session.scalar(
        select(RegistroPonto).where(
            RegistroPonto.id == punch_id, RegistroPonto.usuario_id == user_id
        )
    )
    if punch is None:
        raise PontoError("Registro não encontrado.")
    current_time = effective_punch_times(session, user_id, [punch])[punch.id]
    _validate_retroactive_date(current_time.date())
    day_punches = _punches_for_day(session, user_id, corrected_local.date())
    day_times = effective_punch_times(session, user_id, day_punches)
    if current_time.date() != corrected_local.date():
        old_day_punches = _punches_for_day(session, user_id, current_time.date())
        old_day_times = effective_punch_times(session, user_id, old_day_punches)
        _validate_day_sequence(
            old_day_punches,
            old_day_times,
            excluded_id=punch.id,
        )
    _validate_day_sequence(
        day_punches,
        day_times,
        candidate_type=punch.tipo_registro,
        candidate_time=corrected_local,
        excluded_id=punch.id,
    )
    adjustment = AjustePonto(
        usuario_id=user_id,
        registro_ponto_id=punch.id,
        horario_original=current_time,
        horario_corrigido=corrected_local,
        justificativa=reason,
        operacao="correcao",
        criado_em=now_local(),
    )
    session.add(adjustment)
    session.commit()
    return adjustment


def add_retroactive_punch(
    session: Session,
    user_id: int,
    day: date,
    tipo_registro: str,
    punch_time: time,
    justification: str,
) -> RegistroPonto:
    reason = justification.strip()
    if not reason or len(reason) > 1000:
        raise PontoError("A justificativa é obrigatória (até 1000 caracteres).")
    if tipo_registro not in PUNCH_SEQUENCE:
        raise PontoError("Tipo de marcação inválido.")
    _validate_retroactive_date(day)

    account = session.scalar(
        select(Usuario).where(Usuario.id == user_id).with_for_update()
    )
    if account is None or not account.ativo:
        raise PontoError("Conta não encontrada ou inativa.")

    timestamp = datetime.combine(day, punch_time, tzinfo=app_timezone())
    day_punches = _punches_for_day(session, user_id, day)
    day_times = effective_punch_times(session, user_id, day_punches)
    _validate_day_sequence(
        day_punches,
        day_times,
        candidate_type=tipo_registro,
        candidate_time=timestamp,
    )

    punch = RegistroPonto(
        usuario_id=user_id,
        tipo_registro=tipo_registro,
        data_hora=timestamp,
        origem="ajuste_manual",
        criado_em=now_local(),
    )
    session.add(punch)
    session.flush()
    session.add(
        AjustePonto(
            usuario_id=user_id,
            registro_ponto_id=punch.id,
            horario_original=timestamp,
            horario_corrigido=timestamp,
            justificativa=reason,
            operacao="inclusao",
            criado_em=now_local(),
        )
    )
    session.commit()
    session.refresh(punch)
    return punch


def list_adjustments(session: Session, user_id: int) -> list[AjustePonto]:
    return list(
        session.scalars(
            select(AjustePonto)
            .where(AjustePonto.usuario_id == user_id)
            .order_by(AjustePonto.criado_em.desc(), AjustePonto.id.desc())
        )
    )
