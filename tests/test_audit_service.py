from io import BytesIO

from openpyxl import load_workbook
import pytest
from sqlalchemy import select

from database.models import EventoAuditoria
from services.audit_service import (
    export_audit_events_xlsx,
    list_audit_events,
    record_audit_event,
)
from services.auth_service import (
    AuthenticationError,
    AuthorizationError,
    authenticate_user,
    register_user,
)


def test_login_success_and_failure_are_audited_without_passwords(session):
    user = register_user(session, "Ana", "ana@example.com", "senha-segura-123")

    authenticate_user(session, user.email, "senha-segura-123")
    with pytest.raises(AuthenticationError):
        authenticate_user(session, user.email, "senha-incorreta")

    events = list(
        session.scalars(
            select(EventoAuditoria).where(
                EventoAuditoria.acao.in_(
                    ("auth.login_succeeded", "auth.login_failed")
                )
            )
        )
    )
    assert {event.acao for event in events} == {
        "auth.login_succeeded",
        "auth.login_failed",
    }
    failed_event = next(event for event in events if event.acao == "auth.login_failed")
    assert failed_event.detalhes == {"attempted_email": user.email}
    assert "senha-incorreta" not in str(failed_event.detalhes)


def test_audit_export_is_role_protected_and_safe_for_excel(session):
    employee = register_user(
        session,
        '=HYPERLINK("https://example.invalid")',
        "func@example.com",
        "senha-func-segura-123",
    )
    employee.perfil = "rh"
    session.commit()
    record_audit_event(
        session,
        "auth.login_failed",
        details={"attempted_email": "=HYPERLINK(\"https://example.invalid\")"},
    )
    session.commit()

    rows = list_audit_events(session, employee.id)
    workbook_bytes = export_audit_events_xlsx(rows)
    worksheet = load_workbook(BytesIO(workbook_bytes), data_only=False)["Auditoria"]

    assert worksheet.max_row == 3
    assert all(
        cell.data_type != "f"
        for row in worksheet.iter_rows()
        for cell in row
    )
    assert any(
        isinstance(cell.value, str) and cell.value.startswith("'=")
        for row in worksheet.iter_rows()
        for cell in row
    )

    employee.perfil = "funcionario"
    session.commit()
    with pytest.raises(AuthorizationError):
        list_audit_events(session, employee.id)
