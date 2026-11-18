from datetime import datetime
from io import BytesIO
import smtplib
import zipfile

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from database.models import EnvioRelatorioMensal, EventoAuditoria, RegistroPonto
from services.auth_service import register_user
from services.email_service import SMTPConfiguration
from services.monthly_report_delivery_service import dispatch_monthly_reports
from utils.datetime_utils import app_timezone

LOCAL_TZ = app_timezone()
RUN_AT = datetime(2026, 11, 1, 0, 1, tzinfo=LOCAL_TZ)


def _employee(session, name, email, created_at):
    user = register_user(session, name, email, "senha-segura-12345")
    user.criado_em = created_at
    session.commit()
    return user


def _punch(session, user_id, kind, stamped_at):
    session.add(
        RegistroPonto(
            usuario_id=user_id,
            tipo_registro=kind,
            data_hora=stamped_at,
            origem="web",
            criado_em=stamped_at,
        )
    )
    session.commit()


def test_monthly_reports_send_once_and_wait_for_open_month_end_shift(
    session, monkeypatch
):
    rh = _employee(
        session,
        "Equipe RH",
        "rh@example.com",
        datetime(2026, 1, 1, tzinfo=LOCAL_TZ),
    )
    rh.perfil = "rh"
    completed = _employee(
        session,
        "Ana Completa",
        "ana@example.com",
        datetime(2026, 10, 1, tzinfo=LOCAL_TZ),
    )
    pending = _employee(
        session,
        "Bia Noturna",
        "bia@example.com",
        datetime(2026, 10, 1, tzinfo=LOCAL_TZ),
    )
    registered_after_cutoff = _employee(
        session,
        "Conta Nova",
        "nova@example.com",
        datetime(2026, 11, 1, tzinfo=LOCAL_TZ),
    )
    session.commit()

    for kind, hour in (
        ("entrada", 9),
        ("saida_intervalo", 12),
        ("retorno_intervalo", 13),
        ("saida", 17),
    ):
        _punch(
            session,
            completed.id,
            kind,
            datetime(2026, 10, 31, hour, tzinfo=LOCAL_TZ),
        )
    for kind, hour, minute in (
        ("entrada", 22, 0),
        ("saida_intervalo", 23, 0),
        ("retorno_intervalo", 23, 30),
    ):
        _punch(
            session,
            pending.id,
            kind,
            datetime(2026, 10, 31, hour, minute, tzinfo=LOCAL_TZ),
        )

    monkeypatch.setattr(
        "services.monthly_report_delivery_service.get_smtp_configuration",
        lambda: SMTPConfiguration(
            host="smtp.example.com",
            port=587,
            sender="reports@example.com",
            username=None,
            password=None,
            use_ssl=False,
            use_starttls=True,
        ),
    )
    sent_emails = []

    def capture_email(configuration, message, recipients):
        message.as_bytes()
        sent_emails.append((message, recipients))

    monkeypatch.setattr(
        "services.monthly_report_delivery_service.send_email_message",
        capture_email,
    )

    first = dispatch_monthly_reports(session, RUN_AT)
    assert (first.queued, first.sent, first.deferred) == (2, 1, 1)
    assert len(sent_emails) == 1
    assert sent_emails[0][1] == [rh.email]
    archive_attachment = next(sent_emails[0][0].iter_attachments())
    with zipfile.ZipFile(BytesIO(archive_attachment.get_payload(decode=True))) as archive:
        assert len(archive.namelist()) == 1
        assert f"funcionario-{completed.id}-" in archive.namelist()[0]

    pending_delivery = session.scalar(
        select(EnvioRelatorioMensal).where(
            EnvioRelatorioMensal.usuario_id == pending.id
        )
    )
    assert pending_delivery.status == "pendente"
    assert session.scalar(
        select(EnvioRelatorioMensal).where(
            EnvioRelatorioMensal.usuario_id == registered_after_cutoff.id
        )
    ) is None

    _punch(
        session,
        pending.id,
        "saida",
        datetime(2026, 11, 1, 0, 30, tzinfo=LOCAL_TZ),
    )
    second = dispatch_monthly_reports(
        session, datetime(2026, 11, 1, 0, 31, tzinfo=LOCAL_TZ)
    )
    assert (second.queued, second.sent, second.deferred) == (0, 1, 0)
    assert len(sent_emails) == 2
    archive_attachment = next(sent_emails[1][0].iter_attachments())
    with zipfile.ZipFile(BytesIO(archive_attachment.get_payload(decode=True))) as archive:
        assert len(archive.namelist()) == 1
        assert f"funcionario-{pending.id}-" in archive.namelist()[0]
        workbook_bytes = archive.read(archive.namelist()[0])
    worksheet = load_workbook(BytesIO(workbook_bytes), data_only=True)[
        "Detalhamento diário"
    ]
    headers = [cell.value for cell in worksheet[1]]
    day_column = headers.index("Data de trabalho")
    final_punch_column = headers.index("Saída final")
    final_day = next(
        row
        for row in worksheet.iter_rows(min_row=2)
        if row[day_column].value.date() == datetime(2026, 10, 31).date()
    )
    assert final_day[final_punch_column].value == "01/11/2026 00:30"

    third = dispatch_monthly_reports(
        session, datetime(2026, 11, 1, 0, 46, tzinfo=LOCAL_TZ)
    )
    assert (third.queued, third.sent, third.deferred) == (0, 0, 0)
    assert len(sent_emails) == 2
    assert session.scalar(
        select(EnvioRelatorioMensal).where(
            EnvioRelatorioMensal.usuario_id == pending.id
        )
    ).status == "enviado"
    assert session.scalar(
        select(EventoAuditoria.id).where(
            EventoAuditoria.acao == "report.monthly_emailed"
        )
    )


def test_failed_monthly_email_stays_pending_and_retries(session, monkeypatch):
    rh = _employee(
        session,
        "Equipe RH",
        "rh@example.com",
        datetime(2026, 1, 1, tzinfo=LOCAL_TZ),
    )
    rh.perfil = "rh"
    employee = _employee(
        session,
        "Ana",
        "ana@example.com",
        datetime(2026, 10, 1, tzinfo=LOCAL_TZ),
    )
    session.commit()
    monkeypatch.setattr(
        "services.monthly_report_delivery_service.get_smtp_configuration",
        lambda: SMTPConfiguration(
            host="smtp.example.com",
            port=587,
            sender="reports@example.com",
            username=None,
            password=None,
            use_ssl=False,
            use_starttls=True,
        ),
    )

    def fail_email(*_args):
        raise smtplib.SMTPException("mail server unavailable")

    monkeypatch.setattr(
        "services.monthly_report_delivery_service.send_email_message",
        fail_email,
    )
    with pytest.raises(smtplib.SMTPException):
        dispatch_monthly_reports(session, RUN_AT)

    delivery = session.scalar(
        select(EnvioRelatorioMensal).where(
            EnvioRelatorioMensal.usuario_id == employee.id
        )
    )
    assert delivery.status == "pendente"
    assert delivery.enviado_em is None

    sent = []
    monkeypatch.setattr(
        "services.monthly_report_delivery_service.send_email_message",
        lambda *_args: sent.append(True),
    )
    result = dispatch_monthly_reports(
        session, datetime(2026, 11, 1, 0, 16, tzinfo=LOCAL_TZ)
    )
    assert result.sent == 1
    assert sent == [True]
    assert delivery.status == "enviado"
