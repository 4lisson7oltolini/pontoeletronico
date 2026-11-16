"""Employee punch-change requests and HR decisions."""

from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import RegistroPonto, SolicitacaoAjustePonto, Usuario
from services.audit_service import record_audit_event
from services.auth_service import assert_user_role, get_active_user
from services.notificacao_service import (
    notify_pending_request,
    notify_request_decision,
)
from services.ponto_service import (
    PUNCH_SEQUENCE,
    PontoError,
    _punches_for_day,
    _stage_punch_correction,
    _stage_retroactive_punch,
    effective_punch_times,
)
from utils.datetime_utils import app_timezone, now_local


class SolicitacaoError(ValueError):
    """Raised when a punch-change request is invalid or cannot be decided."""


def _validate_request(day: date, justification: str) -> str:
    reason = justification.strip()
    if not reason or len(reason) > 1000:
        raise SolicitacaoError("A justificativa é obrigatória (até 1000 caracteres).")
    today = now_local().date()
    if day >= today:
        raise SolicitacaoError("Só é possível solicitar alterações para dias anteriores a hoje.")
    if (day.year, day.month) != (today.year, today.month):
        raise SolicitacaoError("Solicitações estão disponíveis somente para o mês atual.")
    return reason


def create_missing_punch_request(
    session: Session,
    user_id: int,
    day: date,
    tipo_registro: str,
    punch_time: time,
    justification: str,
) -> SolicitacaoAjustePonto:
    user = get_active_user(session, user_id)
    assert_user_role(user, ("funcionario", "rh", "admin"))
    if tipo_registro not in PUNCH_SEQUENCE:
        raise SolicitacaoError("Tipo de marcação inválido.")
    reason = _validate_request(day, justification)
    timestamp = datetime.combine(day, punch_time, tzinfo=app_timezone())
    existing_punches = [
        punch
        for punch in _punches_for_day(session, user_id, day)
        if punch.tipo_registro == tipo_registro
    ]
    if len(existing_punches) > 1:
        raise SolicitacaoError(
            "Há mais de uma marcação desse tipo neste dia. "
            "Solicite a correção pelo histórico."
        )
    if existing_punches:
        return create_correction_request(
            session,
            user_id,
            existing_punches[0].id,
            timestamp,
            reason,
        )

    day_start = datetime.combine(day, time.min, tzinfo=app_timezone())
    day_end = datetime.combine(date.fromordinal(day.toordinal() + 1), time.min, tzinfo=app_timezone())
    duplicate = session.scalar(
        select(SolicitacaoAjustePonto.id).where(
            SolicitacaoAjustePonto.usuario_id == user_id,
            SolicitacaoAjustePonto.operacao == "inclusao",
            SolicitacaoAjustePonto.status == "pendente",
            SolicitacaoAjustePonto.tipo_registro == tipo_registro,
            SolicitacaoAjustePonto.horario_solicitado >= day_start,
            SolicitacaoAjustePonto.horario_solicitado < day_end,
        )
    )
    if duplicate is not None:
        raise SolicitacaoError("Já existe um pedido pendente para essa marcação.")

    request = SolicitacaoAjustePonto(
        usuario_id=user_id,
        registro_ponto_id=None,
        operacao="inclusao",
        tipo_registro=tipo_registro,
        horario_solicitado=timestamp,
        justificativa=reason,
        criado_em=now_local(),
    )
    session.add(request)
    session.flush()
    notify_pending_request(session, request, user.nome)
    record_audit_event(
        session,
        "punch_change.requested",
        actor_id=user_id,
        target_id=user_id,
        entity="solicitacao_ajuste_ponto",
        entity_id=request.id,
        details={
            "operation": request.operacao,
            "punch_type": request.tipo_registro,
            "requested_at": request.horario_solicitado.isoformat(),
        },
    )
    session.commit()
    session.refresh(request)
    return request


def create_correction_request(
    session: Session,
    user_id: int,
    punch_id: int,
    corrected_at: datetime,
    justification: str,
) -> SolicitacaoAjustePonto:
    user = get_active_user(session, user_id)
    punch = session.scalar(
        select(RegistroPonto).where(
            RegistroPonto.id == punch_id,
            RegistroPonto.usuario_id == user_id,
        )
    )
    if punch is None:
        raise SolicitacaoError("Registro não encontrado.")
    current_time = effective_punch_times(session, user_id, [punch])[punch.id]
    reason = _validate_request(current_time.date(), justification)
    corrected_local = (
        corrected_at.replace(tzinfo=app_timezone())
        if corrected_at.tzinfo is None or corrected_at.utcoffset() is None
        else corrected_at.astimezone(app_timezone())
    )
    _validate_request(corrected_local.date(), reason)
    duplicate = session.scalar(
        select(SolicitacaoAjustePonto.id).where(
            SolicitacaoAjustePonto.usuario_id == user_id,
            SolicitacaoAjustePonto.registro_ponto_id == punch_id,
            SolicitacaoAjustePonto.operacao == "correcao",
            SolicitacaoAjustePonto.status == "pendente",
        )
    )
    if duplicate is not None:
        raise SolicitacaoError("Já existe um pedido pendente para esse registro.")

    request = SolicitacaoAjustePonto(
        usuario_id=user_id,
        registro_ponto_id=punch.id,
        operacao="correcao",
        tipo_registro=punch.tipo_registro,
        horario_solicitado=corrected_local,
        justificativa=reason,
        criado_em=now_local(),
    )
    session.add(request)
    session.flush()
    notify_pending_request(session, request, user.nome)
    record_audit_event(
        session,
        "punch_change.requested",
        actor_id=user_id,
        target_id=user_id,
        entity="solicitacao_ajuste_ponto",
        entity_id=request.id,
        details={
            "operation": request.operacao,
            "punch_type": request.tipo_registro,
            "requested_at": request.horario_solicitado.isoformat(),
        },
    )
    session.commit()
    session.refresh(request)
    return request


def list_user_requests(
    session: Session, user_id: int
) -> list[SolicitacaoAjustePonto]:
    get_active_user(session, user_id)
    return _list_requests_for_user(session, user_id)


def list_employee_requests_for_hr(
    session: Session, reviewer_id: int, employee_id: int
) -> list[SolicitacaoAjustePonto]:
    reviewer = get_active_user(session, reviewer_id)
    assert_user_role(reviewer, ("rh", "admin"))
    employee_exists = session.scalar(
        select(Usuario.id).where(
            Usuario.id == employee_id,
            Usuario.perfil == "funcionario",
        )
    )
    if employee_exists is None:
        raise SolicitacaoError("Funcionário não encontrado.")
    return _list_requests_for_user(session, employee_id)


def _list_requests_for_user(
    session: Session, user_id: int
) -> list[SolicitacaoAjustePonto]:
    return list(
        session.scalars(
            select(SolicitacaoAjustePonto)
            .where(SolicitacaoAjustePonto.usuario_id == user_id)
            .order_by(SolicitacaoAjustePonto.criado_em.desc())
        )
    )


def list_pending_requests(
    session: Session, reviewer_id: int
) -> list[tuple[SolicitacaoAjustePonto, str, str]]:
    reviewer = get_active_user(session, reviewer_id)
    assert_user_role(reviewer, ("rh", "admin"))
    rows = session.execute(
        select(SolicitacaoAjustePonto, Usuario.nome, Usuario.email)
        .join(Usuario, Usuario.id == SolicitacaoAjustePonto.usuario_id)
        .where(SolicitacaoAjustePonto.status == "pendente")
        .order_by(SolicitacaoAjustePonto.criado_em)
    )
    return list(rows.tuples())


def decide_request(
    session: Session,
    reviewer_id: int,
    request_id: int,
    *,
    approve: bool,
    decision_note: str,
) -> SolicitacaoAjustePonto:
    reviewer = get_active_user(session, reviewer_id)
    assert_user_role(reviewer, ("rh", "admin"))
    note = decision_note.strip()
    if not note or len(note) > 1000:
        raise SolicitacaoError("Informe uma observação para registrar a decisão.")

    request = session.scalar(
        select(SolicitacaoAjustePonto)
        .where(SolicitacaoAjustePonto.id == request_id)
        .with_for_update()
    )
    if request is None:
        raise SolicitacaoError("Solicitação não encontrada.")
    if request.status != "pendente":
        raise SolicitacaoError("Essa solicitação já foi decidida.")
    if request.usuario_id == reviewer_id:
        raise SolicitacaoError("Não é permitido decidir o próprio pedido.")

    if approve:
        try:
            if request.operacao == "inclusao":
                _stage_retroactive_punch(
                    session,
                    request.usuario_id,
                    request.horario_solicitado.date(),
                    request.tipo_registro,
                    request.horario_solicitado.timetz().replace(tzinfo=None),
                    request.justificativa,
                )
            else:
                _stage_punch_correction(
                    session,
                    request.usuario_id,
                    request.registro_ponto_id,
                    request.horario_solicitado,
                    request.justificativa,
                )
        except PontoError as exc:
            session.rollback()
            raise SolicitacaoError(str(exc)) from exc

    request.status = "aprovada" if approve else "rejeitada"
    request.decidido_por_id = reviewer_id
    request.decidido_em = now_local()
    request.observacao_decisao = note
    notify_request_decision(session, request)
    record_audit_event(
        session,
        "punch_change.decided",
        actor_id=reviewer_id,
        target_id=request.usuario_id,
        entity="solicitacao_ajuste_ponto",
        entity_id=request.id,
        details={
            "status": request.status,
            "operation": request.operacao,
            "punch_type": request.tipo_registro,
        },
    )
    session.commit()
    session.refresh(request)
    return request