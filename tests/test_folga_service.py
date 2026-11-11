from datetime import date

import pytest

from services.auth_service import register_user
from services.folga_service import FolgaError, list_days_off, plan_day_off, update_day_off


def test_planned_day_off_transitions_are_explicit(session):
    user = register_user(session, "Ana Silva", "ana@example.com", "senha-segura-123")
    day_off = plan_day_off(session, user.id, date(2026, 12, 25), "Natal")
    assert day_off.status == "planejada"
    assert day_off.observacao == "Natal"

    completed = update_day_off(session, user.id, day_off.id, "realizada")
    assert completed.status == "realizada"
    with pytest.raises(FolgaError, match="Somente"):
        update_day_off(session, user.id, day_off.id, "cancelada")

    assert len(list_days_off(session, user.id, date(2026, 12, 25), date(2026, 12, 25))) == 1
