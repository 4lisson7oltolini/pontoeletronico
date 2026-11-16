"""Account-scoped in-app notifications for request activity."""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from database.models import Notificacao, SolicitacaoAjustePonto, Usuario
from services.auth_service import get_active_user
from utils.datetime_utils import now_local


class NotificacaoError(ValueError):
    """Raised when an in-app notification cannot be updated."""


def notify_pending_request(
    session: Session,
    request: SolicitacaoAjustePonto,
    employee_name: str,
) -> None:
    recipients = session.scalars(
        select(Usuario).where(
            Usuario.perfil.in_(("admin", "rh")),
            Usuario.ativo.is_(True),
            Usuario.id != request.usuario_id,
        )
    )
    operation = "inclusão esquecida" if request.operacao == "inclusao" else "correção"
    requested_at = request.horario_solicitado.strftime("%d/%m/%Y %H:%M")
    for recipient in recipients:
        session.add(
            Notificacao(
                usuario_id=recipient.id,
                solicitacao_id=request.id,
                tipo="solicitacao_pendente",
                titulo="Nova solicitação de ajuste",
                mensagem=(
                    f"{employee_name} enviou um pedido de {operation} "
                    f"para {requested_at}."
                ),
                criada_em=now_local(),
            )
        )


def notify_request_decision(
    session: Session, request: SolicitacaoAjustePonto
) -> None:
    approved = request.status == "aprovada"
    session.add(
        Notificacao(
            usuario_id=request.usuario_id,
            solicitacao_id=request.id,
            tipo="solicitacao_decidida",
            titulo="Sua solicitação foi analisada",
            mensagem=(
                "O RH/admin aprovou sua solicitação."
                if approved
                else "O RH/admin rejeitou sua solicitação."
            ),
            criada_em=now_local(),
        )
    )


def count_unread_notifications(session: Session, user_id: int) -> int:
    get_active_user(session, user_id)
    return int(
        session.scalar(
            select(func.count())
            .select_from(Notificacao)
            .where(
                Notificacao.usuario_id == user_id,
                Notificacao.lida_em.is_(None),
            )
        )
        or 0
    )


def list_notifications(
    session: Session, user_id: int, limit: int = 100
) -> list[Notificacao]:
    get_active_user(session, user_id)
    return list(
        session.scalars(
            select(Notificacao)
            .where(Notificacao.usuario_id == user_id)
            .order_by(Notificacao.criada_em.desc(), Notificacao.id.desc())
            .limit(limit)
        )
    )


def mark_notification_read(
    session: Session, user_id: int, notification_id: int
) -> None:
    get_active_user(session, user_id)
    notification = session.scalar(
        select(Notificacao)
        .where(
            Notificacao.id == notification_id,
            Notificacao.usuario_id == user_id,
        )
        .with_for_update()
    )
    if notification is None:
        raise NotificacaoError("Notificação não encontrada.")
    if notification.lida_em is None:
        notification.lida_em = now_local()
        session.commit()


def mark_all_notifications_read(session: Session, user_id: int) -> int:
    get_active_user(session, user_id)
    result = session.execute(
        update(Notificacao)
        .where(
            Notificacao.usuario_id == user_id,
            Notificacao.lida_em.is_(None),
        )
        .values(lida_em=now_local())
    )
    session.commit()
    return result.rowcount or 0
