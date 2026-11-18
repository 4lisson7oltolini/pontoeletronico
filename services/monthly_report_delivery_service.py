"""Scheduled monthly report generation and delivery to active RH accounts."""

import re
import smtplib
import ssl
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from email.message import EmailMessage
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import EnvioRelatorioMensal, Usuario
from services.audit_service import record_audit_event
from services.email_service import (
    EmailConfigurationError,
    SMTPConfiguration,
    get_smtp_configuration,
    send_email_message,
)
from services.ponto_service import PUNCH_SEQUENCE, effective_punch_times
from services.relatorio_service import (
    build_monthly_report,
    export_monthly_report_xlsx,
    group_punches_by_workday,
    monthly_punches,
    report_period_end,
)
from utils.datetime_utils import app_timezone, now_local


@dataclass(frozen=True)
class DispatchResult:
    queued: int
    sent: int
    deferred: int


def _previous_month(current_date: date) -> tuple[int, int]:
    if current_date.month == 1:
        return current_date.year - 1, 12
    return current_date.year, current_date.month - 1


def _first_day_after_month(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1)
    return date(year, month + 1, 1)


def _enqueue_month(
    session: Session, year: int, month: int, created_at: datetime
) -> int:
    cutoff = datetime.combine(
        _first_day_after_month(year, month), time.min, tzinfo=app_timezone()
    )
    employees = list(
        session.scalars(
            select(Usuario).where(
                Usuario.perfil == "funcionario",
                Usuario.criado_em < cutoff,
            )
        )
    )
    existing_ids = set(
        session.scalars(
            select(EnvioRelatorioMensal.usuario_id).where(
                EnvioRelatorioMensal.ano == year,
                EnvioRelatorioMensal.mes == month,
            )
        )
    )
    new_deliveries = [
        EnvioRelatorioMensal(
            usuario_id=employee.id,
            ano=year,
            mes=month,
            status="pendente",
            criado_em=created_at,
        )
        for employee in employees
        if employee.id not in existing_ids
    ]
    session.add_all(new_deliveries)
    session.commit()
    return len(new_deliveries)


def _has_open_month_end_shift(
    session: Session, user_id: int, year: int, month: int
) -> bool:
    month_end = report_period_end(year, month)
    punches = monthly_punches(session, user_id, year, month)
    effective_times = effective_punch_times(session, user_id, punches)
    month_days = group_punches_by_workday(punches, effective_times)
    kinds = [
        punch.tipo_registro for punch in month_days.get(month_end, [])
    ]
    return (
        0 < len(kinds) < len(PUNCH_SEQUENCE)
        and tuple(kinds) == PUNCH_SEQUENCE[: len(kinds)]
    )


def _safe_filename(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")
    return slug[:48] or "funcionario"


def _build_monthly_zip(
    session: Session,
    deliveries: list[tuple[EnvioRelatorioMensal, Usuario]],
    as_of: date,
) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for delivery, employee in deliveries:
            report = build_monthly_report(
                session,
                employee.id,
                delivery.ano,
                delivery.mes,
                as_of=as_of,
            )
            workbook = export_monthly_report_xlsx(report, employee.nome)
            filename = (
                f"funcionario-{employee.id}-{_safe_filename(employee.nome)}-"
                f"{delivery.ano}-{delivery.mes:02d}.xlsx"
            )
            archive.writestr(filename, workbook)
    return output.getvalue()


def _send_monthly_email(
    configuration: SMTPConfiguration,
    recipients: list[str],
    year: int,
    month: int,
    attachment: bytes,
) -> None:
    message = EmailMessage()
    message["Subject"] = f"Relatórios de ponto - {month:02d}/{year}"
    message["From"] = configuration.sender
    message["To"] = "Destinatários ocultos:;"
    message.set_content(
        f"Segue o ZIP com os relatórios mensais individuais de {month:02d}/{year}. "
        "Funcionários com turno aberto no último dia do mês receberão o relatório "
        "em um envio posterior, após a marcação de saída final."
    )
    message.add_attachment(
        attachment,
        maintype="application",
        subtype="zip",
        filename=f"relatorios-ponto-{year}-{month:02d}.zip",
    )
    send_email_message(configuration, message, recipients)


def _mark_deliveries_sent(
    session: Session,
    deliveries: list[tuple[EnvioRelatorioMensal, Usuario]],
    *,
    sent_at: datetime,
    recipient_count: int,
) -> None:
    for delivery, employee in deliveries:
        delivery.status = "enviado"
        delivery.enviado_em = sent_at
        record_audit_event(
            session,
            "report.monthly_emailed",
            target_id=employee.id,
            entity="monthly_report_delivery",
            entity_id=delivery.id,
            details={
                "year": delivery.ano,
                "month": delivery.mes,
                "recipient_count": recipient_count,
            },
        )
    session.commit()


def dispatch_monthly_reports(
    session: Session, current_time: datetime | None = None
) -> DispatchResult:
    """Queue the previous month's reports and send all reports that are complete."""
    run_at = current_time or now_local()
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        run_at = run_at.replace(tzinfo=app_timezone())
    else:
        run_at = run_at.astimezone(app_timezone())

    year, month = _previous_month(run_at.date())
    queued = (
        _enqueue_month(session, year, month, run_at)
        if run_at.day <= 3
        else 0
    )

    pending = list(
        session.execute(
            select(EnvioRelatorioMensal, Usuario)
            .join(Usuario, Usuario.id == EnvioRelatorioMensal.usuario_id)
            .where(EnvioRelatorioMensal.status == "pendente")
            .order_by(
                EnvioRelatorioMensal.ano,
                EnvioRelatorioMensal.mes,
                Usuario.id,
            )
            .with_for_update()
        )
    )
    ready_by_period: dict[
        tuple[int, int], list[tuple[EnvioRelatorioMensal, Usuario]]
    ] = defaultdict(list)
    deferred = 0
    for delivery, employee in pending:
        if _has_open_month_end_shift(
            session, employee.id, delivery.ano, delivery.mes
        ):
            deferred += 1
            continue
        ready_by_period[(delivery.ano, delivery.mes)].append((delivery, employee))

    if not ready_by_period:
        return DispatchResult(queued=queued, sent=0, deferred=deferred)

    recipients = list(
        session.scalars(
            select(Usuario.email)
            .where(Usuario.perfil == "rh", Usuario.ativo.is_(True))
            .order_by(Usuario.id)
        )
    )
    if not recipients:
        raise RuntimeError(
            "Não há contas RH ativas para receber os relatórios mensais."
        )
    try:
        configuration = get_smtp_configuration()
    except EmailConfigurationError:
        raise
    if configuration is None:
        raise EmailConfigurationError(
            "Configure SMTP_HOST e SMTP_FROM para enviar os relatórios mensais."
        )

    sent = 0
    for (period_year, period_month), deliveries in sorted(ready_by_period.items()):
        attachment = _build_monthly_zip(
            session, deliveries, as_of=run_at.date()
        )
        try:
            _send_monthly_email(
                configuration,
                recipients,
                period_year,
                period_month,
                attachment,
            )
        except (OSError, smtplib.SMTPException, ssl.SSLError):
            session.rollback()
            raise
        _mark_deliveries_sent(
            session,
            deliveries,
            sent_at=run_at,
            recipient_count=len(recipients),
        )
        sent += len(deliveries)

    return DispatchResult(queued=queued, sent=sent, deferred=deferred)
